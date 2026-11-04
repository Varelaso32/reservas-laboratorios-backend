"""Recursos tecnológicos asociados a una reserva (HU-43 a HU-46).

- HU-43: catálogo administrado por el Administrador del Sistema. El alta pide
  nombre y cantidad: el sistema crea las unidades con etiqueta automática. Las
  unidades se pueden instalar como amenidad fija de un espacio, y entonces
  descuentan del stock disponible.
- HU-44: Docente, Coordinador o Director piden recursos para una reserva propia
  ACTIVA. El horario del recurso es el de la reserva y no se puede editar.
- HU-45: el administrador aprueba por orden de llegada y asigna unidades
  concretas de forma atómica; el stock baja al asignar.
- HU-46: entrega, devolución y penalización con el doble de strikes por retraso.

Igual que la asistencia, el vencimiento de las devoluciones se procesa de forma
perezosa (sin planificador): al consultar solicitudes o préstamos, y en el
endpoint administrativo de procesamiento.

No hace commit salvo en las operaciones que lo indican explícitamente.
"""
import re
import unicodedata
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    AccionTrazabilidad,
    EstadoAsignacion,
    EstadoRecurso,
    EstadoReserva,
    EstadoSolicitudRecurso,
    Rol,
    RolReserva,
    TipoNotificacion,
    rol_reserva_de,
)
from app.models.modelos import (
    AsignacionRecurso,
    DetalleSolicitudRecurso,
    Espacio,
    Recurso,
    RegistroConfiguracion,
    Reserva,
    SolicitudRecurso,
    Strike,
    TipoRecurso,
    Usuario,
)
from app.schemas.recurso import (
    DecisionSolicitudRecursoIn,
    DevolucionIn,
    RecursoActualizar,
    RecursoCrear,
    RecursoEstadoIn,
    SolicitudRecursoCrear,
    TipoRecursoActualizar,
    TipoRecursoCrear,
)
from app.services import notificaciones, sanciones, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA

ESTADOS_VIVOS = (EstadoAsignacion.ASIGNADA, EstadoAsignacion.ENTREGADA)
ESTADOS_VIGENTES_SOLICITUD = (
    EstadoSolicitudRecurso.PENDIENTE,
    EstadoSolicitudRecurso.APROBADA,
)
ROLES_QUE_PIDEN = (RolReserva.DOCENTE, RolReserva.COORDINADOR, RolReserva.DIRECTOR)


class ErrorRecurso(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def _admins(db: Session) -> list[Usuario]:
    return list(
        db.scalars(
            select(Usuario).where(Usuario.rol == Rol.ADMIN, Usuario.activo.is_(True))
        )
    )


# --------------------------------------------------------------------------- #
# HU-43: tipos de recurso
# --------------------------------------------------------------------------- #
def _conteos(db: Session) -> dict[int, dict[str, int]]:
    """Conteo por tipo: totales, instalados en espacios, fallidos, prestados y reservados."""
    totales = dict(
        db.execute(
            select(Recurso.tipo_recurso_id, func.count())
            .where(Recurso.activo.is_(True))
            .group_by(Recurso.tipo_recurso_id)
        ).all()
    )
    instalados = dict(
        db.execute(
            select(Recurso.tipo_recurso_id, func.count())
            .where(Recurso.activo.is_(True), Recurso.espacio_id.is_not(None))
            .group_by(Recurso.tipo_recurso_id)
        ).all()
    )
    fallidos = dict(
        db.execute(
            select(Recurso.tipo_recurso_id, func.count())
            .where(
                Recurso.activo.is_(True),
                Recurso.espacio_id.is_(None),
                Recurso.estado == EstadoRecurso.FALLIDO,
            )
            .group_by(Recurso.tipo_recurso_id)
        ).all()
    )
    prestados = dict(
        db.execute(
            select(Recurso.tipo_recurso_id, func.count())
            .join(AsignacionRecurso, AsignacionRecurso.recurso_id == Recurso.id)
            .where(
                Recurso.activo.is_(True),
                Recurso.espacio_id.is_(None),
                AsignacionRecurso.estado == EstadoAsignacion.ENTREGADA,
            )
            .group_by(Recurso.tipo_recurso_id)
        ).all()
    )
    reservados = dict(
        db.execute(
            select(Recurso.tipo_recurso_id, func.count())
            .join(AsignacionRecurso, AsignacionRecurso.recurso_id == Recurso.id)
            .where(
                Recurso.activo.is_(True),
                Recurso.espacio_id.is_(None),
                AsignacionRecurso.estado == EstadoAsignacion.ASIGNADA,
            )
            .group_by(Recurso.tipo_recurso_id)
        ).all()
    )
    return {
        tipo_id: {
            "total": total,
            "instalados": instalados.get(tipo_id, 0),
            "fallidos": fallidos.get(tipo_id, 0),
            "prestados": prestados.get(tipo_id, 0),
            "reservados": reservados.get(tipo_id, 0),
            "disponibles": max(
                0,
                total
                - instalados.get(tipo_id, 0)
                - fallidos.get(tipo_id, 0)
                - prestados.get(tipo_id, 0)
                - reservados.get(tipo_id, 0),
            ),
        }
        for tipo_id, total in totales.items()
    }


CONTEOS_VACIOS = {
    "total": 0,
    "instalados": 0,
    "disponibles": 0,
    "prestados": 0,
    "reservados": 0,
    "fallidos": 0,
}


def _salida_tipo(tipo: TipoRecurso, conteo: dict[str, int] | None = None) -> dict:
    conteo = conteo or CONTEOS_VACIOS
    return {
        "id": tipo.id,
        "nombre": tipo.nombre,
        "descripcion": tipo.descripcion,
        "activo": tipo.activo,
        **conteo,
    }


def listar_tipos(db: Session, solo_activos: bool = False) -> list[dict]:
    consulta = select(TipoRecurso)
    if solo_activos:
        consulta = consulta.where(TipoRecurso.activo.is_(True))
    tipos = list(db.scalars(consulta.order_by(TipoRecurso.nombre)))
    conteos = _conteos(db)
    return [_salida_tipo(tipo, conteos.get(tipo.id)) for tipo in tipos]


def stock_por_tipo(db: Session) -> list[dict]:
    """Stock global por tipo activo (HU-43, criterio 5)."""
    conteos = _conteos(db)
    return [
        {
            "tipo_recurso_id": tipo.id,
            "tipo": tipo.nombre,
            **(
                conteos.get(tipo.id)
                or {
                    "total": 0,
                    "instalados": 0,
                    "disponibles": 0,
                    "prestados": 0,
                    "reservados": 0,
                    "fallidos": 0,
                }
            ),
        }
        for tipo in _tipos_activos(db)
    ]


def _prefijo_codigo(nombre: str) -> str:
    """Prefijo legible para las etiquetas: «Cable HDMI» → «CABLE-HDMI»."""
    normalizado = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9]+", "-", normalizado).strip("-").upper()
    return limpio[:12].strip("-") or "REC"


