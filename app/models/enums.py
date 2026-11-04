import enum


class Rol(str, enum.Enum):
    SOLICITANTE = "SOLICITANTE"
    APROBADOR = "APROBADOR"
    ADMIN = "ADMIN"


class Cargo(str, enum.Enum):
    ESTUDIANTE = "ESTUDIANTE"
    DOCENTE = "DOCENTE"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    COORDINADOR_LABORATORIOS = "COORDINADOR_LABORATORIOS"
    ADMINISTRADOR_SALA = "ADMINISTRADOR_SALA"
    ADMINISTRADOR_SISTEMA = "ADMINISTRADOR_SISTEMA"


class RolReserva(str, enum.Enum):
    """Jerarquía de reserva (HU-30, HU-32, HU-37): de menor a mayor.

    Es distinta de `Rol`, que es el permiso dentro de la plataforma. Un usuario
    con rol SOLICITANTE puede tener cargo DOCENTE, y para las reservas cuenta
    como DOCENTE.
    """

    ESTUDIANTE = "ESTUDIANTE"
    DOCENTE = "DOCENTE"
    COORDINADOR = "COORDINADOR"
    DIRECTOR = "DIRECTOR"


# De menor a mayor jerarquía: el índice sirve para comparar (HU-30)
JERARQUIA_RESERVA = (
    RolReserva.ESTUDIANTE,
    RolReserva.DOCENTE,
    RolReserva.COORDINADOR,
    RolReserva.DIRECTOR,
)

# Cargo institucional -> rol de reserva. El administrativo reserva como docente
# y el administrador de salas como coordinador: son los niveles equivalentes.
ROL_RESERVA_POR_CARGO = {
    Cargo.ESTUDIANTE: RolReserva.ESTUDIANTE,
    Cargo.DOCENTE: RolReserva.DOCENTE,
    Cargo.ADMINISTRATIVO: RolReserva.DOCENTE,
    Cargo.COORDINADOR_LABORATORIOS: RolReserva.COORDINADOR,
    Cargo.ADMINISTRADOR_SALA: RolReserva.COORDINADOR,
    Cargo.ADMINISTRADOR_SISTEMA: RolReserva.DIRECTOR,
}


def rol_reserva_de(cargo: Cargo | None) -> RolReserva:
    """Rol de reserva de un usuario. Sin cargo se asume el nivel más bajo."""
    if cargo is None:
        return RolReserva.ESTUDIANTE
    return ROL_RESERVA_POR_CARGO[cargo]


class TipoEspacio(str, enum.Enum):
    LABORATORIO = "LABORATORIO"
    SALA = "SALA"


