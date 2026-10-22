from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChapterOut(BaseModel):
    id: int
    document_id: int
    title: str
    order_index: int
    start_page: int
    end_page: int
    source: str

    class Config:
        from_attributes = True


class ChapterDetail(ChapterOut):
    content: str


class ChapterCreate(BaseModel):
    """Manually define a chapter by page range (when auto-detection misses it)."""
    title: str = Field(..., min_length=1, max_length=500)
    start_page: int = Field(..., ge=1)
    end_page: int = Field(..., ge=1)


class ChapterSearchHit(ChapterOut):
    document_title: str
    score: float
    matched_by: list[str]
    snippet: str


class GenerateQuestionsRequest(BaseModel):
    num_mcq: int = Field(5, ge=0, le=30)
    num_true_false: int = Field(0, ge=0, le=30)
    num_short: int = Field(3, ge=0, le=20)
    num_broad: int = Field(1, ge=0, le=10)
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "medium"
    focus: Optional[str] = Field(None, description="Optional sub-topic inside the chapter")
    instructions: Optional[str] = None
    save_to_bank: bool = False
