from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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