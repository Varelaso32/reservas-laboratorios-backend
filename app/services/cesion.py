"""Cupo por orden de llegada y jerarquía de rol (HU-30) y cesión del cupo (HU-31).

Reglas:
- Gana el cupo quien lo pidió primero (fecha y hora de registro en el servidor).
- Quien llega después con el mismo rol o uno inferior se rechaza automáticamente.
- Quien llega después con un rol superior debe dar un motivo de urgencia y su
  solicitud queda en espera de la decisión del titular: nunca le quita el cupo.
- El titular decide ceder o conservar; la decisión queda en la trazabilidad.

Ninguna función hace commit, salvo `decidir`, que cierra su propia transacción.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    JERARQUIA_RESERVA,
    AccionTrazabilidad,
    EstadoReserva,
    EstadoSolicitud,
    RolReserva,
    TipoNotificacion,
    rol_reserva_de,
)
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario
from app.services import notificaciones, recursos, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA

# Una solicitud pendiente ocupa cupo igual que una reserva confirmada (HU-34.5)
ESTADOS_QUE_OCUPAN = (
    EstadoSolicitud.PENDIENTE,
    EstadoSolicitud.PENDIENTE_AUTORIZACION,
    EstadoSolicitud.EN_ESPERA_CESION,
)

NOMBRES_ROL = {
    RolReserva.ESTUDIANTE: "Estudiante",
    RolReserva.DOCENTE: "Docente",
    RolReserva.COORDINADOR: "Coordinador",
    RolReserva.DIRECTOR: "Director",
}


class ErrorCesion(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass
class Cupo:
    """Quién tiene el cupo de un espacio y horario, y con qué respaldo."""

    usuario: Usuario
    rol: RolReserva
    creada_en: datetime
    reserva: Reserva | None = None
    solicitud: Solicitud | None = None


@dataclass
class Evaluacion:
    """Resultado de comparar la jerarquía de quien llega con la del titular."""

    rechazo: str | None = None
    en_espera: bool = False


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def buscar_titular(
    db: Session, espacio_id: int, inicio: datetime, fin: datetime, solicitante_id: int
) -> Cupo | None:
    """Cupo vigente de otro usuario que se cruza con el horario, o None.

    Se consideran reservas activas y solicitudes que ocupan cupo. Si hay varias,
    gana la que se registró primero (HU-30, criterio 3).
    """
    reservas = db.execute(
        select(Reserva, Usuario)
        .join(Usuario, Usuario.id == Reserva.usuario_id)
        .where(
            Reserva.espacio_id == espacio_id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < fin,
            Reserva.fin > inicio,
            Reserva.usuario_id != solicitante_id,
        )
    ).all()
    solicitudes = db.execute(
        select(Solicitud, Usuario)
        .join(Usuario, Usuario.id == Solicitud.solicitante_id)
        .where(
            Solicitud.espacio_id == espacio_id,
            Solicitud.estado.in_(ESTADOS_QUE_OCUPAN),
            Solicitud.inicio < fin,
            Solicitud.fin > inicio,
            Solicitud.solicitante_id != solicitante_id,
        )
    ).all()

    cupos = [
        Cupo(
            usuario=usuario,
            rol=rol_reserva_de(usuario.cargo),
            creada_en=reserva.creada_en,
            reserva=reserva,
        )
        for reserva, usuario in reservas
    ]
    cupos += [
        Cupo(
            usuario=usuario,
            rol=rol_reserva_de(usuario.cargo),
            creada_en=solicitud.creada_en,
            solicitud=solicitud,
        )
        for solicitud, usuario in solicitudes
    ]
    if not cupos:
        return None

    # La reserva confirmada gana el empate: ya está en firme
    cupos.sort(key=lambda cupo: (cupo.creada_en, 0 if cupo.reserva else 1))
    return cupos[0]


def evaluar(usuario: Usuario, cupo: Cupo, motivo_urgencia: str | None) -> Evaluacion:
    """Compara jerarquías. Lanza ErrorCesion si falta el motivo de urgencia."""
    rol_solicitante = rol_reserva_de(usuario.cargo)
    if JERARQUIA_RESERVA.index(rol_solicitante) <= JERARQUIA_RESERVA.index(cupo.rol):
        motivo = (
            f"El cupo de ese espacio y horario lo pidió primero {cupo.usuario.nombre} "
            f"({NOMBRES_ROL[cupo.rol]}), con jerarquía igual o superior a la tuya. "
            "Solo un Docente, Coordinador o Director puede pedir el cupo de alguien de menor "
            "jerarquía."
        )
        return Evaluacion(rechazo=motivo)

    if not motivo_urgencia:
        raise ErrorCesion(
            422,
            "Ese horario ya está ocupado por un usuario de menor jerarquía. "
            "Para pedir el cupo debes indicar el motivo de urgencia.",
        )
    return Evaluacion(en_espera=True)


def notificar_solicitud(
    db: Session, solicitud: Solicitud, espacio: Espacio, titular: Usuario, solicitante: Usuario
) -> None:
    """Avisa al titular con todo lo que necesita para decidir (HU-31, criterio 2)."""
    inicio = solicitud.inicio.astimezone(ZONA_COLOMBIA)
    fin = solicitud.fin.astimezone(ZONA_COLOMBIA)
    rol = NOMBRES_ROL[rol_reserva_de(solicitante.cargo)]
    mensaje = (
        f"{solicitante.nombre} ({rol}) solicita tu cupo de {espacio.nombre} el "
        f"{inicio:%d/%m/%Y} de {inicio:%H:%M} a {fin:%H:%M}. "
        f"Motivo de urgencia: {solicitud.motivo_urgencia}"
    )
    notificaciones.crear(
        db,
        usuario_id=titular.id,
        tipo=TipoNotificacion.CESION_SOLICITADA,
        titulo="Solicitud de cesión de cupo",
        mensaje=mensaje,
        solicitud_id=solicitud.id,
    )


def _salida(solicitud: Solicitud, espacio: Espacio) -> dict:
    return {
        "id": solicitud.id,
        "estado": solicitud.estado,
        "espacio_id": solicitud.espacio_id,
        "espacio_nombre": espacio.nombre,
        "inicio": _local(solicitud.inicio),
        "fin": _local(solicitud.fin),
        "motivo_urgencia": solicitud.motivo_urgencia,
        "motivo_rechazo": solicitud.motivo_rechazo,
    }


def _cancelar_cupo_del_titular(
    db: Session, solicitud: Solicitud, titular: Usuario, solicitante: Usuario
) -> None:
    """Libera el cupo del titular: cancela su reserva o su solicitud pendiente."""
    reserva = db.scalar(
        select(Reserva)
        .where(
            Reserva.usuario_id == titular.id,
            Reserva.espacio_id == solicitud.espacio_id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < solicitud.fin,
            Reserva.fin > solicitud.inicio,
        )
        .with_for_update()
    )
    if reserva is not None:
        reserva.estado = EstadoReserva.CANCELADA
        solicitud_titular = db.get(Solicitud, reserva.solicitud_id)
        if solicitud_titular is not None:
            anterior = solicitud_titular.estado.value
            solicitud_titular.estado = EstadoSolicitud.CANCELADA
            trazabilidad.registrar(
                db,
                solicitud_id=solicitud_titular.id,
                reserva_id=reserva.id,
                usuario_id=titular.id,
                accion=AccionTrazabilidad.CESION_ACEPTADA,
                estado_anterior=anterior,
                estado_nuevo=EstadoSolicitud.CANCELADA.value,
                detalle=f"Cupo cedido a {solicitante.nombre} (solicitud #{solicitud.id})",
            )
        # Se confirma la cancelación antes de crear la reserva nueva: la BD no
        # admite dos reservas activas cruzadas en el mismo espacio.
        db.flush()
        # HU-44, criterio 7: al ceder el cupo se cancelan sus solicitudes de recursos
        recursos.cancelar_por_reserva(db, reserva.id, "El cupo fue cedido a otro solicitante")
        return

    solicitud_titular = db.scalar(
        select(Solicitud)
        .where(
            Solicitud.solicitante_id == titular.id,
            Solicitud.espacio_id == solicitud.espacio_id,
            Solicitud.estado.in_(ESTADOS_QUE_OCUPAN),
            Solicitud.id != solicitud.id,
            Solicitud.inicio < solicitud.fin,
            Solicitud.fin > solicitud.inicio,
        )
        .with_for_update()
    )
    if solicitud_titular is not None:
        anterior = solicitud_titular.estado.value
        solicitud_titular.estado = EstadoSolicitud.CANCELADA
        trazabilidad.registrar(
            db,
            solicitud_id=solicitud_titular.id,
            usuario_id=titular.id,
            accion=AccionTrazabilidad.CESION_ACEPTADA,
            estado_anterior=anterior,
            estado_nuevo=EstadoSolicitud.CANCELADA.value,
            detalle=f"Cupo cedido a {solicitante.nombre} (solicitud #{solicitud.id})",
        )
        db.flush()


def decidir(
    db: Session, usuario: Usuario, solicitud_id: int, aprobar: bool, motivo: str | None
) -> dict:
    """El titular del cupo acepta o rechaza la cesión (HU-31)."""
    solicitud = db.scalar(select(Solicitud).where(Solicitud.id == solicitud_id).with_for_update())
    if solicitud is None:
        raise ErrorCesion(404, "La solicitud no existe")
    if solicitud.titular_id != usuario.id:
        raise ErrorCesion(403, "Solo el titular del cupo puede decidir la cesión")
    if solicitud.estado != EstadoSolicitud.EN_ESPERA_CESION:
        raise ErrorCesion(
            409,
            f"La solicitud ya no está en espera de cesión (estado actual: {solicitud.estado.value})",
        )

    ahora = datetime.now(ZONA_COLOMBIA)
    if solicitud.inicio < ahora:
        raise ErrorCesion(409, "La solicitud está vencida: su hora de inicio ya pasó")

    espacio = db.get(Espacio, solicitud.espacio_id)
    solicitante = db.get(Usuario, solicitud.solicitante_id)
    estado_anterior = solicitud.estado.value

    if not aprobar:
        if not motivo:
            raise ErrorCesion(422, "Para conservar tu cupo debes indicar un motivo")
        solicitud.estado = EstadoSolicitud.RECHAZADA
        solicitud.motivo_rechazo = motivo
        solicitud.decidido_por = usuario.id
        solicitud.fecha_decision = ahora

        trazabilidad.registrar(
            db,
            solicitud_id=solicitud.id,
            usuario_id=usuario.id,
            accion=AccionTrazabilidad.CESION_RECHAZADA,
            estado_anterior=estado_anterior,
            estado_nuevo=EstadoSolicitud.RECHAZADA.value,
            detalle=f"El titular conservó su cupo. Motivo: {motivo}",
        )
        notificaciones.descartar_previos(db, solicitud.id)
        notificaciones.crear(
            db,
            usuario_id=solicitud.solicitante_id,
            tipo=TipoNotificacion.CESION_RECHAZADA,
            titulo="El titular conservó su cupo",
            mensaje=(
                f"{usuario.nombre} no cedió el cupo de {espacio.nombre} el "
                f"{solicitud.inicio.astimezone(ZONA_COLOMBIA):%d/%m/%Y}. Motivo: {motivo}"
            ),
            solicitud_id=solicitud.id,
        )
        db.commit()

        return {
            "mensaje": f"Solicitud #{solicitud.id} rechazada: conservas tu reserva.",
            "solicitud": _salida(solicitud, espacio),
        }

    # Ceder: el cupo del titular se libera y la reserva pasa a quien solicitó
    _cancelar_cupo_del_titular(db, solicitud, usuario, solicitante)

    solicitud.estado = EstadoSolicitud.APROBADA
    solicitud.decidido_por = usuario.id
    solicitud.fecha_decision = ahora

    reserva = Reserva(
        solicitud_id=solicitud.id,
        espacio_id=solicitud.espacio_id,
        usuario_id=solicitud.solicitante_id,
        inicio=solicitud.inicio,
        fin=solicitud.fin,
        estado=EstadoReserva.ACTIVA,
    )
    db.add(reserva)
    try:
        db.flush()
    except IntegrityError as error:
        if "ex_reserva_sin_cruce" in str(error.orig):
            raise ErrorCesion(
                409, "El espacio ya fue reservado en ese horario por otra solicitud aprobada"
            ) from error
        raise

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        reserva_id=reserva.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CESION_ACEPTADA,
        estado_anterior=estado_anterior,
        estado_nuevo=EstadoSolicitud.APROBADA.value,
        detalle=f"Cesión aceptada por el titular; reserva #{reserva.id} a nombre de {solicitante.nombre}",
    )
    notificaciones.descartar_previos(db, solicitud.id)
    notificaciones.crear(
        db,
        usuario_id=usuario.id,
        tipo=TipoNotificacion.CESION_ACEPTADA,
        titulo="Cediste tu cupo",
        mensaje=(
            f"Cediste el cupo de {espacio.nombre} el "
            f"{solicitud.inicio.astimezone(ZONA_COLOMBIA):%d/%m/%Y} a {solicitante.nombre}. "
            f"Su reserva quedó confirmada."
        ),
        solicitud_id=solicitud.id,
    )
    notificaciones.crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=TipoNotificacion.CESION_CONFIRMADA,
        titulo="Cupo cedido a tu favor",
        mensaje=(
            f"{usuario.nombre} cedió el cupo de {espacio.nombre} el "
            f"{solicitud.inicio.astimezone(ZONA_COLOMBIA):%d/%m/%Y}. "
            f"Tu reserva #{reserva.id} quedó confirmada."
        ),
        solicitud_id=solicitud.id,
    )
    db.commit()

    return {
        "mensaje": f"Solicitud #{solicitud.id} aprobada por cesión. Se generó la reserva #{reserva.id}.",
        "solicitud": _salida(solicitud, espacio),
    }