def _codigos_nuevos(db: Session, tipo: TipoRecurso, cantidad: int) -> list[str]:
    """Etiquetas correlativas libres para las unidades nuevas: TV-001, TV-002..."""
    prefijo = _prefijo_codigo(tipo.nombre)
    usados = {codigo.lower() for codigo in db.scalars(select(Recurso.codigo))}
    codigos: list[str] = []
    consecutivo = 1
    while len(codigos) < cantidad:
        candidato = f"{prefijo}-{consecutivo:03d}"
        consecutivo += 1
        if candidato.lower() in usados:
            continue
        usados.add(candidato.lower())
        codigos.append(candidato)
    return codigos


def _crear_unidades(db: Session, admin: Usuario, tipo: TipoRecurso, cantidad: int) -> None:
    """Crea unidades nuevas del tipo con etiqueta automática (HU-43)."""
    for codigo in _codigos_nuevos(db, tipo, cantidad):
        db.add(
            Recurso(
                tipo_recurso_id=tipo.id,
                codigo=codigo,
                actualizado_por=admin.id,
            )
        )
    db.flush()


def _unidades_eliminables(db: Session, tipo_id: int) -> list[Recurso]:
    """Unidades activas que se pueden retirar: ni instaladas en un espacio ni prestadas."""
    return list(
        db.scalars(
            select(Recurso)
            .where(
                Recurso.tipo_recurso_id == tipo_id,
                Recurso.activo.is_(True),
                Recurso.espacio_id.is_(None),
                Recurso.id.not_in(
                    select(AsignacionRecurso.recurso_id).where(
                        AsignacionRecurso.estado.in_(ESTADOS_VIVOS)
                    )
                ),
            )
            .order_by(Recurso.codigo.desc())
        )
    )


def crear_tipo(db: Session, admin: Usuario, datos: TipoRecursoCrear) -> dict:
    existente = db.scalar(
        select(TipoRecurso).where(func.lower(TipoRecurso.nombre) == datos.nombre.lower())
    )
    if existente is not None:
        raise ErrorRecurso(409, "Ya existe un tipo de recurso con ese nombre")

    tipo = TipoRecurso(nombre=datos.nombre, descripcion=datos.descripcion)
    db.add(tipo)
    db.flush()
    if datos.cantidad:
        _crear_unidades(db, admin, tipo, datos.cantidad)
    _registrar_cambio(
        db,
        admin,
        f"Alta del recurso «{tipo.nombre}» con {datos.cantidad} unidad(es)",
    )
    db.commit()
    db.refresh(tipo)
    return _salida_tipo(tipo, _conteos(db).get(tipo.id))


def actualizar_tipo(
    db: Session, admin: Usuario, tipo_id: int, datos: TipoRecursoActualizar
) -> dict:
    tipo = db.get(TipoRecurso, tipo_id)
    if tipo is None:
        raise ErrorRecurso(404, "El tipo de recurso no existe")

    cambios: list[str] = []
    if datos.nombre is not None and datos.nombre.lower() != tipo.nombre.lower():
        repetido = db.scalar(
            select(TipoRecurso).where(
                func.lower(TipoRecurso.nombre) == datos.nombre.lower(),
                TipoRecurso.id != tipo.id,
            )
        )
        if repetido is not None:
            raise ErrorRecurso(409, "Ya existe un tipo de recurso con ese nombre")
        cambios.append(f"nombre «{tipo.nombre}» → «{datos.nombre}»")
        tipo.nombre = datos.nombre
    if datos.descripcion is not None:
        tipo.descripcion = datos.descripcion
        cambios.append("descripción actualizada")
    if datos.activo is not None and datos.activo != tipo.activo:
        tipo.activo = datos.activo
        cambios.append("activado" if datos.activo else "desactivado")
    if datos.cantidad is not None:
        actual = (
            db.scalar(
                select(func.count())
                .select_from(Recurso)
                .where(
                    Recurso.tipo_recurso_id == tipo.id,
                    Recurso.activo.is_(True),
                )
            )
            or 0
        )
        if datos.cantidad > actual:
            _crear_unidades(db, admin, tipo, datos.cantidad - actual)
            cambios.append(f"unidades {actual} → {datos.cantidad}")
        elif datos.cantidad < actual:
            a_quitar = actual - datos.cantidad
            eliminables = _unidades_eliminables(db, tipo.id)
            if len(eliminables) < a_quitar:
                raise ErrorRecurso(
                    409,
                    (
                        f"Solo puedes retirar {len(eliminables)} unidad(es) de «{tipo.nombre}»: "
                        "el resto está instalado en espacios o tiene un préstamo vigente"
                    ),
                )
            for recurso in eliminables[:a_quitar]:
                recurso.activo = False
                recurso.actualizado_por = admin.id
            cambios.append(f"unidades {actual} → {datos.cantidad}")

    if not cambios:
        return _salida_tipo(tipo, _conteos(db).get(tipo.id))

    _registrar_cambio(
        db, admin, f"Cambio en el tipo de recurso «{tipo.nombre}»: {', '.join(cambios)}"
    )
    db.commit()
    db.refresh(tipo)
    return _salida_tipo(tipo, _conteos(db).get(tipo.id))


# --------------------------------------------------------------------------- #
# Amenidades: unidades instaladas de forma fija en un espacio (HU-19 / HU-43)
# --------------------------------------------------------------------------- #
def listar_amenidades(db: Session, espacio_id: int | None = None) -> list[dict]:
    """Catálogo de recursos visto como amenidades, con las unidades que quedan libres."""
    conteos = _conteos(db)
    instaladas_aqui: set[int] = set()
    if espacio_id is not None:
        instaladas_aqui = set(
            db.scalars(
                select(Recurso.tipo_recurso_id).where(
                    Recurso.espacio_id == espacio_id,
                    Recurso.activo.is_(True),
                )
            )
        )
    return [
        {
            "tipo_recurso_id": tipo.id,
            "nombre": tipo.nombre,
            "descripcion": tipo.descripcion,
            "total": (conteos.get(tipo.id) or CONTEOS_VACIOS)["total"],
            "instalados": (conteos.get(tipo.id) or CONTEOS_VACIOS)["instalados"],
            "disponibles": (conteos.get(tipo.id) or CONTEOS_VACIOS)["disponibles"],
            "instalado_aqui": tipo.id in instaladas_aqui,
        }
        for tipo in _tipos_activos(db)
    ]


def amenidades_de_espacio(db: Session, espacio_id: int) -> list[dict]:
    """Recursos instalados de forma fija en el espacio."""
    tipos = db.execute(
        select(TipoRecurso)
        .join(Recurso, Recurso.tipo_recurso_id == TipoRecurso.id)
        .where(Recurso.espacio_id == espacio_id, Recurso.activo.is_(True))
        .order_by(TipoRecurso.nombre)
    ).scalars()
    return [{"tipo_recurso_id": tipo.id, "nombre": tipo.nombre} for tipo in tipos]


