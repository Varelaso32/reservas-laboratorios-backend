from fastapi import APIRouter

from app.api.v1.endpoints import items

api_router = APIRouter()
api_router.include_router(items.router, prefix="/items", tags=["items"])
from app.api.v1.endpoints import espacios
api_router.include_router(espacios.router, prefix="/espacios", tags=["espacios"])
from app.api.v1.endpoints import auth
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
