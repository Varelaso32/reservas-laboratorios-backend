"""Configuración de reglas de espacios, tipos de uso y anticipación (HU-21, HU-22, HU-32, HU-36, HU-37).

Cada cambio queda registrado en `registro_configuracion` con usuario, fecha y hora
(HU-36.8, HU-37.6). No hace commit: lo hace quien llama.
"""
from datetime import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import JERARQUIA_RESERVA, RolReserva
from app.models.modelos import (
    Espacio,
    RegistroConfiguracion,
    ReglaAnticipacionRol,
    TipoUso,
    Usuario,
    espacio_tipo_uso,
)
from app.schemas.configuracion import (
    ReglasEspacioActualizar,
    TipoUsoActualizar,
    TipoUsoCrear,
)
from app.services import reglas
from app.utils.fechas import ZONA_COLOMBIA


class ErrorConfiguracion(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


_NOMBRE_TIPO_DUPLICADO = "Ya existe un tipo de uso con ese nombre"
_ESPACIO_NO_ENCONTRADO = "El espacio no existe"
_INDICE_TIPO_USO = "uq_tipo_uso_nombre"


# --------------------------------------------------------------------------- #
# Tipos de uso (HU-22)
# --------------------------------------------------------------------------- #
def listar_tipos_uso(db: Session, incluir_inactivos: bool = False) -> list[TipoUso]:
    consulta = select(TipoUso)
    if not incluir_inactivos:
        consulta = consulta.where(TipoUso.activo.is_(True))
    return list(db.scalars(consulta.order_by(TipoUso.nombre)))


def _guardar_tipo(db: Session, tipo: TipoUso) -> None:
    try:
        db.flush()
    except IntegrityError as error:
        if _INDICE_TIPO_USO in str(error.orig):
            raise ErrorConfiguracion(409, _NOMBRE_TIPO_DUPLICADO) from error
        raise


def _tipo_en_uso(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    consulta = select(TipoUso.id).where(TipoUso.nombre == nombre)
    if excluir_id is not None:
        consulta = consulta.where(TipoUso.id != excluir_id)
    return db.scalar(consulta) is not None


def crear_tipo_uso(db: Session, admin: Usuario, datos: TipoUsoCrear) -> TipoUso:
    if _tipo_en_uso(db, datos.nombre):
        raise ErrorConfiguracion(409, _NOMBRE_TIPO_DUPLICADO)
    tipo = TipoUso(nombre=datos.nombre, activo=True)
    db.add(tipo)
    _guardar_tipo(db, tipo)
    _registrar(db, admin, None, "TIPO_USO", f"Tipo de uso creado: {tipo.nombre}")
    db.commit()
    db.refresh(tipo)
    return tipo


def actualizar_tipo_uso(
    db: Session, admin: Usuario, tipo_id: int, datos: TipoUsoActualizar
) -> TipoUso:
    tipo = db.scalar(select(TipoUso).where(TipoUso.id == tipo_id).with_for_update())
    if tipo is None:
        raise ErrorConfiguracion(404, "El tipo de uso no existe")

    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and _tipo_en_uso(db, cambios["nombre"], tipo.id):
        raise ErrorConfiguracion(409, _NOMBRE_TIPO_DUPLICADO)

    for campo, valor in cambios.items():
        setattr(tipo, campo, valor)
    _guardar_tipo(db, tipo)
    _registrar(db, admin, None, "TIPO_USO", f"Tipo de uso actualizado: {tipo.nombre}")
    db.commit()
    db.refresh(tipo)
    return tipo


# --------------------------------------------------------------------------- #
# Reglas del espacio (HU-21, HU-28, HU-33, HU-34, HU-36)
# --------------------------------------------------------------------------- #
def _tomar_espacio(db: Session, espacio_id: int) -> Espacio:
    espacio = db.scalar(select(Espacio).where(Espacio.id == espacio_id).with_for_update())
    if espacio is None:
        raise ErrorConfiguracion(404, _ESPACIO_NO_ENCONTRADO)
    return espacio


def reglas_de(db: Session, espacio_id: int) -> dict:
    espacio = db.get(Espacio, espacio_id)
    if espacio is None:
        raise ErrorConfiguracion(404, _ESPACIO_NO_ENCONTRADO)
    return _salida_reglas(db, espacio)


def _salida_reglas(db: Session, espacio: Espacio) -> dict:
    tipos = reglas.tipos_permitidos(db, espacio.id)
    return {
        "espacio_id": espacio.id,
        "nombre": espacio.nombre,
        "tipo": espacio.tipo,
        "capacidad": espacio.capacidad,
        "activo": espacio.activo,
        "hora_apertura": espacio.hora_apertura,
        "hora_cierre": espacio.hora_cierre,
        "dias_operacion": sorted(reglas.dias_de(espacio)) or [1, 2, 3, 4, 5, 6, 7],
        "max_usos_dia": espacio.max_usos_dia,
        "duracion_maxima_min": espacio.duracion_maxima_min,
        "separacion_min": espacio.separacion_min or 0,
        "ocupacion_minima": espacio.ocupacion_minima,
        "requiere_responsable": espacio.requiere_responsable,
        "admite_autorizacion_especial": espacio.admite_autorizacion_especial,
        "tipos_uso": [
            {"id": tipo.id, "nombre": tipo.nombre, "activo": tipo.activo} for tipo in tipos
        ],
    }


def _aplicar_reglas(db: Session, espacio: Espacio, datos: ReglasEspacioActualizar) -> list[str]:
    """Copia las reglas enviadas al espacio. Devuelve el detalle legible del cambio."""
    cambios = datos.model_dump(exclude_unset=True)
    detalle: list[str] = []

    if "hora_apertura" in cambios or "hora_cierre" in cambios:
        apertura: time | None = cambios.get("hora_apertura", espacio.hora_apertura)
        cierre: time | None = cambios.get("hora_cierre", espacio.hora_cierre)
        if (apertura is None) != (cierre is None):
            raise ErrorConfiguracion(
                422, "La franja de operación necesita hora de apertura y de cierre, o ninguna"
            )
        if apertura is not None and cierre is not None and cierre <= apertura:
            raise ErrorConfiguracion(422, "La hora de cierre debe ser posterior a la de apertura")
        espacio.hora_apertura = apertura
        espacio.hora_cierre = cierre
        detalle.append(
            "franja "
            + (f"{apertura:%H:%M}-{cierre:%H:%M}" if apertura and cierre else "institucional")
        )

    if "dias_operacion" in cambios:
        espacio.dias_operacion = ",".join(str(dia) for dia in cambios["dias_operacion"])
        detalle.append(f"días {espacio.dias_operacion}")

    for campo, etiqueta in (
        ("max_usos_dia", "máximo de usos por día"),
        ("duracion_maxima_min", "duración máxima en minutos"),
        ("separacion_min", "separación en minutos"),
        ("ocupacion_minima", "ocupación mínima"),
    ):
        if campo in cambios:
            setattr(espacio, campo, cambios[campo])
            detalle.append(f"{etiqueta} {cambios[campo]}")

    for campo in ("requiere_responsable", "admite_autorizacion_especial"):
        if campo in cambios:
            setattr(espacio, campo, cambios[campo])
            detalle.append(f"{campo} {cambios[campo]}")

    if espacio.ocupacion_minima is not None and espacio.ocupacion_minima > espacio.capacidad:
        raise ErrorConfiguracion(
            422, "La ocupación mínima no puede superar la capacidad del espacio"
        )

    if "tipos_uso_ids" in cambios:
        _asignar_tipos(db, espacio, cambios["tipos_uso_ids"] or [])
        detalle.append(f"tipos de uso {sorted(cambios['tipos_uso_ids'] or [])}")

    return detalle


def _asignar_tipos(db: Session, espacio: Espacio, tipos_ids: list[int]) -> None:
    if tipos_ids:
        encontrados = set(
            db.scalars(select(TipoUso.id).where(TipoUso.id.in_(tipos_ids))).all()
        )
        faltantes = sorted(set(tipos_ids) - encontrados)
        if faltantes:
            raise ErrorConfiguracion(422, f"No existen los tipos de uso {faltantes}")

    db.execute(espacio_tipo_uso.delete().where(espacio_tipo_uso.c.espacio_id == espacio.id))
    for tipo_id in sorted(set(tipos_ids)):
        db.execute(
            espacio_tipo_uso.insert().values(espacio_id=espacio.id, tipo_uso_id=tipo_id)
        )


def actualizar_reglas(
    db: Session, admin: Usuario, espacio_id: int, datos: ReglasEspacioActualizar
) -> dict:
    espacio = _tomar_espacio(db, espacio_id)
    detalle = _aplicar_reglas(db, espacio, datos)
    db.flush()
    if detalle:
        _registrar(db, admin, espacio.id, "ESPACIO", "; ".join(detalle))
    db.commit()
    db.refresh(espacio)
    return _salida_reglas(db, espacio)


def aplicar_por_tipo(db: Session, admin: Usuario, tipo, datos: ReglasEspacioActualizar) -> list[dict]:
    """HU-36, criterio 5: copia la misma configuración a todos los espacios del tipo."""
    espacios = list(db.scalars(select(Espacio).where(Espacio.tipo == tipo).order_by(Espacio.nombre)))
    if not espacios:
        raise ErrorConfiguracion(404, f"No hay espacios de tipo {tipo.value}")

    salida = []
    for espacio in espacios:
        detalle = _aplicar_reglas(db, espacio, datos)
        db.flush()
        _registrar(
            db,
            admin,
            espacio.id,
            "ESPACIO",
            f"Reglas aplicadas al tipo {tipo.value}" + (f": {'; '.join(detalle)}" if detalle else ""),
        )
        salida.append(_salida_reglas(db, espacio))
    db.commit()
    return salida


# --------------------------------------------------------------------------- #
# Anticipación por rol (HU-32, HU-37)
# --------------------------------------------------------------------------- #
def listar_anticipacion(db: Session) -> list[dict]:
    configuradas = {
        regla.rol: regla.dias_maximos
        for regla in db.scalars(select(ReglaAnticipacionRol)).all()
    }
    return [
        {"rol": rol, "dias_maximos": configuradas.get(rol)} for rol in JERARQUIA_RESERVA
    ]


def actualizar_anticipacion(
    db: Session, admin: Usuario, rol: RolReserva, dias_maximos: int | None
) -> dict:
    regla = db.scalar(
        select(ReglaAnticipacionRol)
        .where(ReglaAnticipacionRol.rol == rol)
        .with_for_update()
    )
    if dias_maximos is None:
        if regla is not None:
            db.delete(regla)
    elif regla is None:
        db.add(
            ReglaAnticipacionRol(
                rol=rol, dias_maximos=dias_maximos, actualizado_por=admin.id
            )
        )
    else:
        regla.dias_maximos = dias_maximos
        regla.actualizado_por = admin.id

    db.flush()
    _registrar(
        db,
        admin,
        None,
        "ANTICIPACION",
        f"Anticipación de {rol.value}: "
        + (f"{dias_maximos} días" if dias_maximos is not None else "sin límite"),
    )
    db.commit()
    return {"rol": rol, "dias_maximos": dias_maximos}


# --------------------------------------------------------------------------- #
# Auditoría (HU-36.8, HU-37.6)
# --------------------------------------------------------------------------- #
def _registrar(
    db: Session, usuario: Usuario, espacio_id: int | None, entidad: str, detalle: str
) -> None:
    db.add(
        RegistroConfiguracion(
            usuario_id=usuario.id,
            espacio_id=espacio_id,
            entidad=entidad,
            detalle=detalle,
        )
    )


def historial(db: Session, espacio_id: int | None = None, limite: int = 50) -> list[dict]:
    consulta = (
        select(RegistroConfiguracion, Usuario.nombre)
        .join(Usuario, Usuario.id == RegistroConfiguracion.usuario_id)
        .order_by(RegistroConfiguracion.fecha.desc(), RegistroConfiguracion.id.desc())
        .limit(limite)
    )
    if espacio_id is not None:
        consulta = consulta.where(RegistroConfiguracion.espacio_id == espacio_id)
    filas = db.execute(consulta).all()
    return [
        {
            "id": registro.id,
            "entidad": registro.entidad,
            "espacio_id": registro.espacio_id,
            "usuario": nombre,
            "detalle": registro.detalle,
            "fecha": registro.fecha.astimezone(ZONA_COLOMBIA),
        }
        for registro, nombre in filas
    ]