def _unidad_instalable(db: Session, tipo_id: int) -> Recurso | None:
    """Unidad libre y en funcionamiento que puede quedar instalada como amenidad."""
    return db.scalar(
        select(Recurso)
        .where(
            Recurso.tipo_recurso_id == tipo_id,
            Recurso.activo.is_(True),
            Recurso.espacio_id.is_(None),
            Recurso.estado == EstadoRecurso.EN_FUNCIONAMIENTO,
            Recurso.id.not_in(
                select(AsignacionRecurso.recurso_id).where(
                    AsignacionRecurso.estado.in_(ESTADOS_VIVOS)
                )
            ),
        )
        .order_by(Recurso.codigo)
        .with_for_update()
    )


def aplicar_amenidades(
    db: Session, espacio: Espacio, tipo_ids: list[int], actualizado_por: int
) -> None:
    """Reconcilia las amenidades del espacio descontando del stock disponible.

    Instalar una amenidad toma una unidad libre; quitarla la devuelve al stock.
    """
    deseados = set(tipo_ids)
    actuales = {
        recurso.tipo_recurso_id: recurso
        for recurso in db.scalars(
            select(Recurso).where(
                Recurso.espacio_id == espacio.id,
                Recurso.activo.is_(True),
            )
        )
    }
    for tipo_id, recurso in actuales.items():
        if tipo_id not in deseados:
            recurso.espacio_id = None
            recurso.actualizado_por = actualizado_por
    for tipo_id in deseados - set(actuales):
        tipo = db.get(TipoRecurso, tipo_id)
        if tipo is None or not tipo.activo:
            raise ErrorRecurso(404, f"El recurso {tipo_id} no existe o está inactivo")
        unidad = _unidad_instalable(db, tipo_id)
        if unidad is None:
            raise ErrorRecurso(
                409,
                f"No quedan unidades de «{tipo.nombre}» disponibles para instalar en el espacio",
            )
        unidad.espacio_id = espacio.id
        unidad.actualizado_por = actualizado_por
    db.flush()


# --------------------------------------------------------------------------- #
# HU-43: inventario de unidades
# --------------------------------------------------------------------------- #
def _registrar_cambio(db: Session, admin: Usuario, detalle: str) -> None:
    """Auditoría del inventario: usuario, fecha y hora (HU-43, criterio 8)."""
    db.add(RegistroConfiguracion(usuario_id=admin.id, entidad="RECURSO", detalle=detalle))
    db.flush()


def _salida_recurso(recurso: Recurso, tipo: TipoRecurso | None, espacio: Espacio | None) -> dict:
    return {
        "id": recurso.id,
        "tipo_recurso_id": recurso.tipo_recurso_id,
        "tipo": tipo.nombre if tipo else "",
        "codigo": recurso.codigo,
        "descripcion": recurso.descripcion,
        "estado": recurso.estado,
        "comentario_estado": recurso.comentario_estado,
        "espacio_id": recurso.espacio_id,
        "espacio": espacio.nombre if espacio else None,
        "activo": recurso.activo,
        "actualizado_en": _local(recurso.actualizado_en),
    }


def _filas_inventario(db: Session, tipo_recurso_id: int | None, solo_activos: bool):
    consulta = (
        select(Recurso, TipoRecurso, Espacio)
        .join(TipoRecurso, TipoRecurso.id == Recurso.tipo_recurso_id)
        .outerjoin(Espacio, Espacio.id == Recurso.espacio_id)
    )
    if tipo_recurso_id is not None:
        consulta = consulta.where(Recurso.tipo_recurso_id == tipo_recurso_id)
    if solo_activos:
        consulta = consulta.where(Recurso.activo.is_(True))
    return db.execute(
        consulta.order_by(TipoRecurso.nombre, Recurso.codigo)
    ).all()


def listar_inventario(
    db: Session, tipo_recurso_id: int | None = None, solo_activos: bool = True
) -> list[dict]:
    return [
        _salida_recurso(recurso, tipo, espacio)
        for recurso, tipo, espacio in _filas_inventario(db, tipo_recurso_id, solo_activos)
    ]


def _validar_tipo(db: Session, tipo_recurso_id: int) -> TipoRecurso:
    tipo = db.get(TipoRecurso, tipo_recurso_id)
    if tipo is None:
        raise ErrorRecurso(404, "El tipo de recurso no existe")
    return tipo


def _validar_espacio(db: Session, espacio_id: int | None) -> Espacio | None:
    if espacio_id is None:
        return None
    espacio = db.get(Espacio, espacio_id)
    if espacio is None:
        raise ErrorRecurso(404, "El espacio indicado no existe")
    return espacio


def crear_recurso(db: Session, admin: Usuario, datos: RecursoCrear) -> dict:
    tipo = _validar_tipo(db, datos.tipo_recurso_id)
    espacio = _validar_espacio(db, datos.espacio_id)

    repetido = db.scalar(
        select(Recurso).where(func.lower(Recurso.codigo) == datos.codigo.lower())
    )
    if repetido is not None:
        raise ErrorRecurso(
            409, f"Ya existe una unidad con el identificador «{datos.codigo}»"
        )

    recurso = Recurso(
        tipo_recurso_id=tipo.id,
        codigo=datos.codigo,
        descripcion=datos.descripcion,
        espacio_id=espacio.id if espacio else None,
        actualizado_por=admin.id,
    )
    db.add(recurso)
    db.flush()
    _registrar_cambio(
        db,
        admin,
        f"Alta de la unidad «{recurso.codigo}» ({tipo.nombre}) en estado En funcionamiento",
    )
    db.commit()
    db.refresh(recurso)
    return _salida_recurso(recurso, tipo, espacio)


def actualizar_recurso(
    db: Session, admin: Usuario, recurso_id: int, datos: RecursoActualizar
) -> dict:
    recurso = db.get(Recurso, recurso_id)
    if recurso is None:
        raise ErrorRecurso(404, "La unidad no existe")

    cambios: list[str] = []
    tipo = db.get(TipoRecurso, recurso.tipo_recurso_id)
    if datos.tipo_recurso_id is not None and datos.tipo_recurso_id != recurso.tipo_recurso_id:
        tipo = _validar_tipo(db, datos.tipo_recurso_id)
        cambios.append(f"tipo «{tipo.nombre}»")
        recurso.tipo_recurso_id = tipo.id
    if datos.codigo is not None and datos.codigo.lower() != recurso.codigo.lower():
        repetido = db.scalar(
            select(Recurso).where(
                func.lower(Recurso.codigo) == datos.codigo.lower(),
                Recurso.id != recurso.id,
            )
        )
        if repetido is not None:
            raise ErrorRecurso(
                409, f"Ya existe una unidad con el identificador «{datos.codigo}»"
            )
        cambios.append(f"identificador «{recurso.codigo}» → «{datos.codigo}»")
        recurso.codigo = datos.codigo
    if datos.descripcion is not None:
        recurso.descripcion = datos.descripcion
        cambios.append("descripción actualizada")
    if "espacio_id" in datos.model_fields_set:
        espacio = _validar_espacio(db, datos.espacio_id)
        recurso.espacio_id = espacio.id if espacio else None
        cambios.append(
            f"espacio fijo «{espacio.nombre}»" if espacio else "sin espacio fijo"
        )
    if datos.activo is not None and datos.activo != recurso.activo:
        if not datos.activo:
            _verificar_sin_asignaciones_vivas(db, recurso)
        recurso.activo = datos.activo
        cambios.append("reactivada" if datos.activo else "dada de baja")

    if not cambios:
        espacio = db.get(Espacio, recurso.espacio_id) if recurso.espacio_id else None
        return _salida_recurso(recurso, tipo, espacio)

    recurso.actualizado_por = admin.id
    _registrar_cambio(
        db, admin, f"Cambio en la unidad «{recurso.codigo}»: {', '.join(cambios)}"
    )
    db.commit()
    db.refresh(recurso)
    espacio = db.get(Espacio, recurso.espacio_id) if recurso.espacio_id else None
    return _salida_recurso(recurso, tipo, espacio)