class EstadoSolicitud(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CANCELADA = "CANCELADA"
    # HU-35: fuera de la franja de operación, esperando autorización especial
    PENDIENTE_AUTORIZACION = "PENDIENTE_AUTORIZACION"
    # HU-30 / HU-31: solicitud de mayor jerarquía sobre un cupo ocupado
    EN_ESPERA_CESION = "EN_ESPERA_CESION"


class EstadoReserva(str, enum.Enum):
    ACTIVA = "ACTIVA"
    CANCELADA = "CANCELADA"
    # HU-39: venció la tolerancia sin registrar asistencia; el espacio se libera
    NO_ASISTIO = "NO_ASISTIO"


class EstadoAsistencia(str, enum.Enum):
    """HU-38: estado de asistencia de cada reserva confirmada."""

    PENDIENTE = "PENDIENTE"
    ASISTIO = "ASISTIO"
    NO_ASISTIO = "NO_ASISTIO"


class EstadoReactivacion(str, enum.Enum):
    """HU-42: solicitud de reactivación de un usuario bloqueado."""

    PENDIENTE = "PENDIENTE"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


class EstadoRecurso(str, enum.Enum):
    """HU-43: estado de funcionamiento de una unidad del inventario."""

    EN_FUNCIONAMIENTO = "EN_FUNCIONAMIENTO"
    FALLIDO = "FALLIDO"


class EstadoSolicitudRecurso(str, enum.Enum):
    """HU-44 / HU-45: ciclo de vida de una solicitud de recursos."""

    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CANCELADA = "CANCELADA"
    DEVUELTA = "DEVUELTA"


class EstadoAsignacion(str, enum.Enum):
    """HU-45 / HU-46: una unidad concreta asignada a una solicitud de recursos."""

    # Reservada al aprobar; todavía no se ha entregado físicamente
    ASIGNADA = "ASIGNADA"
    # Entregada al titular de la reserva
    ENTREGADA = "ENTREGADA"
    # Devuelta al inventario
    DEVUELTA = "DEVUELTA"
    # Liberada sin entregar (rechazo, cancelación de la reserva o de la solicitud)
    CANCELADA = "CANCELADA"


class AccionTrazabilidad(str, enum.Enum):
    CREADA = "CREADA"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CANCELADA = "CANCELADA"
    # HU-35: decisión de una solicitud fuera de la franja de operación
    AUTORIZADA = "AUTORIZADA"
    AUTORIZACION_DENEGADA = "AUTORIZACION_DENEGADA"
    # HU-30: conflicto de cupo resuelto por jerarquía de rol
    CONFLICTO_RECHAZADO = "CONFLICTO_RECHAZADO"
    CESION_SOLICITADA = "CESION_SOLICITADA"
    # HU-31: el titular decide sobre la cesión de su cupo
    CESION_ACEPTADA = "CESION_ACEPTADA"
    CESION_RECHAZADA = "CESION_RECHAZADA"
    # HU-38 a HU-42: asistencia, no-show, strikes y reactivación
    ASISTENCIA_REGISTRADA = "ASISTENCIA_REGISTRADA"
    ADVERTENCIA_NO_ASISTENCIA = "ADVERTENCIA_NO_ASISTENCIA"
    NO_SHOW = "NO_SHOW"
    STRIKE_ASIGNADO = "STRIKE_ASIGNADO"
    BLOQUEO_SOLICITUDES = "BLOQUEO_SOLICITUDES"
    REACTIVACION_SOLICITADA = "REACTIVACION_SOLICITADA"
    REACTIVACION_ACEPTADA = "REACTIVACION_ACEPTADA"
    REACTIVACION_RECHAZADA = "REACTIVACION_RECHAZADA"
    # HU-43 a HU-46: recursos tecnológicos asociados a una reserva
    RECURSO_SOLICITADO = "RECURSO_SOLICITADO"
    RECURSO_APROBADO = "RECURSO_APROBADO"
    RECURSO_RECHAZADO = "RECURSO_RECHAZADO"
    RECURSO_ASIGNADO = "RECURSO_ASIGNADO"
    RECURSO_ENTREGADO = "RECURSO_ENTREGADO"
    RECURSO_DEVUELTO = "RECURSO_DEVUELTO"
    RECURSO_CANCELADO = "RECURSO_CANCELADO"
    RECURSO_PENALIZADO = "RECURSO_PENALIZADO"


class TipoNotificacion(str, enum.Enum):
    """Notificaciones internas: cesión de cupo (HU-31) y estado de las solicitudes."""

    # Al titular: alguien de mayor jerarquía pidió su cupo y debe decidir
    CESION_SOLICITADA = "CESION_SOLICITADA"
    # Al titular: confirmación de que cedió su cupo
    CESION_ACEPTADA = "CESION_ACEPTADA"
    # Al solicitante: el titular no cedió el cupo
    CESION_RECHAZADA = "CESION_RECHAZADA"
    # Al solicitante: el titular cedió y la reserva quedó a su nombre
    CESION_CONFIRMADA = "CESION_CONFIRMADA"

    # --- Flujo normal de aprobación (HU-10, HU-11) ---
    # Al solicitante: su solicitud quedó registrada y en qué estado
    SOLICITUD_RECIBIDA = "SOLICITUD_RECIBIDA"
    # A los revisores: hay una solicitud pendiente que deben decidir
    SOLICITUD_PENDIENTE = "SOLICITUD_PENDIENTE"
    # Al solicitante: aprobaron su solicitud y se creó la reserva
    SOLICITUD_APROBADA = "SOLICITUD_APROBADA"
    # Al solicitante: rechazaron su solicitud, con el motivo
    SOLICITUD_RECHAZADA = "SOLICITUD_RECHAZADA"

    # --- Autorización especial fuera de la franja (HU-35) ---
    # A quien puede autorizar: hay una solicitud fuera de franja esperando
    SOLICITUD_POR_AUTORIZAR = "SOLICITUD_POR_AUTORIZAR"
    # Al solicitante: concedieron la autorización especial
    AUTORIZACION_CONCEDIDA = "AUTORIZACION_CONCEDIDA"
    # Al solicitante: negaron la autorización especial, con el motivo
    AUTORIZACION_DENEGADA = "AUTORIZACION_DENEGADA"

    # --- Asistencia, strikes y reactivación (HU-38 a HU-42) ---
    # Al titular: se acerca el vencimiento de la tolerancia y aún no registra asistencia
    ADVERTENCIA_NO_ASISTENCIA = "ADVERTENCIA_NO_ASISTENCIA"
    # Al titular: venció la tolerancia y la reserva quedó como no-show
    NO_SHOW_REGISTRADO = "NO_SHOW_REGISTRADO"
    # Al titular: se le asignó un strike, con el total acumulado
    STRIKE_ASIGNADO = "STRIKE_ASIGNADO"
    # Al titular: alcanzó el máximo de strikes y no puede volver a solicitar
    BLOQUEO_SOLICITUDES = "BLOQUEO_SOLICITUDES"
    # A los administradores: un usuario bloqueado pidió reactivación
    REACTIVACION_SOLICITADA = "REACTIVACION_SOLICITADA"
    # Al usuario: el administrador aceptó su reactivación
    REACTIVACION_ACEPTADA = "REACTIVACION_ACEPTADA"
    # Al usuario: el administrador rechazó su reactivación, con el motivo
    REACTIVACION_RECHAZADA = "REACTIVACION_RECHAZADA"

    # --- Recursos tecnológicos (HU-43 a HU-46) ---
    # A los administradores: hay una solicitud de recursos pendiente de decidir
    RECURSO_SOLICITADO = "RECURSO_SOLICITADO"
    # Al solicitante: aprobaron su solicitud y se asignaron las unidades
    RECURSO_APROBADO = "RECURSO_APROBADO"
    # Al solicitante: rechazaron su solicitud, con el motivo
    RECURSO_RECHAZADO = "RECURSO_RECHAZADO"
    # Al solicitante: su solicitud se canceló porque la reserva se canceló, cedió o fue no-show
    RECURSO_CANCELADO = "RECURSO_CANCELADO"
    # Al titular: no devolvió los recursos a tiempo y se generaron strikes dobles
    RECURSO_DEVOLUCION_TARDIA = "RECURSO_DEVOLUCION_TARDIA"
