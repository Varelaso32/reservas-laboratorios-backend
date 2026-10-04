"""Esquemas de gestión de usuarios. Ninguno de salida incluye la clave."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Cargo, Rol
from app.utils.fechas import ZONA_COLOMBIA

# Coinciden con las columnas de la tabla usuario: si se pasan, la BD daría error 500
NOMBRE_MAX = 120
EMAIL_MAX = 254
# Argon2 no tiene el límite de 72 bytes de bcrypt; el tope evita claves gigantes
# que cuestan CPU al hashear.
CLAVE_MIN = 8
CLAVE_MAX = 128


def normalizar_email(valor: str) -> str:
    """strip() + lower() y reglas mínimas de formato. Lanza ValueError si no cumple."""
    email = valor.strip().lower()
    if len(email) > EMAIL_MAX:
        raise ValueError(f"El correo no puede tener más de {EMAIL_MAX} caracteres")
    if any(c.isspace() for c in email):
        raise ValueError("El correo no puede tener espacios")
    if email.count("@") != 1:
        raise ValueError("El correo debe tener un solo '@'")
    local, dominio = email.split("@")
    if not local or not dominio:
        raise ValueError("El correo debe tener texto antes y después del '@'")
    if "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        raise ValueError("El dominio del correo debe tener al menos un punto, por ejemplo ecci.edu.co")
    return email


def _normalizar_nombre(valor: str) -> str:
    nombre = valor.strip()
    if not nombre:
        raise ValueError("El nombre no puede estar vacío")
    return nombre


class UsuarioCrear(BaseModel):
    # forbid: nadie puede mandar id, clave_hash, activo o creado_en
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "Laura Gómez",
                "email": "laura.gomez@ecci.edu.co",
                "clave": "Laboratorio2026*",
                "rol": "SOLICITANTE",
                "cargo": "ESTUDIANTE",
            }
        },
    )

    nombre: str = Field(max_length=NOMBRE_MAX, description="Nombre completo")
    email: str = Field(max_length=EMAIL_MAX + 50, description="Correo. Se guarda en minúsculas y sin espacios")
    clave: str = Field(
        min_length=CLAVE_MIN, max_length=CLAVE_MAX,
        description=f"Contraseña de {CLAVE_MIN} a {CLAVE_MAX} caracteres. Se guarda solo el hash",
    )
    rol: Rol = Field(description="SOLICITANTE, APROBADOR o ADMIN")
    cargo: Cargo | None = Field(None, description="Debe corresponder al rol. Opcional")

    _nombre = field_validator("nombre")(_normalizar_nombre)
    _email = field_validator("email")(normalizar_email)


class RegistroCrear(BaseModel):
    """Auto-registro desde el login. No lleva rol ni cargo: el backend los fija."""

    # forbid: si el front manda "rol" (por ejemplo para intentar ser ADMIN), responde 422
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "Laura Gómez",
                "email": "laura.gomez@ecci.edu.co",
                "clave": "Laboratorio2026*",
            }
        },
    )

    nombre: str = Field(max_length=NOMBRE_MAX, description="Nombre completo")
    email: str = Field(max_length=EMAIL_MAX + 50, description="Correo institucional. Se guarda en minúsculas y sin espacios")
    clave: str = Field(
        min_length=CLAVE_MIN, max_length=CLAVE_MAX,
        description=f"Contraseña de {CLAVE_MIN} a {CLAVE_MAX} caracteres. Se guarda solo el hash",
    )

    _nombre = field_validator("nombre")(_normalizar_nombre)
    _email = field_validator("email")(normalizar_email)


class UsuarioActualizar(BaseModel):
    """Solo se cambian los campos enviados. La clave y el estado tienen su propio flujo."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"rol": "APROBADOR", "cargo": "COORDINADOR_LABORATORIOS"}},
    )

    nombre: str | None = Field(None, max_length=NOMBRE_MAX, description="Nombre completo")
    email: str | None = Field(None, max_length=EMAIL_MAX + 50, description="Correo nuevo")
    rol: Rol | None = Field(None, description="SOLICITANTE, APROBADOR o ADMIN")
    cargo: Cargo | None = Field(None, description="Cargo. Se puede enviar null para quitarlo")

    @field_validator("nombre", "email", "rol", mode="before")
    @classmethod
    def _sin_null(cls, valor):
        # Son columnas NOT NULL: un null explícito se rechaza con 422 en lugar de un 500
        if valor is None:
            raise ValueError("Este campo no puede ser null; si no quieres cambiarlo, no lo envíes")
        return valor

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, valor: str) -> str:
        return _normalizar_nombre(valor)

    @field_validator("email")
    @classmethod
    def _email(cls, valor: str) -> str:
        return normalizar_email(valor)


class UsuarioEstadoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"activo": False}})

    activo: bool = Field(description="false desactiva al usuario (borrado lógico); true lo reactiva")


class UsuarioDetalleOut(BaseModel):
    """Se llama así y no UsuarioOut porque ese nombre ya lo usa app/schemas/auth.py
    y Swagger mostraría dos esquemas con nombres largos."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 7,
                "nombre": "Laura Gómez",
                "email": "laura.gomez@ecci.edu.co",
                "rol": "SOLICITANTE",
                "cargo": "ESTUDIANTE",
                "activo": True,
                "creado_en": "2026-10-02T09:15:00-05:00",
            }
        },
    )

    id: int = Field(description="Identificador del usuario")
    nombre: str = Field(description="Nombre completo")
    email: str = Field(description="Correo en minúsculas")
    rol: Rol = Field(description="SOLICITANTE, APROBADOR o ADMIN")
    cargo: Cargo | None = Field(description="Cargo dentro de la institución")
    activo: bool = Field(description="false si fue desactivado")
    creado_en: datetime = Field(description="Fecha de creación, en hora de Colombia")

    @field_validator("creado_en")
    @classmethod
    def _hora_colombia(cls, valor: datetime) -> datetime:
        return valor.astimezone(ZONA_COLOMBIA) if valor.tzinfo else valor


class UsuarioListaOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 1,
                "skip": 0,
                "limit": 20,
                "items": [UsuarioDetalleOut.model_config["json_schema_extra"]["example"]],
            }
        }
    )

    total: int = Field(description="Usuarios que cumplen el filtro, sin contar la paginación")
    skip: int = Field(description="Registros saltados")
    limit: int = Field(description="Máximo de registros devueltos")
    items: list[UsuarioDetalleOut] = Field(description="Usuarios de esta página, ordenados por id")