def _verificar_sin_asignaciones_vivas(db: Session, recurso: Recurso) -> None:
    viva = db.scalar(
        select(AsignacionRecurso).where(
            AsignacionRecurso.recurso_id == recurso.id,
            AsignacionRecurso.estado.in_(ESTADOS_VIVOS),
        )
    )
    if viva is not None:
        raise ErrorRecurso(
            409,
            f"La unidad «{recurso.codigo}» tiene una asignación vigente: no se puede dar de baja",
        )


def cambiar_estado_recurso(
    db: Session, admin: Usuario, recurso_id: int, datos: RecursoEstadoIn
) -> dict:
    recurso = db.get(Recurso, recurso_id)
    if recurso is None:
        raise ErrorRecurso(404, "La unidad no existe")
    if not recurso.activo:
        raise ErrorRecurso(409, "La unidad está dada de baja")

    anterior = recurso.estado
    recurso.estado = datos.estado
    recurso.comentario_estado = datos.comentario
    recurso.actualizado_por = admin.id
    _registrar_cambio(
        db,
        admin,
        (
            f"Unidad «{recurso.codigo}»: {anterior.value} → {datos.estado.value}. "
            f"Comentario: {datos.comentario}"
        ),
    )
    db.commit()
    db.refresh(recurso)
    tipo = db.get(TipoRecurso, recurso.tipo_recurso_id)
    espacio = db.get(Espacio, recurso.espacio_id) if recurso.espacio_id else None
    return _salida_recurso(recurso, tipo, espacio)


# --------------------------------------------------------------------------- #
# HU-44: disponibilidad y solicitud
# --------------------------------------------------------------------------- #
def _asignaciones_cruzadas(inicio: datetime, fin: datetime):
    return select(AsignacionRecurso.recurso_id).where(
        AsignacionRecurso.estado.in_(ESTADOS_VIVOS),
        AsignacionRecurso.inicio < fin,
        AsignacionRecurso.fin > inicio,
    )


def _unidades_libres(
    db: Session,
    tipo_recurso_id: int,
    inicio: datetime,
    fin: datetime,
    bloquear: bool = False,
) -> list[Recurso]:
    consulta = (
        select(Recurso)
        .where(
            Recurso.tipo_recurso_id == tipo_recurso_id,
            Recurso.activo.is_(True),
            # Las unidades instaladas como amenidad no se prestan
            Recurso.espacio_id.is_(None),
            Recurso.estado == EstadoRecurso.EN_FUNCIONAMIENTO,
            Recurso.id.not_in(_asignaciones_cruzadas(inicio, fin)),
        )
        .order_by(Recurso.codigo)
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return list(db.scalars(consulta))


def _tipos_activos(db: Session) -> list[TipoRecurso]:
    return list(
        db.scalars(
            select(TipoRecurso)
            .where(TipoRecurso.activo.is_(True))
            .order_by(TipoRecurso.nombre)
        )
    )


def disponibilidad(db: Session, reserva: Reserva) -> dict:
    """Stock por tipo en el horario exacto de la reserva (HU-44, criterio 3)."""
    espacio = db.get(Espacio, reserva.espacio_id)
    conteos = _conteos(db)
    tipos: list[dict] = []
    for tipo in _tipos_activos(db):
        conteo = conteos.get(tipo.id) or dict(CONTEOS_VACIOS)
        ocupadas = db.execute(
            select(AsignacionRecurso.estado, func.count())
            .join(Recurso, Recurso.id == AsignacionRecurso.recurso_id)
            .where(
                Recurso.tipo_recurso_id == tipo.id,
                Recurso.activo.is_(True),
                Recurso.espacio_id.is_(None),
                AsignacionRecurso.estado.in_(ESTADOS_VIVOS),
                AsignacionRecurso.inicio < reserva.fin,
                AsignacionRecurso.fin > reserva.inicio,
            )
            .group_by(AsignacionRecurso.estado)
        ).all()
        por_estado = dict(ocupadas)
        prestados = por_estado.get(EstadoAsignacion.ENTREGADA, 0)
        reservados = por_estado.get(EstadoAsignacion.ASIGNADA, 0)
        tipos.append(
            {
                "tipo_recurso_id": tipo.id,
                "tipo": tipo.nombre,
                "total": conteo["total"],
                "instalados": conteo["instalados"],
                "disponibles": max(
                    0,
                    conteo["total"]
                    - conteo["instalados"]
                    - conteo["fallidos"]
                    - prestados
                    - reservados,
                ),
                "prestados": prestados,
                "reservados": reservados,
                "fallidos": conteo["fallidos"],
            }
        )
    return {
        "reserva_id": reserva.id,
        "espacio": espacio.nombre if espacio else "",
        "inicio": _local(reserva.inicio),
        "fin": _local(reserva.fin),
        "tipos": tipos,
    }


def disponibilidad_para(db: Session, usuario: Usuario, reserva_id: int) -> dict:
    reserva = db.get(Reserva, reserva_id)
    if reserva is None or (usuario.rol != Rol.ADMIN and reserva.usuario_id != usuario.id):
        raise ErrorRecurso(404, "La reserva no existe o no tienes acceso a ella")
    return disponibilidad(db, reserva)


def reservas_elegibles(db: Session, usuario: Usuario) -> list[dict]:
    """Reservas propias ACTIVAS que aún no terminan (HU-44, criterios 1 y 2)."""
    if rol_reserva_de(usuario.cargo) not in ROLES_QUE_PIDEN:
        return []
    ahora = datetime.now(ZONA_COLOMBIA)
    filas = db.execute(
        select(Reserva, Espacio)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .where(
            Reserva.usuario_id == usuario.id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.fin > ahora,
        )
        .order_by(Reserva.inicio)
    ).all()
    return [
        {
            "reserva_id": reserva.id,
            "espacio_id": espacio.id,
            "espacio": espacio.nombre,
            "inicio": _local(reserva.inicio),
            "fin": _local(reserva.fin),
        }
        for reserva, espacio in filas
    ]


def _notificar_admins(db: Session, titulo: str, mensaje: str, solicitud_id: int | None) -> None:
    for admin in _admins(db):
        notificaciones.crear(
            db,
            usuario_id=admin.id,
            tipo=TipoNotificacion.RECURSO_SOLICITADO,
            titulo=titulo,
            mensaje=mensaje,
            solicitud_id=solicitud_id,
        )


def crear_solicitud(db: Session, usuario: Usuario, datos: SolicitudRecursoCrear) -> dict:
    if rol_reserva_de(usuario.cargo) not in ROLES_QUE_PIDEN:
        raise ErrorRecurso(
            403,
            "Solo Docente, Coordinador o Director pueden solicitar recursos adicionales",
        )
    if sanciones.esta_bloqueado(db, usuario):
        raise ErrorRecurso(409, sanciones.mensaje_bloqueo(db, usuario))

    reserva = db.scalar(
        select(Reserva).where(Reserva.id == datos.reserva_id).with_for_update()
    )
    if reserva is None or reserva.usuario_id != usuario.id:
        raise ErrorRecurso(404, "La reserva no existe o no tienes acceso a ella")
    if reserva.estado != EstadoReserva.ACTIVA:
        raise ErrorRecurso(409, "La reserva no está confirmada: no se pueden pedir recursos")
    if reserva.fin <= datetime.now(ZONA_COLOMBIA):
        raise ErrorRecurso(409, "La reserva ya terminó: no se pueden pedir recursos")

    vigente = db.scalar(
        select(SolicitudRecurso).where(
            SolicitudRecurso.reserva_id == reserva.id,
            SolicitudRecurso.estado.in_(ESTADOS_VIGENTES_SOLICITUD),
        )
    )
    if vigente is not None:
        raise ErrorRecurso(
            409,
            f"La reserva ya tiene la solicitud de recursos #{vigente.id} vigente",
        )

    espacio = db.get(Espacio, reserva.espacio_id)
    solicitud = SolicitudRecurso(
        reserva_id=reserva.id,
        solicitante_id=usuario.id,
        observacion=(datos.observacion or "").strip() or None,
    )
    db.add(solicitud)
    db.flush()

    nombres: list[str] = []
    for linea in datos.detalle:
        tipo = _validar_tipo(db, linea.tipo_recurso_id)
        if not tipo.activo:
            raise ErrorRecurso(409, f"El tipo de recurso «{tipo.nombre}» está desactivado")
        libres = _unidades_libres(db, tipo.id, reserva.inicio, reserva.fin)
        if linea.cantidad > len(libres):
            raise ErrorRecurso(
                422,
                (
                    f"Solo hay {len(libres)} unidad(es) de «{tipo.nombre}» disponibles "
                    f"en el horario de la reserva y pediste {linea.cantidad}"
                ),
            )
        db.add(
            DetalleSolicitudRecurso(
                solicitud_recurso_id=solicitud.id,
                tipo_recurso_id=tipo.id,
                cantidad=linea.cantidad,
            )
        )
        nombres.append(f"{linea.cantidad} × {tipo.nombre}")

    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.RECURSO_SOLICITADO,
        detalle=(
            f"Solicitud de recursos #{solicitud.id} para {espacio.nombre if espacio else ''}: "
            f"{', '.join(nombres)}"
        ),
    )
    _notificar_admins(
        db,
        "Solicitud de recursos pendiente",
        (
            f"{usuario.nombre} pidió {', '.join(nombres)} para "
            f"{espacio.nombre if espacio else 'una reserva'} "
            f"el {reserva.inicio.astimezone(ZONA_COLOMBIA):%d/%m %H:%M}. "
            "Revísala en Admin → Recursos."
        ),
        reserva.solicitud_id,
    )
    db.commit()
    db.refresh(solicitud)
    return _salida_solicitud(db, solicitud)


