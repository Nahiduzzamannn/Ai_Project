from fastapi import APIRouter
from .health import router as health_router
from .documents import router as documents_router
from .chapters import router as chapters_router
from .questions import router as questions_router
from .chat import router as chat_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(chapters_router, tags=["chapters"])
api_router.include_router(questions_router, tags=["questions"])
api_router.include_router(chat_router, tags=["chat"])
