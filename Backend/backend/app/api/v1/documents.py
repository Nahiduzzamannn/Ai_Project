"""
Document API endpoints for PDF upload and semantic search.

This module provides:
- POST /documents/upload: Upload and process PDF files with embeddings
- GET /documents/search: Semantic search across document chunks using pgvector
"""

import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.deps import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentOut
from app.services.pdf_parser import extract_pdf_text_by_page, chunk_text
from app.services.embedding_service import generate_embedding

router = APIRouter()

UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF file, extract text, chunk it, generate embeddings, and store in DB.
    
    Process:
    1. Validate PDF file
    2. Save to disk with unique name
    3. Extract text page by page
    4. Split into chunks (1000 chars, 150 overlap)
    5. Generate OpenAI embeddings for each chunk
    6. Store chunks + embeddings in document_chunks table
    7. Update document status to PROCESSED
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

    # Extract and process PDF
    pages = extract_pdf_text_by_page(save_path)

    chunk_rows = []
    for page_number, page_text in pages:
        for idx, chunk in enumerate(chunk_text(page_text)):
            emb = None
            try:
                # Generate embedding for this chunk
                emb = generate_embedding(chunk)
            except Exception as e:
                # Keep app running even if embedding fails for one chunk
                # You can log the error here if needed
                print(f"Warning: Failed to generate embedding for chunk: {e}")
                emb = None

            chunk_rows.append(
                DocumentChunk(
                    document_id=doc.id,
                    page_number=page_number,
                    chunk_index=idx,
                    content=chunk,
                    embedding=emb if emb else None,
                )
            )

    # Save all chunks to database
    if chunk_rows:
        db.add_all(chunk_rows)
        db.commit()

    # Update document status to PROCESSED
    doc.status = "PROCESSED"
    db.commit()
    db.refresh(doc)

    return doc


@router.get("/documents/search")
def search_documents(
    q: str = Query(..., min_length=2, description="Search query text"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results to return"),
    db: Session = Depends(get_db),
):
    """
    Semantic search across document chunks using pgvector cosine similarity.
    
    Process:
    1. Generate embedding for the query text
    2. Use pgvector's cosine_distance to find similar chunks
    3. Return top_k most similar chunks with scores
    
    The cosine_distance operator returns values where:
    - 0 = identical vectors (most similar)
    - 2 = opposite vectors (least similar)
    We convert to similarity score: 1.0 - distance
    """
    # Generate embedding for search query
    query_vec = generate_embedding(q)

    # pgvector SQLAlchemy query using cosine distance
    # cosine_distance(vector) returns distance (lower = more similar)
    # We order by this distance to get nearest neighbors first
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

    # Format results
    results = []
    for chunk, distance in rows:
        # Convert distance to similarity score (0-1 scale, higher = more similar)
        score = 1.0 - float(distance)
        results.append({
            "document_id": chunk.document_id,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": score,
        })

    return {"query": q, "count": len(results), "results": results}