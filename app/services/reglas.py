"""Reglas de reserva configurables por espacio (HU-21, HU-28, HU-29, HU-32 a HU-35).

Todas las validaciones viven aquí y se ejecutan en el servidor: el formulario
puede avisar antes, pero la decisión siempre la toma la API.

Ninguna función hace commit; el commit lo hace quien llama.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    ROL_RESERVA_POR_CARGO,
    EstadoReserva,
    EstadoSolicitud,
    RolReserva,
    rol_reserva_de,
)
from app.models.modelos import (
    Espacio,
    ReglaAnticipacionRol,
    Reserva,
    Solicitud,
    TipoUso,
    Usuario,
    espacio_tipo_uso,
)
from app.schemas.solicitud import SolicitudCrear
from app.utils.fechas import HORA_APERTURA, HORA_CIERRE, ZONA_COLOMBIA

# Estados que ocupan cupo del espacio: una solicitud pendiente cuenta igual que
# una reserva confirmada (HU-34, criterio 5).
ESTADOS_QUE_OCUPAN = (
    EstadoSolicitud.PENDIENTE,
    EstadoSolicitud.PENDIENTE_AUTORIZACION,
    EstadoSolicitud.EN_ESPERA_CESION,
)

DIAS_SEMANA = {
    1: "lunes",
    2: "martes",
    3: "miércoles",
    4: "jueves",
    5: "viernes",
    6: "sábado",
    7: "domingo",
}

# Roles que pueden quedar como responsable de una actividad (HU-32, criterio 6)
ROLES_RESPONSABLE = (RolReserva.DOCENTE, RolReserva.COORDINADOR, RolReserva.DIRECTOR)


class ErrorRegla(Exception):
    """Regla de negocio incumplida, con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass
class Validacion:
    """Resultado de validar una solicitud nueva."""

    estado: EstadoSolicitud
    tipo_uso: TipoUso | None
    responsable: Usuario | None
    avisos: list[str]


# --------------------------------------------------------------------------- #
# Franja de operación (HU-21, HU-34)
# --------------------------------------------------------------------------- #
def franja_de(espacio: Espacio) -> tuple[time, time]:
    """Franja del espacio o, si no tiene una configurada, la institucional."""
    if espacio.hora_apertura is not None and espacio.hora_cierre is not None:
        return espacio.hora_apertura, espacio.hora_cierre
    return HORA_APERTURA, HORA_CIERRE


def dias_de(espacio: Espacio) -> set[int]:
    """Días operables (1 = lunes ... 7 = domingo). Vacío significa sin restricción."""
    crudo = espacio.dias_operacion or ""
    return {int(parte) for parte in crudo.split(",") if parte.strip().isdigit()}


def _hhmm(valor: time) -> str:
    return valor.strftime("%H:%M")


def _dias_legibles(dias: set[int]) -> str:
    return ", ".join(DIAS_SEMANA[dia] for dia in sorted(dias))


def fuera_de_franja(espacio: Espacio, fecha: date, hora_inicio: time, hora_fin: time) -> str | None:
    """Motivo por el que el horario no cabe en la operación del espacio, o None."""
    apertura, cierre = franja_de(espacio)
    if hora_inicio < apertura or hora_fin > cierre:
        return f"Solo se puede reservar entre las {_hhmm(apertura)} y las {_hhmm(cierre)}"
    dias = dias_de(espacio)
    if dias and fecha.isoweekday() not in dias:
        return (
            f"El espacio no opera el {DIAS_SEMANA[fecha.isoweekday()]}; "
            f"atiende {_dias_legibles(dias)} de {_hhmm(apertura)} a {_hhmm(cierre)}"
        )
    return None


# --------------------------------------------------------------------------- #
# Catálogo de tipos de uso (HU-22, HU-29)
# --------------------------------------------------------------------------- #
def tipos_permitidos(db: Session, espacio_id: int) -> list[TipoUso]:
    return list(
        db.scalars(
            select(TipoUso)
            .join(espacio_tipo_uso, espacio_tipo_uso.c.tipo_uso_id == TipoUso.id)
            .where(espacio_tipo_uso.c.espacio_id == espacio_id, TipoUso.activo.is_(True))
            .order_by(TipoUso.nombre)
        )
    )


