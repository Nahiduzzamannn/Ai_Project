from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import APIError, AuthenticationError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.models.document import Document
from app.models.question import Question
from app.services import llm_service, search_service

router = APIRouter()

@router.get("/health")
def health():
    llm_service._refresh_settings_from_env()
    return {
        "status": "ok",
        "elasticsearch": search_service.is_available(),
        "ai_agent": {
            "configured": bool(settings.LLM_API_KEY),
            "model": settings.LLM_MODEL,
            "base_url": settings.LLM_BASE_URL,
        },
        "embedding_model": settings.EMBEDDING_MODEL,
    }


@router.post("/search/sync")
def sync_elasticsearch(db: Session = Depends(get_db)):
    """Copy all chapters, chunks and questions from Postgres into Elasticsearch
    (e.g. after starting Elasticsearch for the first time)."""
    if not search_service.is_available():
        raise HTTPException(status_code=503, detail=f"Elasticsearch is not reachable at {settings.ELASTICSEARCH_URL}")
    docs = db.scalars(select(Document)).all()
    for doc in docs:
        search_service.index_document(doc, doc.chapters, doc.chunks)
    questions = db.scalars(select(Question)).all()
    search_service.index_questions(questions)
    return {"documents": len(docs), "questions": len(questions)}


class LLMKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=10)
    provider: Literal["groq", "gemini"] = "groq"


@router.post("/settings/llm")
def set_llm_key(body: LLMKeyRequest, request: Request):
    """Test an AI API key and save it to .env. Only allowed from this computer."""
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="The AI key can only be set from this computer")
    key = body.api_key.strip()
    try:
        llm_service.check_key(key, llm_service.PROVIDERS[body.provider]["base_url"])
    except AuthenticationError:
        raise HTTPException(status_code=400, detail=f"{body.provider.title()} rejected this key. Copy it again and paste the whole key.")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Could not check the key: {e.message}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach {body.provider.title()}: {e}")
    return {"saved": True, **llm_service.save_llm_settings(key, body.provider)}
