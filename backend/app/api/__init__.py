from fastapi import APIRouter

from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.cantieri import router as cantieri_router
from app.api.dashboard import router as dashboard_router
from app.api.dataset import router as dataset_router
from app.api.documents import router as documents_router
from app.api.entities import router as entities_router
from app.api.health import router as health_router
from app.api.issues import router as issues_router
from app.api.reports import router as reports_router
from app.api.review import router as review_router
from app.api.toolsmith import router as toolsmith_router
from app.api.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(ask_router)
api_router.include_router(dashboard_router)
api_router.include_router(cantieri_router)
api_router.include_router(reports_router)
api_router.include_router(review_router)
api_router.include_router(entities_router)
api_router.include_router(issues_router)
api_router.include_router(workflows_router)
api_router.include_router(dataset_router)
api_router.include_router(toolsmith_router)