def _resolver_tipo_uso(
    db: Session, espacio: Espacio, tipo_uso_id: int | None
) -> TipoUso | None:
    permitidos = tipos_permitidos(db, espacio.id)
    if not permitidos:
        # HU-29, criterio 5: sin actividades configuradas no se bloquea la solicitud
        if tipo_uso_id is None:
            return None
        tipo = db.get(TipoUso, tipo_uso_id)
        if tipo is None:
            raise ErrorRegla(422, "El tipo de uso seleccionado no existe")
        return tipo

    nombres = ", ".join(tipo.nombre for tipo in permitidos)
    if tipo_uso_id is None:
        raise ErrorRegla(422, f"Selecciona la actividad de la reserva. Este espacio admite: {nombres}")
    elegido = next((tipo for tipo in permitidos if tipo.id == tipo_uso_id), None)
    if elegido is None:
        raise ErrorRegla(
            422, f"El espacio no admite esa actividad. Actividades permitidas: {nombres}"
        )
    return elegido


# --------------------------------------------------------------------------- #
# Anticipación por rol (HU-32, HU-37)
# --------------------------------------------------------------------------- #
def anticipacion_de(db: Session, usuario: Usuario) -> int | None:
    """Días máximos de anticipación del rol del usuario; None si no tiene límite."""
    return db.scalar(
        select(ReglaAnticipacionRol.dias_maximos).where(
            ReglaAnticipacionRol.rol == rol_reserva_de(usuario.cargo)
        )
    )


def _validar_anticipacion(db: Session, usuario: Usuario, fecha: date) -> None:
    dias = anticipacion_de(db, usuario)
    if dias is None:
        return
    limite = datetime.now(ZONA_COLOMBIA).date() + timedelta(days=dias)
    if fecha > limite:
        raise ErrorRegla(
            422,
            f"Tu rol permite reservar con {dias} días de anticipación como máximo; "
            f"la fecha máxima es {limite.isoformat()}",
        )


# --------------------------------------------------------------------------- #
# Responsable de la actividad (HU-32)
# --------------------------------------------------------------------------- #
def _resolver_responsable(
    db: Session, espacio: Espacio, responsable_id: int | None
) -> Usuario | None:
    if responsable_id is None:
        if espacio.requiere_responsable:
            raise ErrorRegla(
                422,
                "Este espacio exige seleccionar un responsable (docente, coordinador o director)",
            )
        return None

    responsable = db.get(Usuario, responsable_id)
    if responsable is None or not responsable.activo:
        raise ErrorRegla(422, "El responsable seleccionado no existe o no está activo")
    if rol_reserva_de(responsable.cargo) not in ROLES_RESPONSABLE:
        raise ErrorRegla(422, "El responsable debe ser docente, coordinador o director")
    return responsable


def responsables_disponibles(db: Session) -> list[Usuario]:
    """Usuarios activos que pueden quedar como responsable de una actividad."""
    cargos = [cargo for cargo, rol in ROL_RESERVA_POR_CARGO.items() if rol in ROLES_RESPONSABLE]
    return list(
        db.scalars(
            select(Usuario)
            .where(Usuario.activo.is_(True), Usuario.cargo.in_(cargos))
            .order_by(Usuario.nombre)
        )
    )


# --------------------------------------------------------------------------- #
# Duración máxima, separación y usos diarios (HU-33, HU-34)
# --------------------------------------------------------------------------- #
def _ocupacion(db: Session, espacio_id: int, inicio: datetime, fin: datetime, margen: timedelta):
    """Reservas activas y solicitudes que ocupan cupo dentro de [inicio - margen, fin + margen)."""
    desde = inicio - margen
    hasta = fin + margen

    reservas = db.execute(
        select(Reserva.inicio, Reserva.fin).where(
            Reserva.espacio_id == espacio_id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < hasta,
            Reserva.fin > desde,
        )
    ).all()
    solicitudes = db.execute(
        select(Solicitud.inicio, Solicitud.fin).where(
            Solicitud.espacio_id == espacio_id,
            Solicitud.estado.in_(ESTADOS_QUE_OCUPAN),
            Solicitud.inicio < hasta,
            Solicitud.fin > desde,
        )
    ).all()
    return list(reservas) + list(solicitudes)


def _primera_hora_disponible(
    db: Session,
    espacio_id: int,
    inicio: datetime,
    fin: datetime,
    margen: timedelta,
    intentos: int = 6,
) -> datetime | None:
    duracion = fin - inicio
    candidato = inicio
    for _ in range(intentos):
        conflictos = _ocupacion(db, espacio_id, candidato, candidato + duracion, margen)
        if not conflictos:
            return candidato
        candidato = max(conflicto.fin for conflicto in conflictos) + margen
    return None


def _validar_duracion(espacio: Espacio, inicio: datetime, fin: datetime) -> None:
    if espacio.duracion_maxima_min is None:
        return
    minutos = (fin - inicio).total_seconds() / 60
    if minutos > espacio.duracion_maxima_min:
        raise ErrorRegla(
            422,
            f"La duración máxima por uso de este espacio es de {espacio.duracion_maxima_min} minutos",
        )


