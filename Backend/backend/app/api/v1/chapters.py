"""
Chapter endpoints:
- GET    /documents/{id}/chapters: chapters detected in a PDF
- POST   /documents/{id}/chapters: add a chapter manually by page range
- GET    /chapters/search: hybrid chapter search (Elasticsearch BM25 + pgvector)
- GET    /chapters/{id}: chapter with its full text
- DELETE /chapters/{id}
- POST   /chapters/{id}/generate-questions: AI agent writes questions from the chapter
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from openai import APIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.models.chapter import Chapter
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.question import Question
from app.schemas.chapter import (
    ChapterCreate, ChapterDetail, ChapterOut, ChapterSearchHit, GenerateQuestionsRequest,
)
from app.services import llm_service, search_service
from app.services.document_service import chapter_embed_text
from app.services.embedding_service import generate_embedding
from app.services.pdf_parser import extract_pdf_text_by_page, text_for_pages
from app.api.v1.documents import get_document_or_404

router = APIRouter()

RRF_K = 60  # reciprocal rank fusion constant


def get_chapter_or_404(db: Session, chapter_id: int) -> Chapter:
    ch = db.get(Chapter, chapter_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ch


@router.get("/documents/{document_id}/chapters", response_model=list[ChapterOut])
def list_chapters(document_id: int, db: Session = Depends(get_db)):
    get_document_or_404(db, document_id)
    return db.scalars(
        select(Chapter).where(Chapter.document_id == document_id).order_by(Chapter.order_index)
    ).all()


@router.post("/documents/{document_id}/chapters", response_model=ChapterOut)
def create_chapter(document_id: int, body: ChapterCreate, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, document_id)
    pages = extract_pdf_text_by_page(doc.storage_path)
    if body.end_page < body.start_page or body.end_page > len(pages):
        raise HTTPException(status_code=400, detail=f"Page range must be within 1-{len(pages)}")
    content = text_for_pages(pages, body.start_page, body.end_page)
    ch = Chapter(
        document_id=doc.id,
        title=body.title.strip(),
        start_page=body.start_page,
        end_page=body.end_page,
        source="manual",
        content=content,
        embedding=generate_embedding(chapter_embed_text(body.title, content)),
    )
    db.add(ch)
    db.flush()
    chapters = db.scalars(
        select(Chapter).where(Chapter.document_id == doc.id)
        .order_by(Chapter.start_page, Chapter.title)
    ).all()
    for i, c in enumerate(chapters):
        c.order_index = i
    db.commit()
    db.refresh(ch)
    search_service.index_chapter(doc, ch)
    return ch


@router.get("/chapters/search", response_model=list[ChapterSearchHit])
def search_chapters(
    q: str = Query(..., min_length=1, description="Chapter name or topic"),
    document_id: int | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Hybrid search, fused with Reciprocal Rank Fusion:
    1. Elasticsearch BM25 on chapter title (boosted) + text  -> "keyword"
       (falls back to a Postgres ILIKE title match if ES is down)
    2. pgvector similarity to each chapter's embedding        -> "semantic"
    3. pgvector similarity of chunks, mapped to their chapter -> "content"
    """
    rankings: dict[str, list[int]] = {}

    es_hits = search_service.search_chapters(q, document_id, size=20)
    if es_hits is not None:
        rankings["keyword"] = [h["id"] for h in es_hits]
    else:
        stmt = select(Chapter.id).where(Chapter.title.ilike(f"%{q}%"))
        if document_id:
            stmt = stmt.where(Chapter.document_id == document_id)
        rankings["keyword"] = list(db.scalars(stmt.order_by(Chapter.order_index).limit(20)))

    qvec = generate_embedding(q)
    stmt = select(Chapter.id).where(Chapter.embedding.is_not(None))
    if document_id:
        stmt = stmt.where(Chapter.document_id == document_id)
    rankings["semantic"] = list(db.scalars(
        stmt.order_by(Chapter.embedding.cosine_distance(qvec)).limit(20)
    ))

    stmt = select(DocumentChunk.document_id, DocumentChunk.page_number).where(
        DocumentChunk.embedding.is_not(None)
    )
    if document_id:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    chunk_hits = db.execute(
        stmt.order_by(DocumentChunk.embedding.cosine_distance(qvec)).limit(30)
    ).all()
    if chunk_hits:
        doc_ids = {d for d, _ in chunk_hits}
        all_chapters = db.scalars(select(Chapter).where(Chapter.document_id.in_(doc_ids))).all()
        content_rank: list[int] = []
        for d, page in chunk_hits:
            for ch in all_chapters:
                if ch.document_id == d and ch.start_page <= page <= ch.end_page:
                    if ch.id not in content_rank:
                        content_rank.append(ch.id)
                    break
        rankings["content"] = content_rank

    scores: dict[int, float] = {}
    matched: dict[int, list[str]] = {}
    weights = {"keyword": 1.5, "semantic": 1.0, "content": 0.7}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids):
            scores[cid] = scores.get(cid, 0.0) + weights[name] / (RRF_K + rank + 1)
            matched.setdefault(cid, []).append(name)

    top_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
    if not top_ids:
        return []
    rows = {
        ch.id: (ch, title)
        for ch, title in db.execute(
            select(Chapter, Document.title)
            .join(Document, Document.id == Chapter.document_id)
            .where(Chapter.id.in_(top_ids))
        ).all()
    }
    results = []
    for cid in top_ids:
        if cid not in rows:
            continue
        ch, doc_title = rows[cid]
        results.append(ChapterSearchHit(
            **ChapterOut.model_validate(ch).model_dump(),
            document_title=doc_title,
            score=round(scores[cid] * 1000, 3),
            matched_by=matched[cid],
            snippet=" ".join(ch.content[:300].split()),
        ))
    return results


