from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    decision,
    disponibilidad_espacio,
    espacios,
    historial,
    items,
    registro,
    reservas,
    revision,
    solicitudes,
    usuarios,
)

api_router = APIRouter()

api_router.include_router(items.router, prefix="/items", tags=["items"])
api_router.include_router(espacios.router, prefix="/espacios", tags=["espacios"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(solicitudes.router, prefix="/solicitudes", tags=["solicitudes"])
api_router.include_router(disponibilidad_espacio.router, prefix="/espacios", tags=["espacios"])
api_router.include_router(revision.router, prefix="/solicitudes", tags=["solicitudes"])
api_router.include_router(decision.router, prefix="/solicitudes", tags=["solicitudes"])
api_router.include_router(reservas.router, prefix="/reservas", tags=["reservas"])
api_router.include_router(historial.router, tags=["historial"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"])
api_router.include_router(registro.router, prefix="/auth", tags=["auth"])
