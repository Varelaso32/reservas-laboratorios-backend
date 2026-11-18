"""Recursos tecnológicos asociados a una reserva (HU-43 a HU-46).

- HU-43: inventario administrado por el Administrador del Sistema.
- HU-44: solicitud de recursos ligada a una reserva propia ACTIVA.
- HU-45: aprobación por orden de llegada y asignación atómica de unidades.
- HU-46: entrega, devolución y penalización por retraso.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import EstadoAsignacion, EstadoSolicitudRecurso, Rol
from app.models.modelos import Usuario
from app.schemas.recurso import (
    AmenidadOut,
    DecisionSolicitudRecursoIn,
    DevolucionIn,
    DisponibilidadOut,
    HistorialRecursoOut,
    ProcesarRetrasosOut,
    RecursoActualizar,
    RecursoCrear,
    RecursoEstadoIn,
    RecursoOut,
    ReservaElegibleOut,
    SolicitudRecursoCrear,
    SolicitudRecursoOut,
    StockTipoOut,
    TipoRecursoActualizar,
    TipoRecursoCrear,
    TipoRecursoOut,
)
from app.services import recursos

router = APIRouter()

_401 = {401: {"description": "No autenticado"}}
_403 = {403: {"description": "Solo el Administrador del Sistema"}}
_404 = {404: {"description": "El recurso, la unidad o la solicitud no existe"}}
_409 = {
    409: {
        "description": (
            "Conflicto: identificador repetido, sin stock, reserva no confirmada, "
            "solicitud ya decidida o unidad con préstamo vigente"
        )
    }
}
_422 = {422: {"description": "Datos inválidos o cantidad mayor a la disponible"}}


def _ejecutar(db: Session, accion, *args):
    try:
        return accion(db, *args)
    except recursos.ErrorRecurso as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


# --------------------------------------------------------------------------- #
# HU-43: tipos de recurso e inventario
# --------------------------------------------------------------------------- #
@router.get(
    "/tipos",
    response_model=list[TipoRecursoOut],
    summary="Catálogo de tipos de recurso con su stock",
    description=(
        "**HU-43.** Devuelve los tipos de recurso con el total de unidades, las disponibles, "
        "las prestadas, las reservadas y las fallidas. Cualquier usuario con sesión puede "
        "consultarlo; `solo_activos` oculta los tipos desactivados."
    ),
    responses={**_401},
)
def listar_tipos(
    solo_activos: bool = Query(False, description="Ocultar los tipos desactivados"),
    _usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return recursos.listar_tipos(db, solo_activos)


@router.post(
    "/tipos",
    response_model=TipoRecursoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un tipo de recurso",
    description="**HU-43.** Solo el Administrador del Sistema. El nombre debe ser único.",
    responses={**_401, **_403, **_409, **_422},
)
def crear_tipo(
    datos: TipoRecursoCrear,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.crear_tipo, admin, datos)


@router.patch(
    "/tipos/{tipo_id}",
    response_model=TipoRecursoOut,
    summary="Actualizar un tipo de recurso",
    description=(
        "**HU-43.** Solo el Administrador del Sistema. Permite renombrar, cambiar la "
        "descripción o desactivar el tipo."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def actualizar_tipo(
    tipo_id: int,
    datos: TipoRecursoActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.actualizar_tipo, admin, tipo_id, datos)


@router.get(
    "/amenidades",
    response_model=list[AmenidadOut],
    summary="Catálogo de amenidades con su stock",
    description=(
        "**HU-19 / HU-43.** Devuelve los recursos que se pueden instalar en un espacio con "
        "cuántas unidades quedan libres. Si se envía `espacio_id`, marca con "
        "`instalado_aqui` las que ya tiene ese espacio."
    ),
    responses={**_401, **_403},
)
def listar_amenidades(
    espacio_id: int | None = Query(
        None, description="Espacio cuyas amenidades actuales se quieren marcar"
    ),
    _usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return recursos.listar_amenidades(db, espacio_id)


@router.get(
    "/stock",
    response_model=list[StockTipoOut],
    summary="Stock por tipo de recurso",
    description=(
        "**HU-43.** Stock global por tipo: total, instalados en espacios, disponibles, "
        "prestados, reservados y fallidos. Para el stock en el horario de una reserva usa "
        "`/recursos/disponibilidad`."
    ),
    responses={**_401},
)
def stock(
    _usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return recursos.stock_por_tipo(db)


@router.get(
    "/inventario",
    response_model=list[RecursoOut],
    summary="Inventario de unidades",
    description=(
        "**HU-43.** Lista las unidades con su etiqueta física y estado. Solo el Administrador "
        "del Sistema. Por defecto incluye también las unidades dadas de baja."
    ),
    responses={**_401, **_403},
)
def listar_inventario(
    tipo_recurso_id: int | None = Query(None, description="Filtrar por tipo"),
    solo_activos: bool = Query(False, description="Ocultar las unidades dadas de baja"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return recursos.listar_inventario(db, tipo_recurso_id, solo_activos)


@router.post(
    "/",
    response_model=RecursoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una unidad del inventario",
    description=(
        "**HU-43.** Solo el Administrador del Sistema. El identificador corresponde a la "
        "etiqueta física y no puede repetirse. La unidad queda en estado En funcionamiento."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def crear_recurso(
    datos: RecursoCrear,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.crear_recurso, admin, datos)


@router.get(
    "/{recurso_id}/historial",
    response_model=list[HistorialRecursoOut],
    summary="Historial de una unidad",
    description=(
        "**HU-46.** Quién tuvo la unidad, desde cuándo y cuándo la devolvió. "
        "Solo el Administrador del Sistema."
    ),
    responses={**_401, **_403, **_404},
)
def historial_recurso(
    recurso_id: int,
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.historial_recurso, recurso_id)


@router.patch(
    "/{recurso_id}",
    response_model=RecursoOut,
    summary="Actualizar una unidad",
    description=(
        "**HU-43.** Solo el Administrador del Sistema. Cambia tipo, etiqueta, descripción, "
        "espacio fijo o da de baja la unidad. No se puede dar de baja con un préstamo vigente."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def actualizar_recurso(
    recurso_id: int,
    datos: RecursoActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.actualizar_recurso, admin, recurso_id, datos)


@router.patch(
    "/{recurso_id}/estado",
    response_model=RecursoOut,
    summary="Cambiar el estado de una unidad",
    description=(
        "**HU-43.** Solo el Administrador del Sistema. Pasa la unidad a En funcionamiento o "
        "Fallido con un comentario obligatorio. Una unidad fallida no se asigna (HU-45)."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def cambiar_estado_recurso(
    recurso_id: int,
    datos: RecursoEstadoIn,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.cambiar_estado_recurso, admin, recurso_id, datos)


# --------------------------------------------------------------------------- #
# HU-44: solicitudes
# --------------------------------------------------------------------------- #
@router.get(
    "/disponibilidad",
    response_model=DisponibilidadOut,
    summary="Recursos disponibles en el horario de una reserva",
    description=(
        "**HU-44.** Muestra, por tipo, cuántas unidades están disponibles en el horario exacto "
        "de la reserva. El solicitante solo puede consultar sus propias reservas; el "
        "Administrador del Sistema puede consultar cualquiera."
    ),
    responses={**_401, **_404},
)
def disponibilidad(
    reserva_id: int = Query(gt=0, description="Reserva a consultar"),
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.disponibilidad_para, usuario, reserva_id)


@router.get(
    "/reservas-elegibles",
    response_model=list[ReservaElegibleOut],
    summary="Mis reservas para solicitar recursos",
    description=(
        "**HU-44.** Reservas propias ACTIVAS que aún no terminan. Solo Docente, Coordinador y "
        "Director pueden pedir recursos; un Estudiante recibe una lista vacía."
    ),
    responses={**_401},
)
def reservas_elegibles(
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return recursos.reservas_elegibles(db, usuario)


@router.post(
    "/solicitudes",
    response_model=SolicitudRecursoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar recursos para una reserva",
    description=(
        "**HU-44.** Docente, Coordinador o Director piden tipos y cantidades para una reserva "
        "propia ACTIVA. El horario es el de la reserva y no se edita. La solicitud queda "
        "PENDIENTE y se avisa a los administradores. Un usuario bloqueado por strikes no puede "
        "solicitar."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def crear_solicitud(
    datos: SolicitudRecursoCrear,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.crear_solicitud, usuario, datos)


@router.get(
    "/solicitudes/mias",
    response_model=list[SolicitudRecursoOut],
    summary="Mis solicitudes de recursos",
    description="**HU-44.** Solicitudes de recursos del usuario autenticado, en orden de llegada.",
    responses={**_401},
)
def mis_solicitudes(
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return recursos.listar_solicitudes(db, usuario_id=usuario.id)


@router.get(
    "/solicitudes",
    response_model=list[SolicitudRecursoOut],
    summary="Solicitudes de recursos pendientes e historial",
    description=(
        "**HU-45.** Solo el Administrador del Sistema. Devuelve las solicitudes en orden de "
        "llegada; con `estado` filtra por estado. El barrido de devoluciones tardías se "
        "ejecuta antes de responder."
    ),
    responses={**_401, **_403},
)
def listar_solicitudes(
    estado: EstadoSolicitudRecurso | None = Query(None, description="Filtrar por estado"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    recursos.procesar_retrasos(db)
    return recursos.listar_solicitudes(db, estado)


@router.post(
    "/solicitudes/{solicitud_id}/decision",
    response_model=SolicitudRecursoOut,
    summary="Aprobar o rechazar una solicitud de recursos",
    description=(
        "**HU-45.** Solo el Administrador del Sistema. Al aprobar verifica el stock en "
        "funcionamiento en el horario de la reserva, asigna unidades concretas y descuenta el "
        "stock de forma atómica. Al rechazar, el motivo es obligatorio."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def decidir_solicitud(
    solicitud_id: int,
    datos: DecisionSolicitudRecursoIn,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.decidir_solicitud, admin, solicitud_id, datos)


# --------------------------------------------------------------------------- #
# HU-46: préstamos, entrega y devolución
# --------------------------------------------------------------------------- #
@router.get(
    "/asignaciones",
    response_model=list[HistorialRecursoOut],
    summary="Préstamos de recursos",
    description=(
        "**HU-46.** Solo el Administrador del Sistema. Muestra quién tiene cada unidad, desde "
        "cuándo y su hora límite de devolución. `solo_vigentes` deja únicamente las asignadas o "
        "entregadas. El barrido de retrasos se ejecuta antes de responder."
    ),
    responses={**_401, **_403},
)
def listar_asignaciones(
    estado: EstadoAsignacion | None = Query(None, description="Filtrar por estado"),
    solo_vigentes: bool = Query(False, description="Solo asignadas o entregadas"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    recursos.procesar_retrasos(db)
    return recursos.listar_asignaciones(db, estado, solo_vigentes)


@router.post(
    "/asignaciones/{asignacion_id}/entrega",
    response_model=SolicitudRecursoOut,
    summary="Registrar la entrega de una unidad",
    description=(
        "**HU-46.** Solo el Administrador del Sistema. Registra que la unidad salió del "
        "inventario hacia el titular de la reserva, con la hora de entrega."
    ),
    responses={**_401, **_403, **_404, **_409},
)
def registrar_entrega(
    asignacion_id: int,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.registrar_entrega, admin, asignacion_id)


@router.post(
    "/asignaciones/{asignacion_id}/devolucion",
    response_model=SolicitudRecursoOut,
    summary="Registrar la devolución de una unidad",
    description=(
        "**HU-46.** Solo el Administrador del Sistema. La unidad vuelve al inventario con el "
        "estado y comentario indicados. Si la devolución es tardía, antes se generan los "
        "strikes dobles correspondientes."
    ),
    responses={**_401, **_403, **_404, **_409, **_422},
)
def registrar_devolucion(
    asignacion_id: int,
    datos: DevolucionIn,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.registrar_devolucion, admin, asignacion_id, datos)


@router.post(
    "/procesar-retrasos",
    response_model=ProcesarRetrasosOut,
    summary="Procesar devoluciones tardías",
    description=(
        "**HU-46.** Barrido perezoso: notifica al titular y genera los strikes dobles de las "
        "unidades cuya hora límite ya venció. Se ejecuta también al consultar solicitudes y "
        "préstamos, así que no depende de un cron externo."
    ),
    responses={**_401, **_403},
)
def procesar_retrasos(
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, recursos.procesar_retrasos)
