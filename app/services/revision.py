"""Revisión de solicitudes por el aprobador (HU-08, HU-09)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models.enums import EstadoSolicitud, Rol
from app.models.modelos import Espacio, Solicitud, TipoUso, Usuario, espacio_aprobador
from app.services import reglas
from app.utils.fechas import ZONA_COLOMBIA

Solicitante = aliased(Usuario)
Decisor = aliased(Usuario)
Responsable = aliased(Usuario)


def gestiona_espacio(espacio_id, aprobador_id: int):
    """Condición: el aprobador tiene asignado el espacio (HU-08, criterio 4)."""
    return exists().where(
        espacio_aprobador.c.espacio_id == espacio_id,
        espacio_aprobador.c.usuario_id == aprobador_id,
    )


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


# HU-12: etiqueta legible del nivel de prioridad (3 y 2 son alta jerarquía)
ETIQUETAS_PRIORIDAD = {3: "ALTA", 2: "ALTA", 1: "MEDIA", 0: "BAJA"}


def etiqueta_prioridad(prioridad: int) -> str:
    return ETIQUETAS_PRIORIDAD.get(prioridad, "BAJA")


def _fuera_de_franja(sol: Solicitud, esp: Espacio) -> bool:
    inicio = sol.inicio.astimezone(ZONA_COLOMBIA)
    fin = sol.fin.astimezone(ZONA_COLOMBIA)
    return reglas.fuera_de_franja(esp, inicio.date(), inicio.time(), fin.time()) is not None


def _salida(
    sol: Solicitud,
    esp: Espacio,
    solicitante: Usuario,
    tipo_uso: str | None = None,
    responsable: str | None = None,
) -> dict:
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
        "tipo_uso": tipo_uso,
        "responsable": responsable,
        "fuera_de_franja": _fuera_de_franja(sol, esp),
        "creada_en": _local(sol.creada_en),
        "vencida": sol.inicio < datetime.now(ZONA_COLOMBIA),
        "prioridad": sol.prioridad,
        "prioridad_etiqueta": etiqueta_prioridad(sol.prioridad),
    }


def listar_pendientes(db: Session, usuario: Usuario, espacio_id: int | None = None) -> list[dict]:
    """El APROBADOR ve las de sus espacios; el ADMIN las de todos, solo para consulta."""
    consulta = (
        select(Solicitud, Espacio, Solicitante, TipoUso.nombre, Responsable.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Solicitante, Solicitante.id == Solicitud.solicitante_id)
        .outerjoin(TipoUso, TipoUso.id == Solicitud.tipo_uso_id)
        .outerjoin(Responsable, Responsable.id == Solicitud.responsable_id)
        .where(Solicitud.estado == EstadoSolicitud.PENDIENTE)
    )
    if usuario.rol != Rol.ADMIN:
        consulta = consulta.where(gestiona_espacio(Solicitud.espacio_id, usuario.id))
    if espacio_id is not None:
        consulta = consulta.where(Solicitud.espacio_id == espacio_id)
    # HU-12: primero las de mayor prioridad; a igual prioridad, las más próximas
    filas = db.execute(
        consulta.order_by(Solicitud.prioridad.desc(), Solicitud.inicio, Solicitud.id)
    ).all()
    return [_salida(s, e, u, t, r) for s, e, u, t, r in filas]


def listar_resueltas(
    db: Session,
    usuario: Usuario,
    espacio_id: int,
    estado: EstadoSolicitud | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    reserva_desde: date | None = None,
    reserva_hasta: date | None = None,
) -> list[dict]:
    """Lista decisiones aprobadas o rechazadas de un espacio.

    El APROBADOR solo ve los espacios que tiene asignados; el ADMIN ve cualquiera.
    fecha_desde/hasta filtran por la fecha de la decisión; reserva_desde/hasta por el
    día de uso (inicio de la solicitud). Todas son inclusivas, en hora de Colombia.
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
    if reserva_desde is not None:
        consulta = consulta.where(Solicitud.inicio >= datetime.combine(reserva_desde, time.min, ZONA_COLOMBIA))
    if reserva_hasta is not None:
        hasta_exclusivo = datetime.combine(reserva_hasta + timedelta(days=1), time.min, ZONA_COLOMBIA)
        consulta = consulta.where(Solicitud.inicio < hasta_exclusivo)

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
        select(Solicitud, Espacio, Solicitante, Decisor.nombre, TipoUso.nombre, Responsable.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Solicitante, Solicitante.id == Solicitud.solicitante_id)
        .outerjoin(Decisor, Decisor.id == Solicitud.decidido_por)
        .outerjoin(TipoUso, TipoUso.id == Solicitud.tipo_uso_id)
        .outerjoin(Responsable, Responsable.id == Solicitud.responsable_id)
        .where(Solicitud.id == solicitud_id)
    ).first()
    if fila is None:
        return None
    sol, esp, solicitante, decisor_nombre, tipo_uso, responsable = fila

    if usuario.rol == Rol.ADMIN:
        permitido = True
    elif usuario.rol == Rol.APROBADOR:
        permitido = bool(db.scalar(select(gestiona_espacio(sol.espacio_id, usuario.id))))
    else:
        permitido = sol.solicitante_id == usuario.id
    if not permitido:
        return None

    salida = _salida(sol, esp, solicitante, tipo_uso, responsable)
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