def _salida_solicitud(db: Session, solicitud: SolicitudRecurso) -> dict:
    reserva = db.get(Reserva, solicitud.reserva_id)
    espacio = db.get(Espacio, reserva.espacio_id) if reserva else None
    solicitante = db.get(Usuario, solicitud.solicitante_id)
    decisor = db.get(Usuario, solicitud.decidido_por) if solicitud.decidido_por else None

    detalles = db.execute(
        select(DetalleSolicitudRecurso, TipoRecurso)
        .join(TipoRecurso, TipoRecurso.id == DetalleSolicitudRecurso.tipo_recurso_id)
        .where(DetalleSolicitudRecurso.solicitud_recurso_id == solicitud.id)
        .order_by(TipoRecurso.nombre)
    ).all()
    asignaciones = db.execute(
        select(AsignacionRecurso, Recurso, TipoRecurso)
        .join(Recurso, Recurso.id == AsignacionRecurso.recurso_id)
        .join(TipoRecurso, TipoRecurso.id == Recurso.tipo_recurso_id)
        .where(AsignacionRecurso.solicitud_recurso_id == solicitud.id)
        .order_by(Recurso.codigo)
    ).all()

    asignados_por_tipo: dict[int, int] = {}
    for asignacion, recurso, _ in asignaciones:
        if asignacion.estado in ESTADOS_VIVOS:
            asignados_por_tipo[recurso.tipo_recurso_id] = (
                asignados_por_tipo.get(recurso.tipo_recurso_id, 0) + 1
            )

    return {
        "id": solicitud.id,
        "reserva_id": solicitud.reserva_id,
        "espacio_id": reserva.espacio_id if reserva else 0,
        "espacio": espacio.nombre if espacio else "",
        "inicio": _local(reserva.inicio) if reserva else None,
        "fin": _local(reserva.fin) if reserva else None,
        "solicitante_id": solicitud.solicitante_id,
        "solicitante": solicitante.nombre if solicitante else "",
        "estado": solicitud.estado.value,
        "observacion": solicitud.observacion,
        "motivo_rechazo": solicitud.motivo_rechazo,
        "creada_en": _local(solicitud.creada_en),
        "decidida_por": decisor.nombre if decisor else None,
        "fecha_decision": _local(solicitud.fecha_decision),
        "detalle": [
            {
                "tipo_recurso_id": tipo.id,
                "tipo": tipo.nombre,
                "cantidad": detalle.cantidad,
                "asignados": asignados_por_tipo.get(tipo.id, 0),
            }
            for detalle, tipo in detalles
        ],
        "asignaciones": [
            {
                "id": asignacion.id,
                "recurso_id": recurso.id,
                "codigo": recurso.codigo,
                "tipo": tipo.nombre,
                "estado": asignacion.estado.value,
                "entregada_en": _local(asignacion.entregada_en),
                "devuelta_en": _local(asignacion.devuelta_en),
                "estado_devolucion": asignacion.estado_devolucion,
                "comentario_devolucion": asignacion.comentario_devolucion,
                "strikes_generados": asignacion.strikes_generados,
            }
            for asignacion, recurso, tipo in asignaciones
        ],
    }


