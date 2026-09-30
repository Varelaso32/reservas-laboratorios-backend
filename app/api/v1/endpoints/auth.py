"""Fase 2: login y usuario actual (JWT y roles)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.database import get_db
from app.core.security import crear_token, verificar_clave
from app.models.modelos import Usuario
from app.schemas.auth import TokenOut, UsuarioOut

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Iniciar sesión",
    description=(
        "Recibe el correo en `username` y la clave en `password`, como formulario "
        "(application/x-www-form-urlencoded). Devuelve un token JWT que se envía en la "
        "cabecera `Authorization: Bearer <token>`.\n\n"
        "El correo no distingue mayúsculas. Si el correo no existe o la clave es incorrecta, "
        "la respuesta es la misma (401), para no revelar qué correos están registrados."
    ),
    response_description="Sesión iniciada",
    responses={
        401: {"description": "Correo o contraseña incorrectos"},
        403: {"description": "El usuario está inactivo"},
        422: {"description": "Falta el correo o la clave"},
    },
)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    usuario = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    clave_ok = verificar_clave(form.password, usuario.clave_hash if usuario else None)
    if usuario is None or not clave_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El usuario está inactivo")
    token, segundos = crear_token(usuario.id, usuario.rol.value)
    return TokenOut(access_token=token, token_type="bearer", expira_en=segundos, usuario=usuario)


@router.get(
    "/me",
    response_model=UsuarioOut,
    summary="Usuario actual",
    description="Devuelve los datos del usuario dueño del token. Requiere sesión iniciada.",
    response_description="Datos del usuario",
    responses={401: {"description": "No autenticado: el token falta, no es válido o expiró"}},
)
def usuario_actual(usuario: Usuario = Depends(get_usuario_actual)):
    return usuario
