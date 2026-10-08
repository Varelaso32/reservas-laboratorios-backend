from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "Reservas Laboratorios API"
    PROJECT_DESCRIPTION: str = "API backend para la gestión de reservas de laboratorios"
    PROJECT_VERSION: str = "0.1.0"

    API_V1_STR: str = "/api/v1"

    # Conexión a PostgreSQL. La clave NO va en el código: se define en el .env local
    # (ver .env.example) o como variable de entorno del servidor.
    # DATABASE_URL, si se define, reemplaza a las POSTGRES_* (la usan las pruebas).
    POSTGRES_USER: str = "reservas"
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_DB: str = "reservas"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if not self.POSTGRES_PASSWORD:
            raise RuntimeError(
                "Falta POSTGRES_PASSWORD. Crea el archivo .env a partir de .env.example "
                "o define la variable de entorno."
            )
        # URL.create escapa caracteres especiales de la clave (@, :, /)
        return URL.create(
            "postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    # Orígenes del front que pueden llamar a la API, separados por coma.
    # En producción se agrega el dominio de Vercel con la variable CORS_ORIGINS.
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:4200,http://127.0.0.1:4200"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
