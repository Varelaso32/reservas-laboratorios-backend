"""Dependencias de autenticación y autorización (fase 2).

Uso en un endpoint:
    usuario: Usuario = Depends(get_usuario_actual)             # cualquier usuario con sesión
    usuario: Usuario = Depends(requiere_rol(Rol.APROBADOR))    # solo ese rol
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import leer_token
from app.models.enums import Rol
from app.models.modelos import Usuario

# tokenUrl habilita el botón "Authorize" de Swagger
# auto_error=False: sin token FastAPI respondería "Not authenticated" en inglés;
# así el mensaje es siempre el nuestro, en español.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

_NO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No autenticado: el token falta, no es válido o expiró",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_usuario_actual(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Usuario:
    if not token:
        raise _NO_AUTENTICADO
    try:
        datos = leer_token(token)
        usuario_id = int(datos["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _NO_AUTENTICADO
    usuario = db.get(Usuario, usuario_id)
    # Se consulta la BD en cada petición: un usuario desactivado pierde el acceso
    # de inmediato, aunque su token todavía no haya expirado.
    if usuario is None or not usuario.activo:
        raise _NO_AUTENTICADO
    return usuario


def requiere_rol(*roles: Rol):
    def verificar(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para esta acción",
            )
        return usuario

    return verificar
