"""Auto-registro de estudiantes desde la pantalla de inicio de sesión."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.usuario import RegistroCrear, UsuarioDetalleOut
from app.services import usuarios

router = APIRouter()


@router.post(
    "/registro",
    response_model=UsuarioDetalleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrarse",
    description=(
        "Crea una cuenta sin necesidad de sesión. Pensado para el formulario de registro del "
        "login.\n\n"
        "- Solo recibe nombre, email y clave. La cuenta queda siempre con rol **SOLICITANTE** y "
        "cargo **ESTUDIANTE**; si se envía `rol`, `cargo` u otro campo, responde 422.\n"
        "- Solo acepta correos institucionales: `@ecci.edu.co` (y `@reservas.test` en desarrollo).\n"
        "- No inicia sesión: después del registro el front debe llamar a POST /api/v1/auth/login.\n"
        "- Si la persona es docente o administrativo, un ADMIN le cambia el cargo con "
        "PATCH /api/v1/usuarios/{usuario_id}."
    ),
    response_description="Cuenta creada",
    responses={
        400: {"description": "El correo no es de un dominio institucional permitido"},
        409: {"description": "Ya existe un usuario con ese correo"},
        422: {"description": "Campo faltante, correo mal formado, clave fuera de 8 a 128 caracteres, o campo no permitido (rol, cargo...)"},
    },
)
def registrarse(datos: RegistroCrear, db: Session = Depends(get_db)):
    try:
        return usuarios.registrar(db, datos)
    except usuarios.ErrorUsuario as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error
