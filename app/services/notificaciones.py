"""Notificaciones internas del usuario.

Cubren la cesión de cupo (HU-31) y el estado de las solicitudes (HU-10, HU-11,
HU-35): el solicitante sabe si su solicitud quedó pendiente, aprobada o
rechazada —con el motivo— y los revisores ven en la campana lo que deben
decidir.

Se crean dentro de la transacción de la acción que las origina y no hacen
commit: el commit lo hace quien las llama.
"""
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import (
    Cargo,
    EstadoSolicitud,
    Rol,
    TipoNotificacion,
    rol_reserva_de,
)
from app.models.modelos import (
    Espacio,
    Notificacion,
    Solicitud,
    Usuario,
    espacio_aprobador,
)
from app.utils.fechas import ZONA_COLOMBIA

# Cómo se nombra el cargo en los avisos
CARGO_LEGIBLE = {
    Cargo.ESTUDIANTE: "Estudiante",
    Cargo.DOCENTE: "Docente",
    Cargo.ADMINISTRATIVO: "Administrativo",
    Cargo.COORDINADOR_LABORATORIOS: "Coordinador de laboratorios",
    Cargo.ADMINISTRADOR_SALA: "Administrador de sala",
    Cargo.ADMINISTRADOR_SISTEMA: "Administrador del sistema",
}

# Avisos que piden una acción de revisión: se retiran cuando la solicitud ya se decidió
TIPOS_ACCIONABLES = (
    TipoNotificacion.SOLICITUD_PENDIENTE,
    TipoNotificacion.SOLICITUD_POR_AUTORIZAR,
)


class ErrorNotificacion(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def crear(
    db: Session,
    *,
    usuario_id: int,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
    solicitud_id: int | None = None,
) -> Notificacion:
    notificacion = Notificacion(
        usuario_id=usuario_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        solicitud_id=solicitud_id,
    )
    db.add(notificacion)
    db.flush()
    return notificacion


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def _cuando(solicitud: Solicitud) -> str:
    """«el 03/11/2026 de 08:00 a 10:00», en hora de Colombia."""
    inicio = solicitud.inicio.astimezone(ZONA_COLOMBIA)
    fin = solicitud.fin.astimezone(ZONA_COLOMBIA)
    return f"el {inicio:%d/%m/%Y} de {inicio:%H:%M} a {fin:%H:%M}"


def _cargo_legible(usuario: Usuario) -> str:
    return CARGO_LEGIBLE.get(usuario.cargo, "Solicitante")


def _salida(notificacion: Notificacion) -> dict:
    return {
        "id": notificacion.id,
        "tipo": notificacion.tipo,
        "titulo": notificacion.titulo,
        "mensaje": notificacion.mensaje,
        "solicitud_id": notificacion.solicitud_id,
        "leida": notificacion.leida,
        "creada_en": _local(notificacion.creada_en),
        "detalle": None,
    }


def _detalles_de_solicitud(db: Session, ids: list[int]) -> dict[int, dict]:
    """Datos del espacio, el horario y quien pide, para decidir sin salir del aviso."""
    if not ids:
        return {}
    filas = db.execute(
        select(Solicitud, Espacio, Usuario)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .join(Usuario, Usuario.id == Solicitud.solicitante_id)
        .where(Solicitud.id.in_(ids))
    ).all()

    detalles: dict[int, dict] = {}
    for solicitud, espacio, solicitante in filas:
        inicio = solicitud.inicio.astimezone(ZONA_COLOMBIA)
        detalles[solicitud.id] = {
            "solicitud_id": solicitud.id,
            "estado": solicitud.estado,
            "espacio_id": espacio.id,
            "espacio": espacio.nombre,
            "tipo_espacio": espacio.tipo,
            "fecha": inicio.date(),
            "inicio": inicio,
            "fin": solicitud.fin.astimezone(ZONA_COLOMBIA),
            "motivo_urgencia": solicitud.motivo_urgencia,
            "motivo_rechazo": solicitud.motivo_rechazo,
            "solicitante": solicitante.nombre,
            "rol_solicitante": rol_reserva_de(solicitante.cargo),
        }
    return detalles


def listar(
    db: Session,
    usuario: Usuario,
    *,
    solo_no_leidas: bool = False,
    limite: int = 50,
) -> list[dict]:
    consulta = select(Notificacion).where(Notificacion.usuario_id == usuario.id)
    if solo_no_leidas:
        consulta = consulta.where(Notificacion.leida.is_(False))
    filas = list(
        db.scalars(
            consulta.order_by(Notificacion.creada_en.desc(), Notificacion.id.desc()).limit(limite)
        )
    )

    ids = [notificacion.solicitud_id for notificacion in filas if notificacion.solicitud_id]
    detalles = _detalles_de_solicitud(db, ids)

    salida = []
    for notificacion in filas:
        item = _salida(notificacion)
        if notificacion.solicitud_id:
            item["detalle"] = detalles.get(notificacion.solicitud_id)
        salida.append(item)
    return salida


def contar_no_leidas(db: Session, usuario: Usuario) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notificacion)
            .where(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False))
        )
        or 0
    )


