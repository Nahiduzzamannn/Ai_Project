"""
Document API endpoints for PDF upload and search.

This module provides:
- POST   /documents/upload: Upload a PDF, detect chapters, embed chunks, index in Elasticsearch
- GET    /documents: List uploaded documents
- DELETE /documents/{id}: Delete a document with its chunks and chapters
- POST   /documents/{id}/reindex: Rebuild embeddings, chapters and search indexes
- GET    /documents/search: Semantic search across document chunks using pgvector
"""

import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.deps import get_db
from app.models.chapter import Chapter
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentOut, DocumentSummary
from app.services import search_service
from app.services.document_service import process_document
from app.services.embedding_service import generate_embedding

router = APIRouter()

UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_document_or_404(db: Session, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF file, extract text, chunk it, detect chapters, generate local
    embeddings, store in Postgres/pgvector and index in Elasticsearch.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    unique_name = f"{uuid.uuid4().hex}.pdf"
    save_path = os.path.join(UPLOAD_DIR, unique_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # Create document record with UPLOADED status
    doc = Document(
        title=file.filename,
        storage_path=save_path,
        doc_type="content_pdf",
        status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        return process_document(db, doc)
    except Exception as e:
        db.rollback()
        doc.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {e}")


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)):
    chapter_counts = (
        select(Chapter.document_id, func.count(Chapter.id).label("n"))
        .group_by(Chapter.document_id).subquery()
    )
    rows = db.execute(
        select(Document, func.coalesce(chapter_counts.c.n, 0))
        .outerjoin(chapter_counts, chapter_counts.c.document_id == Document.id)
        .order_by(Document.created_at.desc())
    ).all()
    return [
        DocumentSummary.model_validate(doc).model_copy(update={"chapter_count": n})
        for doc, n in rows
    ]


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, document_id)
    path = doc.storage_path
    db.delete(doc)
    db.commit()
    search_service.delete_document(document_id)
    if path and os.path.exists(path):
        os.remove(path)
    return {"deleted": document_id}


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(document_id: int, db: Session = Depends(get_db)):
    """Re-embed chunks, re-detect chapters and re-index in Elasticsearch."""
    doc = get_document_or_404(db, document_id)
    if not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="PDF file is missing on disk")
    return process_document(db, doc)


@router.get("/documents/search")
def search_documents(
    q: str = Query(..., min_length=2, description="Search query text"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results to return"),
    db: Session = Depends(get_db),
):
    """
    Semantic search across document chunks using pgvector cosine similarity.

    The cosine_distance operator returns values where:
    - 0 = identical vectors (most similar)
    - 2 = opposite vectors (least similar)
    We convert to similarity score: 1.0 - distance
    """
    query_vec = generate_embedding(q)

    stmt = (
        select(
            DocumentChunk,
            DocumentChunk.embedding.cosine_distance(query_vec).label("distance")
        )
        .where(DocumentChunk.embedding.is_not(None))  # Only chunks with embeddings
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))  # Nearest first
        .limit(top_k)
    )

    rows = db.execute(stmt).all()

    results = []
    for chunk, distance in rows:
        results.append({
            "document_id": chunk.document_id,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": 1.0 - float(distance),
        })

    return {"query": q, "count": len(results), "results": results}
