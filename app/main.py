import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.utils.esquema import verificar

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Permite que el front (otro origen) consuma la API desde el navegador.
# El token viaja en la cabecera Authorization, no en cookies, por eso no hace falta allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root() -> dict:
    return {"message": f"Bienvenido a la API de {settings.PROJECT_NAME}"}


# El esquema no cambia mientras el proceso está vivo: se recuerda el resultado
# bueno unos segundos para que el health check de Render no consulte el catálogo
# en cada ping, pero sin ocultar una caída de la base.
_CACHE_SALUD = {"ok": False, "comprobado_en": 0.0}
VIDA_CACHE_SALUD = 60


@app.get("/salud", summary="Estado del servicio y del esquema de la base")
def salud() -> JSONResponse:
    """200 solo si la base responde y el esquema está al día; 503 si no."""
    if _CACHE_SALUD["ok"] and time.monotonic() - _CACHE_SALUD["comprobado_en"] < VIDA_CACHE_SALUD:
        return JSONResponse(status_code=200, content={"estado": "ok"})
    try:
        problemas = verificar()
    except Exception as error:  # noqa: BLE001  (cualquier fallo de conexión es 503)
        _CACHE_SALUD["ok"] = False
        return JSONResponse(
            status_code=503,
            content={
                "estado": "error",
                "detalle": f"No se pudo consultar la base ({type(error).__name__})",
            },
        )
    if problemas:
        _CACHE_SALUD["ok"] = False
        return JSONResponse(
            status_code=503, content={"estado": "error", "problemas": problemas}
        )
    _CACHE_SALUD["ok"] = True
    _CACHE_SALUD["comprobado_en"] = time.monotonic()
    return JSONResponse(status_code=200, content={"estado": "ok"})
