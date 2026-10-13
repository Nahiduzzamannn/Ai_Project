from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class DocumentOut(BaseModel):
    id: int
    title: str
    doc_type: str
    status: str
    storage_path: str
    created_at: datetime
    owner_id: Optional[int] = None

    class Config:
        from_attributes = True


class ChunkSearchResult(BaseModel):
    """
    Schema for a single search result chunk.
    Returned by the semantic search endpoint.
    """
    chunk_id: int
    document_id: int
    document_title: str
    page_number: int
    chunk_index: int
    content: str
    similarity_score: float  # 0.0 to 1.0, higher means more similar

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """
    Complete response for semantic search queries.
    Contains the original query, matching chunks, and result count.
    """
    query: str
    results: List[ChunkSearchResult]
    total_results: int