@router.get("/chapters/{chapter_id}", response_model=ChapterDetail)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)):
    return get_chapter_or_404(db, chapter_id)


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, db: Session = Depends(get_db)):
    ch = get_chapter_or_404(db, chapter_id)
    db.delete(ch)
    db.commit()
    search_service.delete_chapter(chapter_id)
    return {"deleted": chapter_id}


def build_context(db: Session, ch: Chapter, focus: str | None) -> str:
    """
    Pick the chapter text sent to the AI agent, within LLM_CONTEXT_CHARS.
    Short chapters go in whole. For long chapters we take the chunks most
    similar to `focus` (vector search) or, without a focus, an even spread.
    """
    budget = settings.LLM_CONTEXT_CHARS
    if len(ch.content) <= budget:
        return ch.content

    chunks = db.scalars(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == ch.document_id,
            DocumentChunk.page_number.between(ch.start_page, ch.end_page),
        )
        .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
    ).all()
    if not chunks:
        return ch.content[:budget]

    per_chunk = max(len(c.content) for c in chunks)
    n = max(1, budget // per_chunk)
    if focus:
        qvec = generate_embedding(focus)
        ranked = db.scalars(
            select(DocumentChunk.id)
            .where(DocumentChunk.id.in_([c.id for c in chunks]), DocumentChunk.embedding.is_not(None))
            .order_by(DocumentChunk.embedding.cosine_distance(qvec))
            .limit(n)
        ).all()
        chosen = set(ranked)
        picked = [c for c in chunks if c.id in chosen]
    else:
        step = len(chunks) / n
        picked = [chunks[int(i * step)] for i in range(min(n, len(chunks)))]
    return "\n...\n".join(c.content for c in picked)[:budget]


@router.post("/chapters/{chapter_id}/generate-questions")
def generate_questions(
    chapter_id: int, body: GenerateQuestionsRequest, db: Session = Depends(get_db)
):
    ch = get_chapter_or_404(db, chapter_id)
    if not ch.content.strip():
        raise HTTPException(status_code=400, detail="This chapter has no extractable text (scanned PDF?)")

    counts = {
        "mcq": body.num_mcq,
        "true_false": body.num_true_false,
        "short": body.num_short,
        "broad": body.num_broad,
    }
    if sum(counts.values()) == 0:
        raise HTTPException(status_code=400, detail="Ask for at least one question")

    context = build_context(db, ch, body.focus)
    instructions = body.instructions
    if body.focus:
        instructions = f"Focus on: {body.focus}. {instructions or ''}".strip()
    try:
        questions = llm_service.generate_questions(
            ch.title, context, counts, body.difficulty, instructions
        )
    except llm_service.LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"AI agent error: {e.message}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    for q in questions:
        q.update(topic=ch.title, document_id=ch.document_id, chapter_id=ch.id, source="ai")

    saved_ids: list[int] = []
    if body.save_to_bank and questions:
        rows = [Question(**q) for q in questions]
        db.add_all(rows)
        db.commit()
        search_service.index_questions(rows)
        saved_ids = [r.id for r in rows]

    return {
        "chapter_id": ch.id,
        "chapter_title": ch.title,
        "model": settings.LLM_MODEL,
        "context_chars": len(context),
        "questions": questions,
        "saved_ids": saved_ids,
    }
