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
from app.api.v1.endpoints import revision
api_router.include_router(revision.router, prefix="/solicitudes", tags=["solicitudes"])
from app.api.v1.endpoints import decision
api_router.include_router(decision.router, prefix="/solicitudes", tags=["solicitudes"])
from app.api.v1.endpoints import reservas
api_router.include_router(reservas.router, prefix="/reservas", tags=["reservas"])
from app.api.v1.endpoints import historial
api_router.include_router(historial.router, tags=["historial"])
