"""Revisión de solicitudes por el aprobador (HU-08, HU-09)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models.enums import EstadoSolicitud, Rol
from app.models.modelos import Espacio, Solicitud, Usuario, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA

Solicitante = aliased(Usuario)
Decisor = aliased(Usuario)


def gestiona_espacio(espacio_id, aprobador_id: int):
    """Condición: el aprobador tiene asignado el espacio (HU-08, criterio 4)."""
    return exists().where(
        espacio_aprobador.c.espacio_id == espacio_id,
        espacio_aprobador.c.usuario_id == aprobador_id,
    )


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def _salida(sol: Solicitud, esp: Espacio, solicitante: Usuario) -> dict:
    return {
        "id": sol.id,
        "estado": sol.estado,
        "solicitante": {
            "id": solicitante.id,
            "nombre": solicitante.nombre,
            "email": solicitante.email,
            "cargo": solicitante.cargo,
        },
        "espacio": {
            "id": esp.id,
            "nombre": esp.nombre,
            "tipo": esp.tipo,
            "capacidad": esp.capacidad,
            "ubicacion": esp.ubicacion,
        },
        "inicio": _local(sol.inicio),
        "fin": _local(sol.fin),
        "asistentes": sol.asistentes,
        "creada_en": _local(sol.creada_en),
        "vencida": sol.inicio < datetime.now(ZONA_COLOMBIA),
    }


def listar_pendientes(db: Session, usuario: Usuario, espacio_id: int | None = None) -> list[dict]:
    """El APROBADOR ve las de sus espacios; el ADMIN las de todos, solo para consulta."""
    consulta = (
        select(Solicitud, Espacio, Solicitante)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Solicitante, Solicitante.id == Solicitud.solicitante_id)
        .where(Solicitud.estado == EstadoSolicitud.PENDIENTE)
    )
    if usuario.rol != Rol.ADMIN:
        consulta = consulta.where(gestiona_espacio(Solicitud.espacio_id, usuario.id))
    if espacio_id is not None:
        consulta = consulta.where(Solicitud.espacio_id == espacio_id)
    # Primero las que se usan más pronto: son las más urgentes de decidir
    filas = db.execute(consulta.order_by(Solicitud.inicio, Solicitud.id)).all()
    return [_salida(s, e, u) for s, e, u in filas]


def listar_resueltas(
    db: Session,
    usuario: Usuario,
    espacio_id: int,
    estado: EstadoSolicitud | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> list[dict]:
    """Lista decisiones aprobadas o rechazadas de un espacio.

    El APROBADOR solo ve los espacios que tiene asignados; el ADMIN ve cualquiera.
    """
    consulta = (
        select(Solicitud, Espacio, Solicitante, Decisor.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Solicitante, Solicitante.id == Solicitud.solicitante_id)
        .join(Decisor, Decisor.id == Solicitud.decidido_por)
        .where(
            Solicitud.espacio_id == espacio_id,
            Solicitud.estado.in_((EstadoSolicitud.APROBADA, EstadoSolicitud.RECHAZADA)),
        )
    )
    if usuario.rol != Rol.ADMIN:
        consulta = consulta.where(gestiona_espacio(Solicitud.espacio_id, usuario.id))
    if estado is not None:
        consulta = consulta.where(Solicitud.estado == estado)
    if fecha_desde is not None:
        desde = datetime.combine(fecha_desde, time.min, ZONA_COLOMBIA)
        consulta = consulta.where(Solicitud.fecha_decision >= desde)
    if fecha_hasta is not None:
        hasta_exclusivo = datetime.combine(fecha_hasta + timedelta(days=1), time.min, ZONA_COLOMBIA)
        consulta = consulta.where(Solicitud.fecha_decision < hasta_exclusivo)

    filas = db.execute(consulta.order_by(Solicitud.fecha_decision.desc(), Solicitud.id.desc())).all()
    return [
        {
            "id": solicitud.id,
            "estado": solicitud.estado.value,
            "solicitante": {
                "id": solicitante.id,
                "nombre": solicitante.nombre,
                "email": solicitante.email,
                "cargo": solicitante.cargo,
            },
            "espacio": {
                "id": espacio.id,
                "nombre": espacio.nombre,
                "tipo": espacio.tipo,
                "capacidad": espacio.capacidad,
                "ubicacion": espacio.ubicacion,
            },
            "inicio": _local(solicitud.inicio),
            "fin": _local(solicitud.fin),
            "asistentes": solicitud.asistentes,
            "decidida_por": decisor_nombre,
            "fecha_decision": _local(solicitud.fecha_decision),
            "motivo_rechazo": solicitud.motivo_rechazo,
        }
        for solicitud, espacio, solicitante, decisor_nombre in filas
    ]


def obtener_detalle(db: Session, usuario: Usuario, solicitud_id: int) -> dict | None:
    """Devuelve None si no existe o si el usuario no puede verla (así no se revela que existe)."""
    fila = db.execute(
        select(Solicitud, Espacio, Solicitante, Decisor.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Solicitante, Solicitante.id == Solicitud.solicitante_id)
        .outerjoin(Decisor, Decisor.id == Solicitud.decidido_por)
        .where(Solicitud.id == solicitud_id)
    ).first()
    if fila is None:
        return None
    sol, esp, solicitante, decisor_nombre = fila

    if usuario.rol == Rol.ADMIN:
        permitido = True
    elif usuario.rol == Rol.APROBADOR:
        permitido = bool(db.scalar(select(gestiona_espacio(sol.espacio_id, usuario.id))))
    else:
        permitido = sol.solicitante_id == usuario.id
    if not permitido:
        return None

    salida = _salida(sol, esp, solicitante)
    salida.update(
        {
            "proposito": sol.proposito,
            "equipamiento": sol.equipamiento,
            "motivo_rechazo": sol.motivo_rechazo,
            "decidido_por": decisor_nombre,
            "fecha_decision": _local(sol.fecha_decision),
        }
    )
    return salida
