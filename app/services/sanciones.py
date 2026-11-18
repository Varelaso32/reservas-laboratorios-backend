"""Strikes, sanciones y reactivaciones (HU-40, HU-41 y HU-42).

Un strike se crea cuando vence la tolerancia de una reserva sin asistencia
(HU-39). Al llegar al máximo configurado el usuario queda bloqueado: puede
consultar todo, pero no crear solicitudes nuevas. La reactivación la decide el
Administrador del Sistema.

No hace commit salvo en las operaciones que lo indican explícitamente.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    AccionTrazabilidad,
    EstadoReactivacion,
    Rol,
    TipoNotificacion,
)
from app.models.modelos import (
    Espacio,
    ParametroSancion,
    Reactivacion,
    RegistroConfiguracion,
    Reserva,
    Strike,
    Usuario,
)
from app.schemas.sancion import (
    ParametroSancionActualizar,
    ReactivacionCrear,
    ReactivacionDecision,
)
from app.services import notificaciones, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA

ACCIONES_DEFECTO = [
    {"nivel": 1, "accion": "ADVERTENCIA"},
    {"nivel": 2, "accion": "ADVERTENCIA"},
    {"nivel": 3, "accion": "BLOQUEO"},
]

SIN_REACTIVACION_PENDIENTE = "Ya tienes una solicitud de reactivación pendiente"


class ErrorSancion(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


# --------------------------------------------------------------------------- #
# Parámetros (HU-41)
# --------------------------------------------------------------------------- #
def obtener_parametros(db: Session) -> ParametroSancion:
    """Fila única de la política; se crea con los valores iniciales si no existe."""
    parametros = db.get(ParametroSancion, 1)
    if parametros is None:
        parametros = ParametroSancion(id=1, acciones=ACCIONES_DEFECTO)
        db.add(parametros)
        db.flush()
    return parametros


def _salida_parametros(parametros: ParametroSancion) -> dict:
    return {
        "tolerancia_minutos": parametros.tolerancia_minutos,
        "aviso_minutos": parametros.aviso_minutos,
        "minutos_por_strike": parametros.minutos_por_strike,
        "max_strikes": parametros.max_strikes,
        "acciones": parametros.acciones,
        "actualizado_en": _local(parametros.actualizado_en),
    }


def consultar_parametros(db: Session) -> dict:
    return _salida_parametros(obtener_parametros(db))


def actualizar_parametros(
    db: Session, admin: Usuario, datos: ParametroSancionActualizar
) -> dict:
    niveles = [accion.nivel for accion in datos.acciones]
    if len(niveles) != len(set(niveles)):
        raise ErrorSancion(422, "No se puede repetir el nivel de strikes en las acciones")
    if any(nivel > datos.max_strikes for nivel in niveles):
        raise ErrorSancion(422, "Ningún nivel de acción puede superar el máximo de strikes")

    parametros = obtener_parametros(db)
    parametros.tolerancia_minutos = datos.tolerancia_minutos
    parametros.aviso_minutos = datos.aviso_minutos
    parametros.minutos_por_strike = datos.minutos_por_strike
    parametros.max_strikes = datos.max_strikes
    parametros.acciones = [accion.model_dump() for accion in datos.acciones]
    parametros.actualizado_por = admin.id

    db.add(
        RegistroConfiguracion(
            usuario_id=admin.id,
            entidad="SANCIONES",
            detalle=(
                "Política de sanciones: "
                f"tolerancia {datos.tolerancia_minutos} min, "
                f"aviso {datos.aviso_minutos} min, "
                f"{datos.minutos_por_strike} min por strike, "
                f"máximo {datos.max_strikes} strikes"
            ),
        )
    )
    db.commit()
    db.refresh(parametros)
    return _salida_parametros(parametros)


# --------------------------------------------------------------------------- #
# Strikes y bloqueo (HU-40)
# --------------------------------------------------------------------------- #
def contar_strikes(db: Session, usuario_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Strike)
            .where(Strike.usuario_id == usuario_id, Strike.anulado.is_(False))
        )
        or 0
    )


def esta_bloqueado(db: Session, usuario: Usuario) -> bool:
    parametros = obtener_parametros(db)
    return contar_strikes(db, usuario.id) >= parametros.max_strikes


def mensaje_bloqueo(db: Session, usuario: Usuario) -> str:
    parametros = obtener_parametros(db)
    strikes = contar_strikes(db, usuario.id)
    return (
        f"Tienes {strikes} strikes activos de {parametros.max_strikes} permitidos: "
        "no puedes crear nuevas solicitudes. Puedes pedir tu reactivación en "
        "Configuración → Mi sanción."
    )


def _strikes_out(
    filas: list[tuple[Strike, Reserva, Espacio]]
) -> list[dict]:
    return [
        {
            "id": strike.id,
            "reserva_id": strike.reserva_id,
            "espacio": espacio.nombre,
            "inicio": _local(reserva.inicio),
            "minutos_retraso": strike.minutos_retraso,
            "anulado": strike.anulado,
            "motivo_anulacion": strike.motivo_anulacion,
            "creada_en": _local(strike.creada_en),
        }
        for strike, reserva, espacio in filas
    ]


def _filas_strikes(db: Session, usuario_id: int | None = None):
    consulta = (
        select(Strike, Reserva, Espacio)
        .join(Reserva, Reserva.id == Strike.reserva_id)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
    )
    if usuario_id is not None:
        consulta = consulta.where(Strike.usuario_id == usuario_id)
    return db.execute(
        consulta.order_by(Strike.creada_en.desc(), Strike.id.desc())
    ).all()


def _reactivacion_out(db: Session, reactivacion: Reactivacion) -> dict:
    usuario = db.get(Usuario, reactivacion.usuario_id)
    decisor = db.get(Usuario, reactivacion.decidida_por) if reactivacion.decidida_por else None
    return {
        "id": reactivacion.id,
        "usuario_id": reactivacion.usuario_id,
        "usuario": usuario.nombre if usuario else "",
        "estado": reactivacion.estado,
        "justificacion": reactivacion.justificacion,
        "detalle": reactivacion.detalle or [],
        "strikes_anulados": reactivacion.strikes_anulados,
        "creada_en": _local(reactivacion.creada_en),
        "decidida_por": decisor.nombre if decisor else None,
        "fecha_decision": _local(reactivacion.fecha_decision),
        "motivo_rechazo": reactivacion.motivo_rechazo,
    }


def reactivacion_vigente(db: Session, usuario_id: int) -> Reactivacion | None:
    """La pendiente si existe; si no, la última que se decidió."""
    pendiente = db.scalar(
        select(Reactivacion)
        .where(
            Reactivacion.usuario_id == usuario_id,
            Reactivacion.estado == EstadoReactivacion.PENDIENTE,
        )
        .order_by(Reactivacion.creada_en.desc())
        .limit(1)
    )
    if pendiente is not None:
        return pendiente
    return db.scalar(
        select(Reactivacion)
        .where(Reactivacion.usuario_id == usuario_id)
        .order_by(Reactivacion.creada_en.desc(), Reactivacion.id.desc())
        .limit(1)
    )


def estado_usuario(db: Session, usuario: Usuario) -> dict:
    parametros = obtener_parametros(db)
    strikes = contar_strikes(db, usuario.id)
    reactivacion = reactivacion_vigente(db, usuario.id)
    return {
        "bloqueado": strikes >= parametros.max_strikes,
        "strikes_activos": strikes,
        "max_strikes": parametros.max_strikes,
        "tolerancia_minutos": parametros.tolerancia_minutos,
        "aviso_minutos": parametros.aviso_minutos,
        "strikes": _strikes_out(_filas_strikes(db, usuario.id)),
        "reactivacion": _reactivacion_out(db, reactivacion) if reactivacion else None,
    }


# --------------------------------------------------------------------------- #
# Reporte de sancionados (HU-42)
# --------------------------------------------------------------------------- #
def reporte(db: Session, solo_bloqueados: bool = False) -> dict:
    parametros = obtener_parametros(db)
    filas = _filas_strikes(db)

    por_usuario: dict[int, list[tuple[Strike, Reserva, Espacio]]] = {}
    for fila in filas:
        por_usuario.setdefault(fila[0].usuario_id, []).append(fila)

    usuarios: list[dict] = []
    for usuario_id, filas_usuario in por_usuario.items():
        usuario = db.get(Usuario, usuario_id)
        if usuario is None:
            continue
        activos = sum(1 for strike, _, _ in filas_usuario if not strike.anulado)
        bloqueado = activos >= parametros.max_strikes
        if solo_bloqueados and not bloqueado:
            continue
        reactivacion = reactivacion_vigente(db, usuario_id)
        usuarios.append(
            {
                "usuario_id": usuario.id,
                "nombre": usuario.nombre,
                "email": usuario.email,
                "rol": usuario.rol.value,
                "cargo": usuario.cargo.value if usuario.cargo else None,
                "strikes_activos": activos,
                "bloqueado": bloqueado,
                "strikes": _strikes_out(filas_usuario),
                "reactivacion": _reactivacion_out(db, reactivacion) if reactivacion else None,
            }
        )

    usuarios.sort(key=lambda item: (-item["strikes_activos"], item["nombre"].lower()))
    pendientes = db.execute(
        select(Reactivacion)
        .where(Reactivacion.estado == EstadoReactivacion.PENDIENTE)
        .order_by(Reactivacion.creada_en)
    ).scalars()

    return {
        "total_usuarios": len(usuarios),
        "total_bloqueados": sum(1 for item in usuarios if item["bloqueado"]),
        "usuarios": usuarios,
        "reactivaciones_pendientes": [_reactivacion_out(db, item) for item in pendientes],
    }


# --------------------------------------------------------------------------- #
# Reactivación (HU-42)
# --------------------------------------------------------------------------- #
def _admins(db: Session) -> list[Usuario]:
    return list(db.scalars(select(Usuario).where(Usuario.rol == Rol.ADMIN, Usuario.activo.is_(True))))


def crear_reactivacion(db: Session, usuario: Usuario, datos: ReactivacionCrear) -> dict:
    if not esta_bloqueado(db, usuario):
        raise ErrorSancion(409, "No estás bloqueado: no necesitas reactivación")

    pendiente = db.scalar(
        select(Reactivacion).where(
            Reactivacion.usuario_id == usuario.id,
            Reactivacion.estado == EstadoReactivacion.PENDIENTE,
        )
    )
    if pendiente is not None:
        raise ErrorSancion(409, SIN_REACTIVACION_PENDIENTE)

    activos = list(
        db.scalars(
            select(Strike).where(Strike.usuario_id == usuario.id, Strike.anulado.is_(False))
        )
    )
    ids_activos = {strike.id for strike in activos}
    ids_pedidos = {item.strike_id for item in datos.strikes}
    if not ids_pedidos.issubset(ids_activos):
        raise ErrorSancion(422, "Solo puedes justificar tus strikes activos")
    if ids_pedidos != ids_activos:
        raise ErrorSancion(422, "Debes justificar cada uno de tus strikes activos")

    reactivacion = Reactivacion(
        usuario_id=usuario.id,
        justificacion=datos.justificacion.strip(),
        detalle=[
            {
                "strike_id": item.strike_id,
                "justificacion": item.justificacion.strip(),
            }
            for item in datos.strikes
        ],
    )
    db.add(reactivacion)
    db.flush()

    for admin in _admins(db):
        notificaciones.crear(
            db,
            usuario_id=admin.id,
            tipo=TipoNotificacion.REACTIVACION_SOLICITADA,
            titulo="Solicitud de reactivación",
            mensaje=(
                f"{usuario.nombre} pidió reactivarse con {len(ids_activos)} strikes activos. "
                "Revisa el caso en Admin → Sanciones."
            ),
        )
    db.commit()
    db.refresh(reactivacion)
    return _reactivacion_out(db, reactivacion)


def listar_reactivaciones(db: Session, estado: EstadoReactivacion | None = None) -> list[dict]:
    consulta = select(Reactivacion)
    if estado is not None:
        consulta = consulta.where(Reactivacion.estado == estado)
    filas = db.scalars(consulta.order_by(Reactivacion.creada_en.desc(), Reactivacion.id.desc()))
    return [_reactivacion_out(db, item) for item in filas]


def decidir_reactivacion(
    db: Session,
    admin: Usuario,
    reactivacion_id: int,
    datos: ReactivacionDecision,
) -> dict:
    reactivacion = db.scalar(
        select(Reactivacion).where(Reactivacion.id == reactivacion_id).with_for_update()
    )
    if reactivacion is None:
        raise ErrorSancion(404, "La solicitud de reactivación no existe")
    if reactivacion.estado != EstadoReactivacion.PENDIENTE:
        raise ErrorSancion(409, "Esta solicitud de reactivación ya fue decidida")

    usuario = db.get(Usuario, reactivacion.usuario_id)
    if usuario is None:
        raise ErrorSancion(404, "El usuario de la reactivación no existe")

    if datos.aprobar:
        anulados = _anular_strikes(db, admin, reactivacion, datos.strikes_anular)
        reactivacion.estado = EstadoReactivacion.ACEPTADA
        reactivacion.strikes_anulados = anulados
        reactivacion.motivo_rechazo = None
        restantes = contar_strikes(db, usuario.id)
        notificaciones.crear(
            db,
            usuario_id=usuario.id,
            tipo=TipoNotificacion.REACTIVACION_ACEPTADA,
            titulo="Reactivación aceptada",
            mensaje=(
                f"El administrador aceptó tu reactivación y anuló {anulados} strike(s). "
                f"Te quedan {restantes} strikes activos."
            ),
        )
    else:
        reactivacion.estado = EstadoReactivacion.RECHAZADA
        reactivacion.motivo_rechazo = (datos.motivo or "").strip()
        notificaciones.crear(
            db,
            usuario_id=usuario.id,
            tipo=TipoNotificacion.REACTIVACION_RECHAZADA,
            titulo="Reactivación rechazada",
            mensaje=(
                "El administrador rechazó tu reactivación. Motivo: "
                f"{reactivacion.motivo_rechazo}"
            ),
        )

    reactivacion.decidida_por = admin.id
    reactivacion.fecha_decision = datetime.now(ZONA_COLOMBIA)
    db.commit()
    db.refresh(reactivacion)
    return _reactivacion_out(db, reactivacion)


def _anular_strikes(
    db: Session, admin: Usuario, reactivacion: Reactivacion, ids: list[int]
) -> int:
    strikes = list(
        db.scalars(
            select(Strike).where(
                Strike.id.in_(ids),
                Strike.usuario_id == reactivacion.usuario_id,
                Strike.anulado.is_(False),
            )
        )
    )
    if len(strikes) != len(set(ids)):
        raise ErrorSancion(422, "Solo puedes anular strikes activos del usuario de la reactivación")
    for strike in strikes:
        strike.anulado = True
        strike.anulado_por = admin.id
        strike.motivo_anulacion = "Anulado por reactivación aceptada"
        strike.reactivacion_id = reactivacion.id
        trazabilidad.registrar(
            db,
            solicitud_id=db.get(Reserva, strike.reserva_id).solicitud_id,
            reserva_id=strike.reserva_id,
            usuario_id=admin.id,
            accion=AccionTrazabilidad.REACTIVACION_ACEPTADA,
            detalle=f"Strike #{strike.id} anulado al aceptar la reactivación #{reactivacion.id}",
        )
    return len(strikes)
