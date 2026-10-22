"""
RAG chat endpoint:
- POST /chat: chat with the AI agent about a chapter, a document or all documents.
  Each message retrieves relevant chunks (pgvector + Elasticsearch) and the AI
  answers and/or writes exam questions grounded in them.

The chat is stateless: the client sends the whole conversation each time.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from openai import APIError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.models.chapter import Chapter
from app.models.document import Document
from app.services import llm_service, rag_service

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    # Questions the assistant produced in that turn (sent back for follow-ups)
    questions: Optional[list[dict]] = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    chapter_id: Optional[int] = None
    document_id: Optional[int] = None


@router.post("/chat")
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    if body.messages[-1].role != "user" or not body.messages[-1].content.strip():
        raise HTTPException(status_code=400, detail="The last message must be a non-empty user message")

    chapter = None
    if body.chapter_id:
        chapter = db.get(Chapter, body.chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
    elif body.document_id and not db.get(Document, body.document_id):
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        result = rag_service.chat(
            db,
            [m.model_dump() for m in body.messages],
            document_id=body.document_id,
            chapter=chapter,
        )
    except llm_service.LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"AI agent error: {e.message}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {**result, "model": settings.LLM_MODEL}
