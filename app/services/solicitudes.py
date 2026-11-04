"""Creación y consulta de solicitudes (HU-04, HU-05, HU-21, HU-28 a HU-35)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    JERARQUIA_RESERVA,
    AccionTrazabilidad,
    EstadoSolicitud,
    rol_reserva_de,
)
from app.models.modelos import Espacio, Solicitud, TipoUso, Usuario
from app.schemas.solicitud import SolicitudCrear
from app.services import (
    asistencia,
    cesion,
    disponibilidad,
    notificaciones,
    reglas,
    sanciones,
    trazabilidad,
)
from app.utils.fechas import ZONA_COLOMBIA


class ErrorSolicitud(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def a_salida(
    solicitud: Solicitud,
    espacio_nombre: str,
    tipo_uso: str | None = None,
    responsable: str | None = None,
    fuera_de_franja: bool = False,
) -> dict:
    def local(fecha):
        return fecha.astimezone(ZONA_COLOMBIA) if fecha else None

    return {
        "id": solicitud.id,
        "espacio_id": solicitud.espacio_id,
        "espacio_nombre": espacio_nombre,
        "inicio": local(solicitud.inicio),
        "fin": local(solicitud.fin),
        "proposito": solicitud.proposito,
        "asistentes": solicitud.asistentes,
        "equipamiento": solicitud.equipamiento,
        "estado": solicitud.estado,
        "tipo_uso": tipo_uso,
        "responsable": responsable,
        "fuera_de_franja": fuera_de_franja,
        "motivo_urgencia": solicitud.motivo_urgencia,
        "motivo_rechazo": solicitud.motivo_rechazo,
        "fecha_decision": local(solicitud.fecha_decision),
        "creada_en": local(solicitud.creada_en),
    }


def crear(db: Session, usuario: Usuario, datos: SolicitudCrear) -> dict:
    # HU-39 / HU-40: primero se ponen al día los no-show y luego se verifica el bloqueo
    asistencia.procesar_vencidas(db)
    if sanciones.esta_bloqueado(db, usuario):
        raise ErrorSolicitud(403, sanciones.mensaje_bloqueo(db, usuario))

    # HU-12: la prioridad se fija con el rol de reserva de quien solicita y
    # queda asociada a la solicitud para ordenar la bandeja del aprobador.
    prioridad = JERARQUIA_RESERVA.index(rol_reserva_de(usuario.cargo))

    # Bloquea la fila del espacio hasta el commit: si llegan dos solicitudes al
    # mismo tiempo (doble clic), la segunda espera y ve la primera.
    espacio = db.scalar(select(Espacio).where(Espacio.id == datos.espacio_id).with_for_update())
    if espacio is None or not espacio.activo:
        raise ErrorSolicitud(404, "El espacio no existe o no está activo")

    inicio = datetime.combine(datos.fecha, datos.hora_inicio, ZONA_COLOMBIA)
    fin = datetime.combine(datos.fecha, datos.hora_fin, ZONA_COLOMBIA)
    if fin <= inicio:
        raise ErrorSolicitud(422, "La hora de fin debe ser mayor que la hora de inicio")
    if inicio < datetime.now(ZONA_COLOMBIA):
        raise ErrorSolicitud(422, "No se puede solicitar un espacio en una fecha u hora pasada")

    if datos.asistentes > espacio.capacidad:
        raise ErrorSolicitud(
            422, f"La cantidad de asistentes ({datos.asistentes}) supera la capacidad del espacio ({espacio.capacidad})"
        )

    # HU-30: ¿el horario coincide con el cupo vigente de otro usuario?
    cupo = cesion.buscar_titular(db, espacio.id, inicio, fin, usuario.id)

    # HU-05: una reserva propia que se cruza no es una cesión, es un choque directo.
    if cupo is None and not disponibilidad.esta_disponible(db, espacio.id, inicio, fin):
        raise ErrorSolicitud(409, "El espacio ya está ocupado en ese horario")

    # SCRUM-212: una solicitud PENDIENTE de cualquier usuario también bloquea el horario.
    # El FOR UPDATE del espacio (arriba) evita que dos solicitudes simultáneas pasen las dos.
    # No aplica cuando hay un cupo en juego (HU-30): ese conflicto lo resuelve la cesión.
    if cupo is None:
        pendiente = db.execute(
            select(Solicitud.id, Solicitud.solicitante_id)
            .where(
                Solicitud.espacio_id == espacio.id,
                Solicitud.estado.in_(
                    (
                        EstadoSolicitud.PENDIENTE,
                        EstadoSolicitud.PENDIENTE_AUTORIZACION,
                        EstadoSolicitud.EN_ESPERA_CESION,
                    )
                ),
                Solicitud.inicio < fin,
                Solicitud.fin > inicio,
            )
            .limit(1)
        ).first()
        if pendiente:
            # A otro usuario no se le muestra el número de una solicitud que no es suya
            if pendiente.solicitante_id == usuario.id:
                mensaje = (
                    f"Ya tienes una solicitud pendiente (#{pendiente.id}) para ese espacio "
                    "en un horario que se cruza"
                )
            else:
                mensaje = "El espacio ya tiene una solicitud pendiente en ese horario"
            raise ErrorSolicitud(409, mensaje)

    # HU-21, HU-28, HU-29, HU-32, HU-33, HU-34 y HU-35
    try:
        validacion = reglas.validar_creacion(
            db, usuario, espacio, datos, inicio, fin, conflicto_autorizado=cupo is not None
        )
    except reglas.ErrorRegla as error:
        raise ErrorSolicitud(error.codigo, error.mensaje) from error

    # Fuera de franja manda la autorización especial (HU-35): la cesión de cupo
    # se resuelve cuando la solicitud ya esté dentro de la operación normal.
    if validacion.estado == EstadoSolicitud.PENDIENTE_AUTORIZACION:
        cupo = None

    if cupo is not None:
        try:
            evaluacion = cesion.evaluar(usuario, cupo, datos.motivo_urgencia)
        except cesion.ErrorCesion as error:
            raise ErrorSolicitud(error.codigo, error.mensaje) from error

        if evaluacion.rechazo is not None:
            return _rechazar_por_conflicto(
                db, usuario, espacio, datos, inicio, fin, validacion, cupo, evaluacion.rechazo
            )

    estado = EstadoSolicitud.EN_ESPERA_CESION if cupo is not None else validacion.estado
    avisos = list(validacion.avisos)

    solicitud = Solicitud(
        solicitante_id=usuario.id,
        espacio_id=espacio.id,
        inicio=inicio,
        fin=fin,
        proposito=datos.proposito,
        asistentes=datos.asistentes,
        equipamiento=datos.equipamiento,
        estado=estado,
        tipo_uso_id=validacion.tipo_uso.id if validacion.tipo_uso else None,
        responsable_id=validacion.responsable.id if validacion.responsable else None,
        motivo_urgencia=datos.motivo_urgencia if cupo is not None else None,
        titular_id=cupo.usuario.id if cupo is not None else None,
        prioridad=prioridad,
    )
    db.add(solicitud)
    db.flush()

    if cupo is not None:
        avisos.append(
            f"El horario está ocupado por {cupo.usuario.nombre}. Tu solicitud quedó en espera "
            "de que decida si cede el cupo."
        )

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CREADA,
        estado_nuevo=estado.value,
        detalle="; ".join(avisos) or None,
    )

    if cupo is not None:
        trazabilidad.registrar(
            db,
            solicitud_id=solicitud.id,
            usuario_id=usuario.id,
            accion=AccionTrazabilidad.CESION_SOLICITADA,
            estado_nuevo=estado.value,
            detalle=(
                f"Cupo de {cupo.usuario.nombre} solicitado por jerarquía. "
                f"Motivo de urgencia: {datos.motivo_urgencia}"
            ),
        )
        cesion.notificar_solicitud(db, solicitud, espacio, cupo.usuario, usuario)

    # Campana de notificaciones: el solicitante sabe en qué quedó y los
    # revisores ven lo que deben decidir (HU-10, HU-11, HU-35).
    if estado == EstadoSolicitud.PENDIENTE:
        notificaciones.notificar_revisores(db, solicitud, espacio, usuario)
    elif estado == EstadoSolicitud.PENDIENTE_AUTORIZACION:
        notificaciones.notificar_autorizadores(db, solicitud, espacio, usuario)
    notificaciones.notificar_recibida(db, solicitud, espacio)

    db.commit()
    db.refresh(solicitud)

    salida = a_salida(
        solicitud,
        espacio.nombre,
        tipo_uso=validacion.tipo_uso.nombre if validacion.tipo_uso else None,
        responsable=validacion.responsable.nombre if validacion.responsable else None,
        fuera_de_franja=estado == EstadoSolicitud.PENDIENTE_AUTORIZACION,
    )
    if cupo is not None:
        salida["titular"] = cupo.usuario.nombre
    salida["avisos"] = avisos
    return salida


def _rechazar_por_conflicto(
    db: Session,
    usuario: Usuario,
    espacio: Espacio,
    datos: SolicitudCrear,
    inicio: datetime,
    fin: datetime,
    validacion: reglas.Validacion,
    cupo: cesion.Cupo,
    motivo: str,
) -> dict:
    """HU-30, criterio 4: rechazo automático cuando la jerarquía no alcanza.

    Se guarda la solicitud rechazada para que el solicitante vea el motivo en
    «Mis solicitudes» y para que el conflicto quede en la trazabilidad (criterio 8).
    """
    solicitud = Solicitud(
        solicitante_id=usuario.id,
        espacio_id=espacio.id,
        inicio=inicio,
        fin=fin,
        proposito=datos.proposito,
        asistentes=datos.asistentes,
        equipamiento=datos.equipamiento,
        estado=EstadoSolicitud.RECHAZADA,
        decidido_por=usuario.id,
        fecha_decision=datetime.now(ZONA_COLOMBIA),
        motivo_rechazo=motivo,
        tipo_uso_id=validacion.tipo_uso.id if validacion.tipo_uso else None,
        responsable_id=validacion.responsable.id if validacion.responsable else None,
        titular_id=cupo.usuario.id,
        prioridad=JERARQUIA_RESERVA.index(rol_reserva_de(usuario.cargo)),
    )
    db.add(solicitud)
    db.flush()

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CREADA,
        estado_nuevo=EstadoSolicitud.RECHAZADA.value,
        detalle="Solicitud rechazada automáticamente por conflicto de cupo",
    )
    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CONFLICTO_RECHAZADO,
        estado_nuevo=EstadoSolicitud.RECHAZADA.value,
        detalle=motivo,
    )
    notificaciones.notificar_rechazada(db, solicitud, espacio, motivo)
    db.commit()
    db.refresh(solicitud)

    salida = a_salida(
        solicitud,
        espacio.nombre,
        tipo_uso=validacion.tipo_uso.nombre if validacion.tipo_uso else None,
        responsable=validacion.responsable.nombre if validacion.responsable else None,
    )
    salida["titular"] = cupo.usuario.nombre
    salida["avisos"] = [motivo]
    return salida


def listar_del_usuario(db: Session, usuario: Usuario, estado: EstadoSolicitud | None = None) -> list[dict]:
    consulta = (
        select(Solicitud, Espacio, TipoUso.nombre, Usuario.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .outerjoin(TipoUso, TipoUso.id == Solicitud.tipo_uso_id)
        .outerjoin(Usuario, Usuario.id == Solicitud.responsable_id)
        .where(Solicitud.solicitante_id == usuario.id)
    )
    if estado is not None:
        consulta = consulta.where(Solicitud.estado == estado)
    filas = db.execute(consulta.order_by(Solicitud.creada_en.desc(), Solicitud.id.desc())).all()
    return [
        a_salida(
            solicitud,
            espacio.nombre,
            tipo_uso=tipo_uso_nombre,
            responsable=responsable_nombre,
            fuera_de_franja=_fuera_de_franja(solicitud, espacio),
        )
        for solicitud, espacio, tipo_uso_nombre, responsable_nombre in filas
    ]


def _fuera_de_franja(solicitud: Solicitud, espacio: Espacio) -> bool:
    inicio = solicitud.inicio.astimezone(ZONA_COLOMBIA)
    fin = solicitud.fin.astimezone(ZONA_COLOMBIA)
    return reglas.fuera_de_franja(espacio, inicio.date(), inicio.time(), fin.time()) is not None

