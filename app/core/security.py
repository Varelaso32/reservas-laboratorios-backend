"""Claves y tokens JWT (fase 2)."""
import os
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

# Se leen de variables de entorno del sistema, NO del .env (config.py rechaza
# variables que no conoce). En producción JWT_SECRET debe definirse sí o sí.
JWT_SECRET = os.getenv("JWT_SECRET", "solo-desarrollo-cambiar-en-produccion-7f3a9c2e")
JWT_ALGORITMO = "HS256"
JWT_EXPIRA_MINUTOS = int(os.getenv("JWT_EXPIRA_MINUTOS", "60"))

# Argon2 en lugar de bcrypt: bcrypt 5.x falla con claves de más de 72 bytes
_hasher = PasswordHash((Argon2Hasher(),))

# Se usa cuando el correo no existe, para que la respuesta tarde lo mismo
# y no se pueda adivinar qué correos están registrados.
_HASH_FALSO = _hasher.hash("clave-que-nadie-usa")


def hash_clave(clave: str) -> str:
    return _hasher.hash(clave)


def verificar_clave(clave: str, clave_hash: str | None) -> bool:
    try:
        return _hasher.verify(clave, clave_hash or _HASH_FALSO)
    except UnknownHashError:
        # Usuarios sin clave definida todavía (por ejemplo "PENDIENTE_LOGIN")
        return False


def crear_token(usuario_id: int, rol: str) -> tuple[str, int]:
    expira = datetime.now(UTC) + timedelta(minutes=JWT_EXPIRA_MINUTOS)
    # "sub" debe ser texto: PyJWT 2.10+ rechaza tokens con sub numérico
    datos = {"sub": str(usuario_id), "rol": rol, "exp": expira}
    return jwt.encode(datos, JWT_SECRET, algorithm=JWT_ALGORITMO), JWT_EXPIRA_MINUTOS * 60


def leer_token(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token es inválido o expiró."""
    return jwt.decode(
        token, JWT_SECRET, algorithms=[JWT_ALGORITMO], options={"require": ["exp", "sub"]}
    )