def listar_solicitudes(
    db: Session,
    estado: EstadoSolicitudRecurso | None = None,
    usuario_id: int | None = None,
) -> list[dict]:
    consulta = select(SolicitudRecurso)
    if estado is not None:
        consulta = consulta.where(SolicitudRecurso.estado == estado)
    if usuario_id is not None:
        consulta = consulta.where(SolicitudRecurso.solicitante_id == usuario_id)
    solicitudes = list(
        db.scalars(
            consulta.order_by(SolicitudRecurso.creada_en, SolicitudRecurso.id)
        )
    )
    return [_salida_solicitud(db, solicitud) for solicitud in solicitudes]


# --------------------------------------------------------------------------- #
# HU-45: aprobación y asignación
# --------------------------------------------------------------------------- #
def _notificar_solicitante(
    db: Session,
    solicitud: SolicitudRecurso,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
) -> None:
    reserva = db.get(Reserva, solicitud.reserva_id)
    notificaciones.crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        solicitud_id=reserva.solicitud_id if reserva else None,
    )


def decidir_solicitud(
    db: Session,
    admin: Usuario,
    solicitud_id: int,
    datos: DecisionSolicitudRecursoIn,
) -> dict:
    solicitud = db.scalar(
        select(SolicitudRecurso)
        .where(SolicitudRecurso.id == solicitud_id)
        .with_for_update()
    )
    if solicitud is None:
        raise ErrorRecurso(404, "La solicitud de recursos no existe")
    if solicitud.estado != EstadoSolicitudRecurso.PENDIENTE:
        raise ErrorRecurso(409, "Esta solicitud de recursos ya fue decidida")

    reserva = db.get(Reserva, solicitud.reserva_id)
    if reserva is None:
        raise ErrorRecurso(409, "La reserva asociada a la solicitud no existe")
    espacio = db.get(Espacio, reserva.espacio_id)

    if not datos.aprobar:
        motivo = (datos.motivo or "").strip()
        solicitud.estado = EstadoSolicitudRecurso.RECHAZADA
        solicitud.motivo_rechazo = motivo
        solicitud.decidido_por = admin.id
        solicitud.fecha_decision = datetime.now(ZONA_COLOMBIA)
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=admin.id,
            accion=AccionTrazabilidad.RECURSO_RECHAZADO,
            estado_anterior=EstadoSolicitudRecurso.PENDIENTE.value,
            estado_nuevo=EstadoSolicitudRecurso.RECHAZADA.value,
            detalle=f"Solicitud de recursos #{solicitud.id} rechazada. Motivo: {motivo}",
        )
        _notificar_solicitante(
            db,
            solicitud,
            TipoNotificacion.RECURSO_RECHAZADO,
            "Solicitud de recursos rechazada",
            (
                f"El administrador rechazó tu solicitud de recursos para "
                f"{espacio.nombre if espacio else 'tu reserva'}. Motivo: {motivo}"
            ),
        )
        db.commit()
        db.refresh(solicitud)
        return _salida_solicitud(db, solicitud)

    # HU-45, criterio 3: la reserva debe estar confirmada
    if reserva.estado != EstadoReserva.ACTIVA:
        raise ErrorRecurso(
            409, "La reserva asociada ya no está confirmada: no se puede aprobar la solicitud"
        )

    detalles = list(
        db.scalars(
            select(DetalleSolicitudRecurso)
            .where(DetalleSolicitudRecurso.solicitud_recurso_id == solicitud.id)
            .order_by(DetalleSolicitudRecurso.tipo_recurso_id)
        )
    )
    if not detalles:
        raise ErrorRecurso(409, "La solicitud no tiene recursos que asignar")

    asignadas: list[AsignacionRecurso] = []
    for detalle in detalles:
        tipo = db.get(TipoRecurso, detalle.tipo_recurso_id)
        libres = _unidades_libres(
            db, detalle.tipo_recurso_id, reserva.inicio, reserva.fin, bloquear=True
        )
        if len(libres) < detalle.cantidad:
            raise ErrorRecurso(
                409,
                (
                    f"No hay stock suficiente de «{tipo.nombre if tipo else 'recurso'}» "
                    f"en el horario de la reserva: se necesitan {detalle.cantidad} y hay "
                    f"{len(libres)} disponible(s) en funcionamiento"
                ),
            )
        for recurso in libres[: detalle.cantidad]:
            asignacion = AsignacionRecurso(
                solicitud_recurso_id=solicitud.id,
                recurso_id=recurso.id,
                inicio=reserva.inicio,
                fin=reserva.fin,
            )
            db.add(asignacion)
            asignadas.append(asignacion)

    try:
        db.flush()
    except IntegrityError as error:
        if "ex_asignacion_sin_cruce" in str(error.orig):
            raise ErrorRecurso(
                409, "Otra aprobación tomó esas unidades en el mismo horario: reintenta"
            ) from error
        raise

    solicitud.estado = EstadoSolicitudRecurso.APROBADA
    solicitud.decidido_por = admin.id
    solicitud.fecha_decision = datetime.now(ZONA_COLOMBIA)
    solicitud.motivo_rechazo = None

    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=admin.id,
        accion=AccionTrazabilidad.RECURSO_APROBADO,
        estado_anterior=EstadoSolicitudRecurso.PENDIENTE.value,
        estado_nuevo=EstadoSolicitudRecurso.APROBADA.value,
        detalle=f"Solicitud de recursos #{solicitud.id} aprobada ({len(asignadas)} unidad(es))",
    )
    for asignacion in asignadas:
        recurso = db.get(Recurso, asignacion.recurso_id)
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=admin.id,
            accion=AccionTrazabilidad.RECURSO_ASIGNADO,
            detalle=(
                f"Unidad «{recurso.codigo}» asignada a la solicitud #{solicitud.id} "
                f"para {espacio.nombre if espacio else 'la reserva'}"
            ),
        )
    _notificar_solicitante(
        db,
        solicitud,
        TipoNotificacion.RECURSO_APROBADO,
        "Solicitud de recursos aprobada",
        (
            f"El administrador aprobó tu solicitud de recursos #{solicitud.id} para "
            f"{espacio.nombre if espacio else 'tu reserva'}. "
            f"Unidades asignadas: {', '.join(db.get(Recurso, a.recurso_id).codigo for a in asignadas)}. "
            "Recógelas en el laboratorio y devuélvelas al finalizar la reserva."
        ),
    )
    db.commit()
    db.refresh(solicitud)
    return _salida_solicitud(db, solicitud)


# --------------------------------------------------------------------------- #
# HU-46: entrega, devolución y penalización
# --------------------------------------------------------------------------- #
def _asignacion_bloqueada(db: Session, asignacion_id: int) -> AsignacionRecurso:
    asignacion = db.scalar(
        select(AsignacionRecurso)
        .where(AsignacionRecurso.id == asignacion_id)
        .with_for_update()
    )
    if asignacion is None:
        raise ErrorRecurso(404, "La asignación de recurso no existe")
    return asignacion


