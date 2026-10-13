from fastapi import APIRouter
from .health import router as health_router
from .documents import router as documents_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(documents_router, tags=["documents"])