def marcar_leida(db: Session, usuario: Usuario, notificacion_id: int) -> dict:
    notificacion = db.scalar(
        select(Notificacion).where(
            Notificacion.id == notificacion_id, Notificacion.usuario_id == usuario.id
        )
    )
    if notificacion is None:
        raise ErrorNotificacion(404, "La notificación no existe")
    notificacion.leida = True
    db.commit()
    db.refresh(notificacion)
    return _salida(notificacion)


def marcar_todas_leidas(db: Session, usuario: Usuario) -> int:
    pendientes = list(
        db.scalars(
            select(Notificacion).where(
                Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False)
            )
        )
    )
    for notificacion in pendientes:
        notificacion.leida = True
    db.commit()
    return len(pendientes)


# --------------------------------------------------------------------------- #
# Avisos del flujo de solicitudes
# --------------------------------------------------------------------------- #


def _revisores(db: Session, espacio_id: int, excluir_id: int) -> list[Usuario]:
    """Quien puede decidir sobre el espacio: sus aprobadores y los administradores."""
    asignado = espacio_aprobador.c.usuario_id.isnot(None)
    return list(
        db.scalars(
            select(Usuario)
            .outerjoin(
                espacio_aprobador,
                and_(
                    espacio_aprobador.c.usuario_id == Usuario.id,
                    espacio_aprobador.c.espacio_id == espacio_id,
                ),
            )
            .where(
                Usuario.activo.is_(True),
                Usuario.id != excluir_id,
                or_(
                    Usuario.rol == Rol.ADMIN,
                    and_(Usuario.rol == Rol.APROBADOR, asignado),
                ),
            )
            .order_by(Usuario.id)
        )
    )


def notificar_revisores(
    db: Session, solicitud: Solicitud, espacio: Espacio, solicitante: Usuario
) -> int:
    """Avisa a los aprobadores del espacio (y a los administradores) que hay algo por decidir."""
    mensaje = (
        f"{solicitante.nombre} ({_cargo_legible(solicitante)}) solicitó {espacio.nombre} "
        f"{_cuando(solicitud)}. Revisa la solicitud #{solicitud.id}."
    )
    revisores = _revisores(db, espacio.id, solicitante.id)
    for revisor in revisores:
        crear(
            db,
            usuario_id=revisor.id,
            tipo=TipoNotificacion.SOLICITUD_PENDIENTE,
            titulo="Solicitud pendiente por revisar",
            mensaje=mensaje,
            solicitud_id=solicitud.id,
        )
    return len(revisores)


def notificar_autorizadores(
    db: Session, solicitud: Solicitud, espacio: Espacio, solicitante: Usuario
) -> int:
    """Avisa a quienes pueden autorizar horarios fuera de la franja (HU-35)."""
    mensaje = (
        f"{solicitante.nombre} ({_cargo_legible(solicitante)}) pidió {espacio.nombre} "
        f"{_cuando(solicitud)}, fuera de la franja de operación. "
        f"Revisa la solicitud #{solicitud.id}."
    )
    autorizadores = list(
        db.scalars(
            select(Usuario).where(
                Usuario.activo.is_(True),
                Usuario.id != solicitante.id,
                Usuario.puede_autorizar_especial.is_(True),
            )
        )
    )
    for autorizador in autorizadores:
        crear(
            db,
            usuario_id=autorizador.id,
            tipo=TipoNotificacion.SOLICITUD_POR_AUTORIZAR,
            titulo="Solicitud fuera de la franja por autorizar",
            mensaje=mensaje,
            solicitud_id=solicitud.id,
        )
    return len(autorizadores)


