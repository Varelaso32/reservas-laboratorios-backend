from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Cargo, Rol


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador del usuario", examples=[4])
    nombre: str = Field(description="Nombre completo", examples=["Estudiante de Prueba"])
    email: str = Field(description="Correo", examples=["estudiante@reservas.test"])
    rol: Rol = Field(description="SOLICITANTE, APROBADOR o ADMIN")
    cargo: Cargo | None = Field(description="Cargo dentro de la institución")
    puede_autorizar_especial: bool = Field(
        default=False,
        description="Permiso para decidir solicitudes fuera de la franja de operación (HU-35)",
    )


class TokenOut(BaseModel):
    access_token: str = Field(description="Token JWT. Se envía en la cabecera Authorization: Bearer <token>")
    token_type: str = Field(description="Siempre 'bearer'", examples=["bearer"])
    expira_en: int = Field(description="Segundos de vigencia del token", examples=[3600])
    usuario: UsuarioOut = Field(description="Datos del usuario que inició sesión")
