"""Asistencia efectiva, tolerancia y liberación por no-show (HU-38 y HU-39).

No hay planificador en el proceso: la verificación es perezosa y se ejecuta al
consultar reservas, al crear una solicitud, al abrir el reporte de sanciones o
al llamar al endpoint administrativo de procesamiento. Así el estado siempre
está al día sin depender de un cron externo.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    AccionTrazabilidad,
    EstadoAsistencia,
    EstadoReserva,
    TipoNotificacion,
)
from app.models.modelos import Reserva, Strike, Usuario
from app.services import notificaciones, recursos, sanciones, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA

_YA_ASISTIO = "La asistencia de esta reserva ya fue registrada"


class ErrorAsistencia(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def tolerancia_hasta(reserva: Reserva, tolerancia_minutos: int) -> datetime:
    return reserva.inicio + timedelta(minutes=tolerancia_minutos)


def puede_registrar(reserva: Reserva, ahora: datetime, tolerancia_minutos: int) -> bool:
    """Ventana de registro: desde el inicio y hasta vencer la tolerancia."""
    return (
        reserva.estado == EstadoReserva.ACTIVA
        and reserva.estado_asistencia == EstadoAsistencia.PENDIENTE
        and reserva.inicio <= ahora <= tolerancia_hasta(reserva, tolerancia_minutos)
    )


def _salida_asistencia(reserva: Reserva, mensaje: str) -> dict:
    return {
        "reserva_id": reserva.id,
        "estado": reserva.estado.value,
        "estado_asistencia": reserva.estado_asistencia.value,
        "inicio_efectivo": _local(reserva.inicio_efectivo),
        "mensaje": mensaje,
    }


def registrar(
    db: Session, usuario: Usuario, reserva_id: int, ahora: datetime | None = None
) -> dict:
    """HU-38: el titular registra que asistió dentro de la tolerancia."""
    ahora = ahora or datetime.now(ZONA_COLOMBIA)
    # Primero se ponen al día los no-show: si la tolerancia ya venció, no se registra
    procesar_vencidas(db, ahora)

    reserva = db.scalar(select(Reserva).where(Reserva.id == reserva_id).with_for_update())
    if reserva is None or reserva.usuario_id != usuario.id:
        raise ErrorAsistencia(404, "La reserva no existe o no tienes acceso a ella")
    if reserva.estado == EstadoReserva.CANCELADA:
        raise ErrorAsistencia(409, "La reserva está cancelada")
    if reserva.estado_asistencia == EstadoAsistencia.ASISTIO:
        return _salida_asistencia(reserva, _YA_ASISTIO)
    if reserva.estado == EstadoReserva.NO_ASISTIO:
        raise ErrorAsistencia(
            409,
            "La tolerancia ya venció y la reserva quedó como no-show: no se puede registrar asistencia",
        )

    parametros = sanciones.obtener_parametros(db)
    if ahora < reserva.inicio:
        raise ErrorAsistencia(409, "La reserva todavía no inicia: podrás registrar la asistencia a su hora")
    if ahora > tolerancia_hasta(reserva, parametros.tolerancia_minutos):
        raise ErrorAsistencia(
            409, "La tolerancia ya venció y la reserva quedó como no-show"
        )

    reserva.estado_asistencia = EstadoAsistencia.ASISTIO
    reserva.inicio_efectivo = ahora
    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.ASISTENCIA_REGISTRADA,
        estado_anterior=EstadoAsistencia.PENDIENTE.value,
        estado_nuevo=EstadoAsistencia.ASISTIO.value,
        detalle=f"Asistencia registrada a las {ahora.astimezone(ZONA_COLOMBIA):%H:%M}",
    )
    db.commit()
    db.refresh(reserva)
    return _salida_asistencia(reserva, "Asistencia registrada. ¡Buen uso del espacio!")


def _avisar(db: Session, reserva: Reserva, tipo: TipoNotificacion, titulo: str, mensaje: str):
    notificaciones.crear(
        db,
        usuario_id=reserva.usuario_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        solicitud_id=reserva.solicitud_id,
    )


def _aplicar_no_show(db: Session, reserva: Reserva, parametros) -> int:
    """Marca el no-show, genera los strikes y avisa al titular (HU-39, HU-40)."""
    reserva.estado = EstadoReserva.NO_ASISTIO
    reserva.estado_asistencia = EstadoAsistencia.NO_ASISTIO

    minutos = parametros.tolerancia_minutos
    bloques = minutos // parametros.minutos_por_strike
    trazabilidad.registrar(
        db,
        solicitud_id=reserva.solicitud_id,
        reserva_id=reserva.id,
        usuario_id=reserva.usuario_id,
        accion=AccionTrazabilidad.NO_SHOW,
        estado_anterior=EstadoReserva.ACTIVA.value,
        estado_nuevo=EstadoReserva.NO_ASISTIO.value,
        detalle=(
            f"Sin asistencia al vencer la tolerancia de {minutos} minutos; "
            "el espacio quedó libre"
        ),
    )
    _avisar(
        db,
        reserva,
        TipoNotificacion.NO_SHOW_REGISTRADO,
        "Reserva marcada como no-show",
        (
            f"No registraste asistencia dentro de los {minutos} minutos de tolerancia. "
            "La reserva se liberó y el espacio quedó disponible para el horario restante."
        ),
    )

    total = sanciones.contar_strikes(db, reserva.usuario_id)
    for _ in range(bloques):
        strike = Strike(
            usuario_id=reserva.usuario_id,
            reserva_id=reserva.id,
            minutos_retraso=minutos,
        )
        db.add(strike)
        db.flush()
        total += 1
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=reserva.usuario_id,
            accion=AccionTrazabilidad.STRIKE_ASIGNADO,
            detalle=(
                f"Strike #{strike.id} por {minutos} minutos de retraso "
                f"(total {total}/{parametros.max_strikes})"
            ),
        )

    if bloques:
        _avisar(
            db,
            reserva,
            TipoNotificacion.STRIKE_ASIGNADO,
            "Se registró un strike",
            (
                f"Se te asignó {bloques} strike(s) por no asistir. "
                f"Acumulas {total} de {parametros.max_strikes} permitidos."
            ),
        )

    if total >= parametros.max_strikes:
        _avisar(
            db,
            reserva,
            TipoNotificacion.BLOQUEO_SOLICITUDES,
            "Solicitudes bloqueadas",
            (
                f"Alcanzaste {total} strikes de {parametros.max_strikes} permitidos: "
                "no podrás crear nuevas solicitudes. Puedes pedir tu reactivación en "
                "Configuración → Mi sanción."
            ),
        )
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=reserva.usuario_id,
            accion=AccionTrazabilidad.BLOQUEO_SOLICITUDES,
            detalle=(
                f"Bloqueo de nuevas solicitudes al llegar a {total} strikes "
                f"(máximo {parametros.max_strikes})"
            ),
        )
    # HU-44, criterio 7: el no-show cancela las solicitudes de recursos de la reserva
    recursos.cancelar_por_reserva(db, reserva.id, "La reserva quedó como no-show")
    return bloques


def procesar_vencidas(db: Session, ahora: datetime | None = None) -> dict:
    """Envía advertencias y marca los no-show cuya tolerancia ya venció.

    Solo considera reservas `sancionable = true`, es decir, creadas después de
    activar la funcionalidad.
    """
    ahora = ahora or datetime.now(ZONA_COLOMBIA)
    parametros = sanciones.obtener_parametros(db)

    limite_aviso = ahora - timedelta(minutes=parametros.aviso_minutos)
    limite_tolerancia = ahora - timedelta(minutes=parametros.tolerancia_minutos)

    advertidas = 0
    candidatas = list(
        db.scalars(
            select(Reserva).where(
                Reserva.estado == EstadoReserva.ACTIVA,
                Reserva.estado_asistencia == EstadoAsistencia.PENDIENTE,
                Reserva.sancionable.is_(True),
                Reserva.advertencia_enviada.is_(False),
                Reserva.inicio <= limite_aviso,
                Reserva.inicio > limite_tolerancia,
            )
        )
    )
    for reserva in candidatas:
        _avisar(
            db,
            reserva,
            TipoNotificacion.ADVERTENCIA_NO_ASISTENCIA,
            "Registra tu asistencia",
            (
                f"Tu reserva ya inició y aún no registras asistencia. "
                f"Tienes hasta {parametros.tolerancia_minutos} minutos desde el inicio "
                "para hacerlo; después se marcará como no-show."
            ),
        )
        trazabilidad.registrar(
            db,
            solicitud_id=reserva.solicitud_id,
            reserva_id=reserva.id,
            usuario_id=reserva.usuario_id,
            accion=AccionTrazabilidad.ADVERTENCIA_NO_ASISTENCIA,
            detalle=(
                f"Advertencia enviada a los {parametros.aviso_minutos} minutos de inicio; "
                f"la tolerancia vence a los {parametros.tolerancia_minutos}"
            ),
        )
        reserva.advertencia_enviada = True
        advertidas += 1

    no_shows = 0
    vencidas = list(
        db.scalars(
            select(Reserva).where(
                Reserva.estado == EstadoReserva.ACTIVA,
                Reserva.estado_asistencia == EstadoAsistencia.PENDIENTE,
                Reserva.sancionable.is_(True),
                Reserva.inicio <= limite_tolerancia,
            )
        )
    )
    for reserva in vencidas:
        _aplicar_no_show(db, reserva, parametros)
        no_shows += 1

    if advertidas or no_shows:
        db.commit()
    return {"advertencias": advertidas, "no_shows": no_shows}