def registrar_entrega(db: Session, admin: Usuario, asignacion_id: int) -> dict:
    asignacion = _asignacion_bloqueada(db, asignacion_id)
    solicitud = db.get(SolicitudRecurso, asignacion.solicitud_recurso_id)
    if solicitud is None:
        raise ErrorRecurso(409, "La solicitud de recursos asociada no existe")
    if asignacion.estado == EstadoAsignacion.ENTREGADA:
        return _salida_solicitud(db, solicitud)
    if asignacion.estado != EstadoAsignacion.ASIGNADA:
        raise ErrorRecurso(409, "Solo se puede entregar una unidad asignada y pendiente")

    reserva = db.get(Reserva, solicitud.reserva_id)
    recurso = db.get(Recurso, asignacion.recurso_id)
    ahora = datetime.now(ZONA_COLOMBIA)
    asignacion.estado = EstadoAsignacion.ENTREGADA
    asignacion.entregada_en = ahora
    asignacion.entregada_por = admin.id

    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=admin.id,
        accion=AccionTrazabilidad.RECURSO_ENTREGADO,
        detalle=(
            f"Unidad «{recurso.codigo}» entregada a "
            f"{db.get(Usuario, solicitud.solicitante_id).nombre} "
            f"a las {ahora:%H:%M}; devolución límite "
            f"{reserva.fin.astimezone(ZONA_COLOMBIA):%d/%m %H:%M}"
        ),
    )
    db.commit()
    db.refresh(solicitud)
    return _salida_solicitud(db, solicitud)


def registrar_devolucion(
    db: Session, admin: Usuario, asignacion_id: int, datos: DevolucionIn
) -> dict:
    # Primero se ponen al día los retrasos: una devolución tardía ya genera strikes
    procesar_retrasos(db)

    asignacion = _asignacion_bloqueada(db, asignacion_id)
    solicitud = db.get(SolicitudRecurso, asignacion.solicitud_recurso_id)
    if solicitud is None:
        raise ErrorRecurso(409, "La solicitud de recursos asociada no existe")
    if asignacion.estado == EstadoAsignacion.DEVUELTA:
        return _salida_solicitud(db, solicitud)
    if asignacion.estado not in (EstadoAsignacion.ASIGNADA, EstadoAsignacion.ENTREGADA):
        raise ErrorRecurso(409, "Esta unidad ya no está en préstamo")

    reserva = db.get(Reserva, solicitud.reserva_id)
    recurso = db.get(Recurso, asignacion.recurso_id)
    ahora = datetime.now(ZONA_COLOMBIA)
    asignacion.estado = EstadoAsignacion.DEVUELTA
    asignacion.devuelta_en = ahora
    asignacion.devuelta_por = admin.id
    asignacion.estado_devolucion = datos.estado
    asignacion.comentario_devolucion = (datos.comentario or "").strip() or None

    recurso.estado = datos.estado
    recurso.comentario_estado = asignacion.comentario_devolucion
    recurso.actualizado_por = admin.id

    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=admin.id,
        accion=AccionTrazabilidad.RECURSO_DEVUELTO,
        detalle=(
            f"Unidad «{recurso.codigo}» devuelta en estado {datos.estado.value}"
            + (f". Comentario: {asignacion.comentario_devolucion}" if asignacion.comentario_devolucion else "")
        ),
    )
    _registrar_cambio(
        db,
        admin,
        f"Devolución de «{recurso.codigo}» en estado {datos.estado.value}",
    )

    if _todas_devueltas(db, solicitud.id):
        solicitud.estado = EstadoSolicitudRecurso.DEVUELTA

    db.commit()
    db.refresh(solicitud)
    return _salida_solicitud(db, solicitud)


def _todas_devueltas(db: Session, solicitud_id: int) -> bool:
    vivas = db.scalar(
        select(func.count())
        .select_from(AsignacionRecurso)
        .where(
            AsignacionRecurso.solicitud_recurso_id == solicitud_id,
            AsignacionRecurso.estado.in_(ESTADOS_VIVOS),
        )
    )
    return (vivas or 0) == 0


def procesar_retrasos(db: Session, ahora: datetime | None = None) -> dict:
    """Notifica y penaliza las devoluciones vencidas (HU-46, criterios 5 y 6).

    La penalización es el doble de los strikes de un espacio: por cada bloque de
    `minutos_por_strike` de retraso se generan 2 strikes. `strikes_generados`
    guarda lo ya aplicado para no duplicar cargos entre barridos.
    """
    ahora = ahora or datetime.now(ZONA_COLOMBIA)
    parametros = sanciones.obtener_parametros(db)
    bloque = parametros.minutos_por_strike

    vencidas = list(
        db.scalars(
            select(AsignacionRecurso)
            .where(
                AsignacionRecurso.estado == EstadoAsignacion.ENTREGADA,
                AsignacionRecurso.fin < ahora,
            )
            .with_for_update()
        )
    )

    notificados = 0
    strikes_creados = 0
    for asignacion in vencidas:
        retraso = int((ahora - asignacion.fin).total_seconds() // 60)
        bloques = retraso // bloque
        objetivo = 2 * bloques
        nuevos = objetivo - asignacion.strikes_generados
        if nuevos <= 0:
            continue

        solicitud = db.get(SolicitudRecurso, asignacion.solicitud_recurso_id)
        if solicitud is None:
            continue
        reserva = db.get(Reserva, solicitud.reserva_id)
        recurso = db.get(Recurso, asignacion.recurso_id)
        if reserva is None or recurso is None:
            continue

        for _ in range(nuevos):
            strike = Strike(
                usuario_id=reserva.usuario_id,
                reserva_id=reserva.id,
                minutos_retraso=retraso,
            )
            db.add(strike)
            db.flush()
            strikes_creados += 1
            trazabilidad.registrar(
                db,
                solicitud_id=reserva.solicitud_id,
                reserva_id=reserva.id,
                usuario_id=reserva.usuario_id,
                accion=AccionTrazabilidad.STRIKE_ASIGNADO,
                detalle=(
                    f"Strike #{strike.id} por devolución tardía de «{recurso.codigo}» "
                    f"({retraso} min de retraso, doble penalización)"
                ),
            )

        asignacion.strikes_generados = objetivo
        asignacion.penalizada = True
        notificados += 1

        total = sanciones.contar_strikes(db, reserva.usuario_id)
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=reserva.usuario_id,
            accion=AccionTrazabilidad.RECURSO_PENALIZADO,
            detalle=(
                f"Devolución tardía de «{recurso.codigo}»: {retraso} minutos de retraso, "
                f"{nuevos} strike(s) nuevos (total {total})"
            ),
        )
        notificaciones.crear(
            db,
            usuario_id=reserva.usuario_id,
            tipo=TipoNotificacion.RECURSO_DEVOLUCION_TARDIA,
            titulo="Devolución tardía de recursos",
            mensaje=(
                f"La unidad «{recurso.codigo}» debía devolverse a las "
                f"{asignacion.fin.astimezone(ZONA_COLOMBIA):%d/%m %H:%M} y sigue sin "
                f"registrarse su devolución. Se generaron {nuevos} strike(s) por el retraso "
                f"(doble penalización). Acumulas {total} de {parametros.max_strikes} permitidos."
            ),
            solicitud_id=reserva.solicitud_id,
        )

        if total >= parametros.max_strikes:
            notificaciones.crear(
                db,
                usuario_id=reserva.usuario_id,
                tipo=TipoNotificacion.BLOQUEO_SOLICITUDES,
                titulo="Solicitudes bloqueadas",
                mensaje=(
                    f"Alcanzaste {total} strikes de {parametros.max_strikes} permitidos: "
                    "no podrás crear nuevas solicitudes. Puedes pedir tu reactivación en "
                    "Configuración → Mi sanción."
                ),
                solicitud_id=reserva.solicitud_id,
            )

    if notificados or strikes_creados:
        db.commit()
    return {"notificados": notificados, "strikes": strikes_creados}


