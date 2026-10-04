"""Gestión de usuarios: crear, listar, consultar, actualizar y activar/desactivar."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.usuario import (
    UsuarioActualizar, UsuarioCrear, UsuarioDetalleOut, UsuarioEstadoActualizar, UsuarioListaOut,
)
from app.services import usuarios

router = APIRouter()

_401 = {401: {"description": "No autenticado: el token falta, no es válido o expiró"}}
_403 = {403: {"description": "Solo los usuarios ADMIN pueden hacer esta acción"}}
_404 = {404: {"description": "El usuario no existe"}}
_409 = {409: {"description": "Ya existe un usuario con ese correo (sin importar mayúsculas ni espacios)"}}
_422 = {422: {"description": "Datos inválidos: campo faltante, correo mal formado, clave corta o larga, rol inexistente o campo no permitido"}}
_400_CARGO = "El cargo no corresponde al rol"
_400_ADMIN = "Se intentó desactivar o quitar el rol al único ADMIN activo"


def _ejecutar(db: Session, accion, *args):
    try:
        return accion(db, *args)
    except usuarios.ErrorUsuario as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje)


@router.post(
    "/",
    response_model=UsuarioDetalleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
    description=(
        "Registra un usuario nuevo. Solo para ADMIN.\n\n"
        "- El correo se guarda en minúsculas y sin espacios. No puede repetirse.\n"
        "- La clave debe tener de 8 a 128 caracteres y se guarda solo su hash (Argon2). "
        "Nunca aparece en ninguna respuesta.\n"
        "- El cargo es opcional, pero si se envía debe corresponder al rol: SOLICITANTE → "
        "ESTUDIANTE, DOCENTE o ADMINISTRATIVO; APROBADOR → COORDINADOR_LABORATORIOS o "
        "ADMINISTRADOR_SALA; ADMIN → ADMINISTRADOR_SISTEMA.\n"
        "- El usuario nace activo."
    ),
    response_description="Usuario creado",
    responses={400: {"description": _400_CARGO}, **_401, **_403, **_409, **_422},
)
def crear_usuario(
    datos: UsuarioCrear,
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, usuarios.crear, datos)


@router.get(
    "/",
    response_model=UsuarioListaOut,
    summary="Listar usuarios",
    description=(
        "Devuelve los usuarios ordenados por id, con paginación. Solo para ADMIN. "
        "Se puede filtrar por rol y por estado (activo). `total` cuenta todos los que cumplen "
        "el filtro, no solo los de la página."
    ),
    response_description="Página de usuarios",
    responses={**_401, **_403, 422: {"description": "skip negativo o limit fuera de 1 a 100"}},
)
def listar_usuarios(
    skip: int = Query(0, ge=0, description="Cuántos registros saltar"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de registros a devolver (1 a 100)"),
    rol: Rol | None = Query(None, description="Filtrar por rol"),
    activo: bool | None = Query(None, description="true solo activos, false solo inactivos. Sin enviar: todos"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return usuarios.listar(db, skip, limit, rol, activo)


@router.get(
    "/{usuario_id}",
    response_model=UsuarioDetalleOut,
    summary="Consultar un usuario",
    description=(
        "Devuelve los datos de un usuario. ADMIN puede consultar cualquiera; los demás roles "
        "solo a sí mismos. Si un usuario que no es ADMIN pide otro id, la respuesta es 404, "
        "igual que si no existiera, para no revelar qué ids están registrados.\n\n"
        "Para los datos del usuario con sesión también existe GET /api/v1/auth/me."
    ),
    response_description="Datos del usuario",
    responses={**_401, 404: {"description": "El usuario no existe o no tienes acceso a él"}},
)
def consultar_usuario(
    usuario_id: int,
    actual: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, usuarios.obtener, usuario_id, actual)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioDetalleOut,
    summary="Actualizar usuario",
    description=(
        "Cambia nombre, correo, rol o cargo. Solo para ADMIN. Solo se modifican los campos "
        "enviados; los campos nombre, email y rol no aceptan null.\n\n"
        "- Se valida que el cargo final corresponda al rol final (si solo cambias el rol, el "
        "cargo actual también debe encajar; envía `cargo` nuevo o `null`).\n"
        "- No se puede quitar el rol ADMIN al único ADMIN activo.\n"
        "- La clave y el estado no se cambian aquí."
    ),
    response_description="Usuario actualizado",
    responses={
        400: {"description": f"{_400_CARGO}, o {_400_ADMIN.lower()}"},
        **_401, **_403, **_404, **_409, **_422,
    },
)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizar,
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, usuarios.actualizar, usuario_id, datos)


@router.patch(
    "/{usuario_id}/estado",
    response_model=UsuarioDetalleOut,
    summary="Activar o desactivar usuario",
    description=(
        "Borrado lógico. Solo para ADMIN. Con `activo: false` el usuario no puede iniciar "
        "sesión y sus tokens dejan de servir de inmediato, pero la fila se conserva porque "
        "sus solicitudes, reservas e historial la referencian. Con `activo: true` se reactiva.\n\n"
        "No se puede desactivar al único ADMIN activo."
    ),
    response_description="Usuario con su nuevo estado",
    responses={400: {"description": _400_ADMIN}, **_401, **_403, **_404, **_422},
)
def cambiar_estado_usuario(
    usuario_id: int,
    datos: UsuarioEstadoActualizar,
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, usuarios.cambiar_estado, usuario_id, datos.activo)
