"""Autorización especial de solicitudes fuera de la franja de operación (HU-35)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AccionTrazabilidad, EstadoSolicitud, rol_reserva_de
from app.models.modelos import Espacio, Solicitud, Usuario
from app.services import disponibilidad, notificaciones, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA


class ErrorAutorizacion(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _exigir_permiso(usuario: Usuario) -> None:
    # HU-35, criterio 4: solo un usuario con permiso de autorización especial decide
    if not usuario.puede_autorizar_especial:
        raise ErrorAutorizacion(403, "No tienes permiso para autorizar solicitudes fuera de la franja")


def _salida(solicitud: Solicitud, espacio: Espacio, solicitante: Usuario) -> dict:
    inicio = solicitud.inicio.astimezone(ZONA_COLOMBIA)
    fin = solicitud.fin.astimezone(ZONA_COLOMBIA)
    return {
        "id": solicitud.id,
        "estado": solicitud.estado,
        "solicitante": {
            "id": solicitante.id,
            "nombre": solicitante.nombre,
            "email": solicitante.email,
            "cargo": solicitante.cargo,
            "rol_reserva": rol_reserva_de(solicitante.cargo),
        },
        "espacio": {
            "id": espacio.id,
            "nombre": espacio.nombre,
            "tipo": espacio.tipo,
            "capacidad": espacio.capacidad,
            "ubicacion": espacio.ubicacion,
        },
        "fecha": inicio.date(),
        "inicio": inicio,
        "fin": fin,
        "asistentes": solicitud.asistentes,
        "proposito": solicitud.proposito,
        "motivo_urgencia": solicitud.motivo_urgencia,
        "creada_en": solicitud.creada_en.astimezone(ZONA_COLOMBIA),
    }


def listar_pendientes(db: Session, usuario: Usuario) -> list[dict]:
    _exigir_permiso(usuario)
    filas = db.execute(
        select(Solicitud, Espacio, Usuario)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Usuario, Usuario.id == Solicitud.solicitante_id)
        .where(Solicitud.estado == EstadoSolicitud.PENDIENTE_AUTORIZACION)
        .order_by(Solicitud.inicio, Solicitud.id)
    ).all()
    return [_salida(solicitud, espacio, solicitante) for solicitud, espacio, solicitante in filas]


def decidir(
    db: Session, usuario: Usuario, solicitud_id: int, aprobar: bool, motivo: str | None
) -> dict:
    _exigir_permiso(usuario)

    solicitud = db.scalar(select(Solicitud).where(Solicitud.id == solicitud_id).with_for_update())
    if solicitud is None:
        raise ErrorAutorizacion(404, "La solicitud no existe")
    if solicitud.estado != EstadoSolicitud.PENDIENTE_AUTORIZACION:
        raise ErrorAutorizacion(
            409,
            f"La solicitud no está pendiente de autorización (estado actual: {solicitud.estado.value})",
        )

    ahora = datetime.now(ZONA_COLOMBIA)
    estado_anterior = solicitud.estado.value

    if aprobar:
        if solicitud.inicio < ahora:
            raise ErrorAutorizacion(
                409, "La solicitud está vencida: su hora de inicio ya pasó y solo se puede negar"
            )
        if not disponibilidad.esta_disponible(
            db, solicitud.espacio_id, solicitud.inicio, solicitud.fin
        ):
            raise ErrorAutorizacion(
                409, "El espacio ya fue reservado en ese horario por otra solicitud aprobada"
            )
        solicitud.estado = EstadoSolicitud.PENDIENTE
        accion = AccionTrazabilidad.AUTORIZADA
        mensaje = (
            f"Solicitud #{solicitud.id} autorizada. Pasa al flujo normal de aprobación."
        )
    else:
        if not motivo:
            raise ErrorAutorizacion(422, "Para negar la autorización debes indicar un motivo")
        solicitud.estado = EstadoSolicitud.RECHAZADA
        solicitud.motivo_rechazo = motivo
        solicitud.decidido_por = usuario.id
        solicitud.fecha_decision = ahora
        accion = AccionTrazabilidad.AUTORIZACION_DENEGADA
        mensaje = f"Solicitud #{solicitud.id} rechazada: la autorización especial fue negada."

    solicitud.autorizado_por = usuario.id
    solicitud.fecha_autorizacion = ahora

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        accion=accion,
        estado_anterior=estado_anterior,
        estado_nuevo=solicitud.estado.value,
        detalle=motivo,
    )

    espacio = db.get(Espacio, solicitud.espacio_id)
    solicitante = db.get(Usuario, solicitud.solicitante_id)
    # El aviso de autorización ya no aplica; si se concedió, ahora toca aprobarla
    notificaciones.descartar_previos(db, solicitud.id)
    notificaciones.notificar_autorizacion(
        db, solicitud, espacio, concedida=aprobar, motivo=motivo
    )
    if aprobar:
        notificaciones.notificar_revisores(db, solicitud, espacio, solicitante)

    db.commit()
    db.refresh(solicitud)

    return {"mensaje": mensaje, "solicitud": _salida(solicitud, espacio, solicitante)}
