"""
Document processing pipeline shared by upload and re-index:
PDF -> pages -> chunks + chapters -> local embeddings (pgvector) -> Elasticsearch.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import search_service
from app.services.embedding_service import generate_embeddings
from app.services.pdf_parser import (
    chunk_text, detect_chapters, extract_pdf_text_by_page, text_for_pages,
)

# How much of a chapter goes into its embedding (title + opening text)
CHAPTER_EMBED_CHARS = 1500


def chapter_embed_text(title: str, content: str) -> str:
    return f"{title}\n{content[:CHAPTER_EMBED_CHARS]}"


def process_document(db: Session, doc: Document) -> Document:
    """(Re)build chunks, chapters, embeddings and search indexes for a document."""
    pages = extract_pdf_text_by_page(doc.storage_path)

    # Chunks
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    chunk_rows = []
    for page_number, page_text in pages:
        for idx, chunk in enumerate(chunk_text(page_text)):
            chunk_rows.append(DocumentChunk(
                document_id=doc.id, page_number=page_number, chunk_index=idx, content=chunk,
            ))
    for row, emb in zip(chunk_rows, generate_embeddings([c.content for c in chunk_rows])):
        row.embedding = emb
    db.add_all(chunk_rows)

    # Chapters: keep manually added ones, re-detect the rest
    db.execute(delete(Chapter).where(Chapter.document_id == doc.id, Chapter.source != "manual"))
    manual = db.scalars(select(Chapter).where(Chapter.document_id == doc.id)).all()
    for ch in manual:
        ch.content = text_for_pages(pages, ch.start_page, ch.end_page)

    detected = [
        Chapter(
            document_id=doc.id,
            title=c["title"],
            start_page=c["start_page"],
            end_page=c["end_page"],
            source=c["source"],
            content=text_for_pages(pages, c["start_page"], c["end_page"]),
        )
        for c in detect_chapters(doc.storage_path, pages)
    ]
    chapters = sorted(list(manual) + detected, key=lambda c: (c.start_page, c.title))
    for i, ch in enumerate(chapters):
        ch.order_index = i
    embs = generate_embeddings([chapter_embed_text(c.title, c.content) for c in chapters])
    for ch, emb in zip(chapters, embs):
        ch.embedding = emb
    db.add_all(detected)

    doc.status = "PROCESSED"
    db.commit()
    db.refresh(doc)

    search_service.index_document(doc, chapters, chunk_rows)
    return doc
