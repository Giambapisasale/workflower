from fastapi import APIRouter

from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.azienda import router as azienda_router
from app.api.cantieri import router as cantieri_router
from app.api.consuntivo import router as consuntivo_router
from app.api.dashboard import router as dashboard_router
from app.api.dataset import router as dataset_router
from app.api.diagnoses import router as diagnoses_router
from app.api.documents import router as documents_router
from app.api.entities import router as entities_router
from app.api.erp import router as erp_router
from app.api.golden import router as golden_router
from app.api.health import router as health_router
from app.api.issues import router as issues_router
from app.api.logs import router as logs_router
from app.api.reports import router as reports_router
from app.api.review import router as review_router
from app.api.samples import router as samples_router
from app.api.scarti import router as scarti_router
from app.api.toolsmith import router as toolsmith_router
from app.api.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(ask_router)
api_router.include_router(dashboard_router)
api_router.include_router(cantieri_router)
api_router.include_router(consuntivo_router)
api_router.include_router(reports_router)
api_router.include_router(review_router)
# Prima di entities_router: /scartati/{id}/ripristina non deve finire nella
# rotta generica /entities/{tipo}/{id}. (Sono prefissi diversi, ma l'ordine
# rende l'intenzione esplicita.)
api_router.include_router(scarti_router)
api_router.include_router(entities_router)
api_router.include_router(issues_router)
api_router.include_router(workflows_router)
api_router.include_router(golden_router)
api_router.include_router(dataset_router)
api_router.include_router(toolsmith_router)
api_router.include_router(logs_router)
api_router.include_router(diagnoses_router)
api_router.include_router(samples_router)
api_router.include_router(erp_router)
api_router.include_router(azienda_router)
