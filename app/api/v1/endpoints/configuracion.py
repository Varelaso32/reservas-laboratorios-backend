"""Configuración de reglas: tipos de uso, reglas por espacio y anticipación por rol.

HU-21, HU-22, HU-32, HU-35, HU-36 y HU-37.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import Rol, RolReserva, rol_reserva_de
from app.models.modelos import Usuario
from app.schemas.configuracion import (
    AnticipacionActualizar,
    AnticipacionOut,
    ReglasEspacioActualizar,
    ReglasEspacioOut,
    ReglasPorTipoIn,
    ResponsableOut,
    TipoUsoActualizar,
    TipoUsoCrear,
    TipoUsoOut,
)
from app.schemas.sancion import ParametroSancionActualizar, ParametroSancionOut
from app.services import configuracion, reglas, sanciones

router = APIRouter()

_401 = {401: {"description": "No autenticado"}}
_403 = {403: {"description": "Solo el Administrador del Sistema puede cambiar la configuración"}}
_404 = {404: {"description": "El recurso no existe"}}
_409 = {409: {"description": "Nombre de tipo de uso duplicado"}}
_422 = {422: {"description": "Datos inválidos"}}


def _ejecutar(db: Session, accion, *args):
    try:
        return accion(db, *args)
    except configuracion.ErrorConfiguracion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


# --------------------------------------------------------------------------- #
# Tipos de uso (HU-22)
# --------------------------------------------------------------------------- #
@router.get(
    "/tipos-uso",
    response_model=list[TipoUsoOut],
    summary="Listar tipos de uso",
    description=(
        "**HU-22.** Catálogo de actividades que se pueden asociar a un espacio. Por defecto "
        "solo devuelve los activos, que son los que aparecen en el formulario de solicitud. "
        "El ADMIN puede pedir también los inactivos con `incluir_inactivos=true`."
    ),
    response_description="Tipos de uso ordenados por nombre",
    responses={**_401},
)
def listar_tipos_uso(
    incluir_inactivos: bool = Query(False, description="Incluir los tipos desactivados"),
    _usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return configuracion.listar_tipos_uso(db, incluir_inactivos)


@router.post(
    "/tipos-uso",
    response_model=TipoUsoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un tipo de uso",
    description="**HU-22.** Solo el ADMIN. El nombre debe ser único.",
    response_description="Tipo de uso creado",
    responses={**_401, **_403, **_409, **_422},
)
def crear_tipo_uso(
    datos: TipoUsoCrear,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.crear_tipo_uso, admin, datos)


@router.patch(
    "/tipos-uso/{tipo_id}",
    response_model=TipoUsoOut,
    summary="Actualizar un tipo de uso",
    description=(
        "**HU-22.** Solo el ADMIN. Se puede renombrar o desactivar. Un tipo desactivado deja de "
        "aparecer en el formulario, pero las solicitudes que ya lo usan lo conservan."
    ),
    response_description="Tipo de uso actualizado",
    responses={**_401, **_403, **_404, **_409, **_422},
)
def actualizar_tipo_uso(
    tipo_id: int,
    datos: TipoUsoActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.actualizar_tipo_uso, admin, tipo_id, datos)


# --------------------------------------------------------------------------- #
# Reglas del espacio (HU-21, HU-28, HU-33, HU-34, HU-36)
# --------------------------------------------------------------------------- #
@router.get(
    "/espacios/{espacio_id}",
    response_model=ReglasEspacioOut,
    summary="Consultar las reglas de un espacio",
    description=(
        "Devuelve la franja de operación, el máximo de usos por día, la duración máxima, la "
        "separación entre reservas, la ocupación mínima, si exige responsable, si admite "
        "autorización especial y las actividades configuradas.\n\n"
        "Lo usa el formulario de solicitud para avisar antes de enviar y la pantalla de "
        "administración para editarlas."
    ),
    response_description="Configuración vigente del espacio",
    responses={**_401, **_404},
)
def consultar_reglas_espacio(
    espacio_id: int,
    _usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.reglas_de, espacio_id)


@router.put(
    "/espacios/por-tipo",
    response_model=list[ReglasEspacioOut],
    summary="Aplicar reglas a todos los espacios de un tipo",
    description=(
        "**HU-36, criterio 5.** Solo el ADMIN. Copia las reglas enviadas a cada espacio del tipo "
        "indicado (por ejemplo, todos los laboratorios) y registra el cambio en la auditoría."
    ),
    response_description="Reglas resultantes de cada espacio",
    responses={**_401, **_403, **_404, **_422},
)
def aplicar_reglas_por_tipo(
    datos: ReglasPorTipoIn,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.aplicar_por_tipo, admin, datos.tipo, datos.reglas)


@router.put(
    "/espacios/{espacio_id}",
    response_model=ReglasEspacioOut,
    summary="Actualizar las reglas de un espacio",
    description=(
        "**HU-21, HU-28, HU-33, HU-34 y HU-36.** Solo el ADMIN. Solo cambian los campos "
        "enviados.\n\n"
        "- `hora_apertura` y `hora_cierre`: franja propia; envíalas juntas o en `null` para "
        "volver a la institucional (07:00 a 22:00).\n"
        "- `dias_operacion`: lista de 1 (lunes) a 7 (domingo).\n"
        "- `max_usos_dia`, `duracion_maxima_min`, `ocupacion_minima`: enteros positivos o `null` "
        "para quitar el límite.\n"
        "- `separacion_min`: minutos de separación entre reservas.\n"
        "- `tipos_uso_ids`: actividades permitidas; `[]` deja el espacio sin restricción.\n\n"
        "Los cambios aplican a las solicitudes nuevas; las reservas confirmadas no se tocan."
    ),
    response_description="Configuración vigente del espacio",
    responses={**_401, **_403, **_404, **_422},
)
def actualizar_reglas_espacio(
    espacio_id: int,
    datos: ReglasEspacioActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.actualizar_reglas, admin, espacio_id, datos)


@router.get(
    "/historial",
    summary="Historial de cambios de configuración",
    description=(
        "**HU-36.8 y HU-37.6.** Solo el ADMIN. Devuelve los últimos cambios con el usuario, la "
        "fecha y la hora. Se puede filtrar por espacio."
    ),
    response_description="Cambios de configuración, del más reciente al más antiguo",
    responses={**_401, **_403},
)
def historial_configuracion(
    espacio_id: int | None = Query(None, description="Filtrar por espacio"),
    limite: int = Query(50, ge=1, le=200, description="Cuántos registros devolver"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return configuracion.historial(db, espacio_id, limite)


@router.get(
    "/responsables",
    response_model=list[ResponsableOut],
    summary="Listar responsables posibles",
    description=(
        "**HU-32, criterio 6.** Usuarios activos con nivel de reserva Docente, Coordinador o "
        "Director, para elegirlos como responsable de una actividad."
    ),
    response_description="Responsables ordenados por nombre",
    responses={**_401},
)
def listar_responsables(
    _usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return [
        {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "cargo": usuario.cargo,
            "rol_reserva": rol_reserva_de(usuario.cargo),
        }
        for usuario in reglas.responsables_disponibles(db)
    ]


# --------------------------------------------------------------------------- #
# Anticipación por rol (HU-32, HU-37)
# --------------------------------------------------------------------------- #
@router.get(
    "/anticipacion",
    response_model=list[AnticipacionOut],
    summary="Consultar la anticipación máxima por rol",
    description=(
        "**HU-37.** Solo el ADMIN. Devuelve los cuatro roles de reserva (Estudiante, Docente, "
        "Coordinador y Director) con su anticipación en días; `null` significa sin límite."
    ),
    response_description="Anticipación configurada por rol",
    responses={**_401, **_403},
)
def consultar_anticipacion(
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return configuracion.listar_anticipacion(db)


@router.put(
    "/anticipacion/{rol}",
    response_model=AnticipacionOut,
    summary="Configurar la anticipación de un rol",
    description=(
        "**HU-37.** Solo el ADMIN. Envía `dias_maximos` como entero positivo, o `null` para "
        "dejar ese rol sin límite de anticipación. Aplica a las solicitudes nuevas."
    ),
    response_description="Anticipación resultante del rol",
    responses={**_401, **_403, **_422},
)
def actualizar_anticipacion(
    rol: RolReserva,
    datos: AnticipacionActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, configuracion.actualizar_anticipacion, admin, rol, datos.dias_maximos)


# --------------------------------------------------------------------------- #
# Política de tolerancia y sanciones (HU-41)
# --------------------------------------------------------------------------- #
@router.get(
    "/sanciones",
    response_model=ParametroSancionOut,
    summary="Consultar la política de tolerancia y sanciones",
    description=(
        "**HU-41.** Solo el ADMIN. Devuelve la tolerancia, los minutos de aviso, los minutos "
        "por strike, el máximo de strikes y la acción configurada para cada nivel."
    ),
    response_description="Política vigente",
    responses={**_401, **_403},
)
def consultar_sanciones(
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return sanciones.consultar_parametros(db)


@router.patch(
    "/sanciones",
    response_model=ParametroSancionOut,
    summary="Configurar la tolerancia y las sanciones",
    description=(
        "**HU-41.** Solo el ADMIN. Los minutos de aviso deben ser menores que la tolerancia. "
        "Los niveles de las acciones no pueden superar el máximo de strikes. Aplica a los "
        "retrasos futuros: los strikes ya registrados no cambian. Cada cambio queda en el "
        "registro de configuración con usuario, fecha y hora."
    ),
    response_description="Política actualizada",
    responses={**_401, **_403, **_422},
)
def actualizar_sanciones(
    datos: ParametroSancionActualizar,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        return sanciones.actualizar_parametros(db, admin, datos)
    except sanciones.ErrorSancion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error
