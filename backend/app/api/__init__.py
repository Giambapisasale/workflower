from fastapi import APIRouter

from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(ask_router)