# --------------------------------------------------------------------------- #
# HU-46: préstamos e historial
# --------------------------------------------------------------------------- #
def _salida_historial(
    asignacion: AsignacionRecurso,
    solicitud: SolicitudRecurso,
    usuario: Usuario,
    recurso: Recurso,
    tipo: TipoRecurso,
) -> dict:
    return {
        "id": asignacion.id,
        "solicitud_recurso_id": asignacion.solicitud_recurso_id,
        "reserva_id": solicitud.reserva_id,
        "recurso_id": recurso.id,
        "codigo": recurso.codigo,
        "tipo": tipo.nombre,
        "solicitante": usuario.nombre if usuario else "",
        "inicio": _local(asignacion.inicio),
        "fin": _local(asignacion.fin),
        "estado": asignacion.estado.value,
        "entregada_en": _local(asignacion.entregada_en),
        "devuelta_en": _local(asignacion.devuelta_en),
        "estado_devolucion": asignacion.estado_devolucion,
        "comentario_devolucion": asignacion.comentario_devolucion,
        "strikes_generados": asignacion.strikes_generados,
    }


def listar_asignaciones(
    db: Session,
    estado: EstadoAsignacion | None = None,
    solo_vigentes: bool = False,
) -> list[dict]:
    consulta = (
        select(AsignacionRecurso, SolicitudRecurso, Usuario, Recurso, TipoRecurso)
        .join(SolicitudRecurso, SolicitudRecurso.id == AsignacionRecurso.solicitud_recurso_id)
        .join(Usuario, Usuario.id == SolicitudRecurso.solicitante_id)
        .join(Recurso, Recurso.id == AsignacionRecurso.recurso_id)
        .join(TipoRecurso, TipoRecurso.id == Recurso.tipo_recurso_id)
    )
    if estado is not None:
        consulta = consulta.where(AsignacionRecurso.estado == estado)
    if solo_vigentes:
        consulta = consulta.where(AsignacionRecurso.estado.in_(ESTADOS_VIVOS))
    filas = db.execute(consulta.order_by(AsignacionRecurso.inicio, AsignacionRecurso.id)).all()
    return [
        _salida_historial(asignacion, solicitud, usuario, recurso, tipo)
        for asignacion, solicitud, usuario, recurso, tipo in filas
    ]


def historial_recurso(db: Session, recurso_id: int) -> list[dict]:
    if db.get(Recurso, recurso_id) is None:
        raise ErrorRecurso(404, "La unidad no existe")
    filas = db.execute(
        select(AsignacionRecurso, SolicitudRecurso, Usuario, Recurso, TipoRecurso)
        .join(SolicitudRecurso, SolicitudRecurso.id == AsignacionRecurso.solicitud_recurso_id)
        .join(Usuario, Usuario.id == SolicitudRecurso.solicitante_id)
        .join(Recurso, Recurso.id == AsignacionRecurso.recurso_id)
        .join(TipoRecurso, TipoRecurso.id == Recurso.tipo_recurso_id)
        .where(AsignacionRecurso.recurso_id == recurso_id)
        .order_by(AsignacionRecurso.inicio.desc(), AsignacionRecurso.id.desc())
    ).all()
    return [
        _salida_historial(asignacion, solicitud, usuario, recurso, tipo)
        for asignacion, solicitud, usuario, recurso, tipo in filas
    ]


# --------------------------------------------------------------------------- #
# Cancelación en cascada (HU-44, criterio 7)
# --------------------------------------------------------------------------- #
def cancelar_por_reserva(db: Session, reserva_id: int, motivo: str) -> int:
    """Cancela las solicitudes de recursos de una reserva cancelada, cedida o no-show.

    Libera las unidades aprobadas que aún no se habían entregado. Si alguna
    unidad ya está entregada, la solicitud se conserva para registrar la
    devolución. No hace commit: lo hace quien llama.
    """
    solicitudes = list(
        db.scalars(
            select(SolicitudRecurso)
            .where(
                SolicitudRecurso.reserva_id == reserva_id,
                SolicitudRecurso.estado.in_(ESTADOS_VIGENTES_SOLICITUD),
            )
            .with_for_update()
        )
    )
    if not solicitudes:
        return 0

    reserva = db.get(Reserva, reserva_id)
    canceladas = 0
    for solicitud in solicitudes:
        asignaciones = list(
            db.scalars(
                select(AsignacionRecurso)
                .where(AsignacionRecurso.solicitud_recurso_id == solicitud.id)
                .with_for_update()
            )
        )
        entregadas = [
            a for a in asignaciones if a.estado == EstadoAsignacion.ENTREGADA
        ]

        for asignacion in asignaciones:
            if asignacion.estado == EstadoAsignacion.ASIGNADA:
                asignacion.estado = EstadoAsignacion.CANCELADA

        if entregadas:
            # Hay unidades ya entregadas: la solicitud sigue abierta para registrar su devolución
            continue

        anterior = solicitud.estado.value
        solicitud.estado = EstadoSolicitudRecurso.CANCELADA
        solicitud.motivo_rechazo = motivo
        canceladas += 1

        if reserva is not None:
            trazabilidad.registrar(
                db,
                solicitud_id=reserva.solicitud_id,
                reserva_id=reserva.id,
                usuario_id=solicitud.solicitante_id,
                accion=AccionTrazabilidad.RECURSO_CANCELADO,
                estado_anterior=anterior,
                estado_nuevo=EstadoSolicitudRecurso.CANCELADA.value,
                detalle=f"Solicitud de recursos #{solicitud.id} cancelada. Motivo: {motivo}",
            )
            notificaciones.crear(
                db,
                usuario_id=solicitud.solicitante_id,
                tipo=TipoNotificacion.RECURSO_CANCELADO,
                titulo="Solicitud de recursos cancelada",
                mensaje=(
                    f"Tu solicitud de recursos #{solicitud.id} se canceló automáticamente. "
                    f"Motivo: {motivo}"
                ),
                solicitud_id=reserva.solicitud_id,
            )
    return canceladas