def notificar_recibida(db: Session, solicitud: Solicitud, espacio: Espacio) -> Notificacion:
    """Confirmación al solicitante de que su solicitud quedó registrada."""
    if solicitud.estado == EstadoSolicitud.PENDIENTE:
        detalle_estado = "quedó pendiente de aprobación"
    elif solicitud.estado == EstadoSolicitud.PENDIENTE_AUTORIZACION:
        detalle_estado = "quedó pendiente de autorización especial por estar fuera de la franja"
    elif solicitud.estado == EstadoSolicitud.EN_ESPERA_CESION:
        detalle_estado = "quedó en espera de que el titular decida si cede el cupo"
    else:
        detalle_estado = f"quedó en estado {solicitud.estado.value}"

    return crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=TipoNotificacion.SOLICITUD_RECIBIDA,
        titulo=f"Solicitud #{solicitud.id} recibida",
        mensaje=(
            f"Tu solicitud para {espacio.nombre} {_cuando(solicitud)} {detalle_estado}. "
            "Te avisaremos aquí cuando haya una decisión."
        ),
        solicitud_id=solicitud.id,
    )


def notificar_aprobada(
    db: Session, solicitud: Solicitud, espacio: Espacio, reserva_id: int
) -> Notificacion:
    return crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=TipoNotificacion.SOLICITUD_APROBADA,
        titulo=f"Solicitud #{solicitud.id} aprobada",
        mensaje=(
            f"Tu solicitud para {espacio.nombre} {_cuando(solicitud)} fue aprobada. "
            f"Se creó la reserva #{reserva_id} a tu nombre."
        ),
        solicitud_id=solicitud.id,
    )


def notificar_rechazada(
    db: Session, solicitud: Solicitud, espacio: Espacio, motivo: str
) -> Notificacion:
    return crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=TipoNotificacion.SOLICITUD_RECHAZADA,
        titulo=f"Solicitud #{solicitud.id} rechazada",
        mensaje=(
            f"Tu solicitud para {espacio.nombre} {_cuando(solicitud)} fue rechazada. "
            f"Motivo: {motivo}"
        ),
        solicitud_id=solicitud.id,
    )


def notificar_autorizacion(
    db: Session,
    solicitud: Solicitud,
    espacio: Espacio,
    *,
    concedida: bool,
    motivo: str | None = None,
) -> Notificacion:
    if concedida:
        titulo = f"Autorización especial concedida para la solicitud #{solicitud.id}"
        mensaje = (
            f"Tu solicitud para {espacio.nombre} {_cuando(solicitud)} fue autorizada. "
            "Ahora pasa a revisión para la aprobación final."
        )
        tipo = TipoNotificacion.AUTORIZACION_CONCEDIDA
    else:
        titulo = f"Autorización especial negada para la solicitud #{solicitud.id}"
        mensaje = (
            f"Tu solicitud para {espacio.nombre} {_cuando(solicitud)} fue rechazada: "
            f"la autorización especial fue negada. Motivo: {motivo}"
        )
        tipo = TipoNotificacion.AUTORIZACION_DENEGADA

    return crear(
        db,
        usuario_id=solicitud.solicitante_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        solicitud_id=solicitud.id,
    )


def descartar_previos(db: Session, solicitud_id: int) -> None:
    """Retira los avisos que ya no aportan cuando la solicitud se decide.

    Incluye los de revisión (ya no hay nada que decidir) y la confirmación de
    recibida (el aviso del resultado la reemplaza).
    """
    db.execute(
        delete(Notificacion).where(
            Notificacion.solicitud_id == solicitud_id,
            Notificacion.tipo.in_(
                TIPOS_ACCIONABLES + (TipoNotificacion.SOLICITUD_RECIBIDA,)
            ),
        )
    )
    db.flush()
