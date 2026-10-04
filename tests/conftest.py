"""Configuración de pytest.

Las pruebas usan una base de datos aparte, reservas_test, en el mismo Postgres
del compose. Se crea sola si no existe. Cada prueba empieza con las tablas vacías.

Uso: docker compose exec api python -m pytest
"""
import os

import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://reservas:reservas_dev@db:5432/reservas_test"
)

# Protección: las pruebas vacían tablas. Si la URL no es la de pruebas, no se corre nada.
if not TEST_DATABASE_URL.endswith("reservas_test"):
    pytest.exit(f"TEST_DATABASE_URL debe terminar en 'reservas_test'. Se recibió: {TEST_DATABASE_URL}", returncode=1)

# database.py crea el engine al importarse: la variable se fija antes de importar la app
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402

# Segunda comprobación, por si algo importó database.py antes que este archivo
if engine.url.database != "reservas_test":
    pytest.exit(f"El engine apunta a '{engine.url.database}', no a 'reservas_test'. Abortado.", returncode=1)

from app.api.v1.endpoints import registro as registro_endpoints  # noqa: E402
from app.api.v1.endpoints import usuarios as usuarios_endpoints  # noqa: E402
from app.core.security import crear_token, hash_clave  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import Cargo, Rol  # noqa: E402
from app.models.modelos import Usuario  # noqa: E402
from app.utils.crear_tablas import crear_tablas  # noqa: E402

CLAVE = "ClavePrueba2026*"

# Mientras los routers no estén registrados en app/api/v1/router.py, se registran
# aquí para poder probarlos. Cuando ya lo estén, esto no hace nada.
# Se usa el esquema OpenAPI porque app.routes agrupa los routers incluidos y no
# muestra sus rutas.
_RUTAS = set(app.openapi()["paths"])
if not any(p.startswith(f"{settings.API_V1_STR}/usuarios") for p in _RUTAS):
    app.include_router(usuarios_endpoints.router, prefix=f"{settings.API_V1_STR}/usuarios", tags=["Usuarios"])
if f"{settings.API_V1_STR}/auth/registro" not in _RUTAS:
    app.include_router(registro_endpoints.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.openapi_schema = None  # que el esquema se vuelva a generar con los routers agregados


def _crear_bd_de_pruebas() -> None:
    servidor = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with servidor.connect() as conn:
        existe = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'reservas_test'"))
        if not existe:
            conn.execute(text("CREATE DATABASE reservas_test"))
    servidor.dispose()


@pytest.fixture(scope="session", autouse=True)
def bd_de_pruebas():
    _crear_bd_de_pruebas()
    crear_tablas()
    yield


@pytest.fixture(autouse=True)
def tablas_vacias(bd_de_pruebas):
    # TRUNCATE no dispara el trigger que protege la trazabilidad (es por fila)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def crear_usuario():
    """Inserta un usuario directo en la BD (sin pasar por la API)."""

    def _crear(email: str, rol: Rol = Rol.SOLICITANTE, cargo: Cargo | None = None, activo: bool = True) -> Usuario:
        with SessionLocal() as db:
            usuario = Usuario(
                nombre=f"Usuario {email}", email=email, clave_hash=hash_clave(CLAVE),
                rol=rol, cargo=cargo, activo=activo,
            )
            db.add(usuario)
            db.commit()
            db.refresh(usuario)
            return usuario

    return _crear


def cabecera(usuario: Usuario) -> dict:
    token, _ = crear_token(usuario.id, usuario.rol.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(crear_usuario) -> Usuario:
    return crear_usuario("admin@reservas.test", Rol.ADMIN, Cargo.ADMINISTRADOR_SISTEMA)


@pytest.fixture
def solicitante(crear_usuario) -> Usuario:
    return crear_usuario("estudiante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
