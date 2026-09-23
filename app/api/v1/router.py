from fastapi import APIRouter

from app.api.v1.endpoints import items

api_router = APIRouter()
api_router.include_router(items.router, prefix="/items", tags=["items"])
from app.api.v1.endpoints import espacios
api_router.include_router(espacios.router, prefix="/espacios", tags=["espacios"])
from app.api.v1.endpoints import auth
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
from app.api.v1.endpoints import solicitudes, disponibilidad_espacio
api_router.include_router(solicitudes.router, prefix="/solicitudes", tags=["solicitudes"])
api_router.include_router(disponibilidad_espacio.router, prefix="/espacios", tags=["espacios"])