def _validar_separacion(
    db: Session, espacio: Espacio, inicio: datetime, fin: datetime
) -> None:
    separacion = espacio.separacion_min or 0
    if separacion <= 0:
        return
    margen = timedelta(minutes=separacion)
    if not _ocupacion(db, espacio.id, inicio, fin, margen):
        return

    candidato = _primera_hora_disponible(db, espacio.id, inicio, fin, margen)
    mensaje = f"Debe haber {separacion} minutos de separación entre reservas de este espacio"
    if candidato is not None:
        mensaje += f". La primera hora disponible es {candidato.astimezone(ZONA_COLOMBIA):%H:%M}"
    raise ErrorRegla(409, mensaje)


def _validar_usos_diarios(
    db: Session, espacio: Espacio, fecha: date, inicio: datetime, fin: datetime
) -> None:
    if espacio.max_usos_dia is None:
        return

    inicio_dia = datetime.combine(fecha, time.min, ZONA_COLOMBIA)
    fin_dia = inicio_dia + timedelta(days=1)
    reservas = db.scalar(
        select(func.count())
        .select_from(Reserva)
        .where(
            Reserva.espacio_id == espacio.id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < fin_dia,
            Reserva.fin > inicio_dia,
        )
    )
    solicitudes = db.scalar(
        select(func.count())
        .select_from(Solicitud)
        .where(
            Solicitud.espacio_id == espacio.id,
            Solicitud.estado.in_(ESTADOS_QUE_OCUPAN),
            Solicitud.inicio < fin_dia,
            Solicitud.fin > inicio_dia,
        )
    )
    if (reservas or 0) + (solicitudes or 0) >= espacio.max_usos_dia:
        raise ErrorRegla(
            409,
            f"El espacio alcanzó el máximo de {espacio.max_usos_dia} usos por día; "
            "no tiene más usos disponibles hasta el día siguiente",
        )


# --------------------------------------------------------------------------- #
# Validación completa de una solicitud nueva
# --------------------------------------------------------------------------- #
def validar_creacion(
    db: Session,
    usuario: Usuario,
    espacio: Espacio,
    datos: SolicitudCrear,
    inicio: datetime,
    fin: datetime,
    conflicto_autorizado: bool = False,
) -> Validacion:
    """Aplica todas las reglas del espacio. Lanza ErrorRegla si alguna no se cumple.

    `conflicto_autorizado` se usa en la cesión de cupo (HU-30): la solicitud se
    cruza a propósito con el cupo del titular, así que la separación y el tope de
    usos diarios no aplican (el uso se reemplaza, no se suma).
    """
    estado = EstadoSolicitud.PENDIENTE
    avisos: list[str] = []

    # HU-21 / HU-34 / HU-35: franja y días de operación
    motivo = fuera_de_franja(espacio, datos.fecha, datos.hora_inicio, datos.hora_fin)
    if motivo is not None:
        if not espacio.admite_autorizacion_especial:
            raise ErrorRegla(422, motivo)
        estado = EstadoSolicitud.PENDIENTE_AUTORIZACION
        avisos.append(
            f"{motivo}. La solicitud queda pendiente de autorización especial."
        )

    # HU-28: capacidad y ocupación mínima
    if datos.asistentes > espacio.capacidad:
        raise ErrorRegla(
            422,
            f"La cantidad de asistentes ({datos.asistentes}) supera la capacidad del espacio "
            f"({espacio.capacidad})",
        )
    if espacio.ocupacion_minima is not None and datos.asistentes < espacio.ocupacion_minima:
        raise ErrorRegla(
            422,
            f"Este espacio exige un mínimo de {espacio.ocupacion_minima} asistentes "
            f"para aprovecharlo",
        )

    # HU-29: actividad permitida
    tipo_uso = _resolver_tipo_uso(db, espacio, datos.tipo_uso_id)

    # HU-32: anticipación y responsable
    _validar_anticipacion(db, usuario, datos.fecha)
    responsable = _resolver_responsable(db, espacio, datos.responsable_id)

    # HU-33: duración máxima y separación entre reservas
    _validar_duracion(espacio, inicio, fin)
    if not conflicto_autorizado:
        _validar_separacion(db, espacio, inicio, fin)

        # HU-34: máximo de usos por día
        _validar_usos_diarios(db, espacio, datos.fecha, inicio, fin)

    return Validacion(estado=estado, tipo_uso=tipo_uso, responsable=responsable, avisos=avisos)
