from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

QType = Literal["mcq", "true_false", "short", "broad"]


class QuestionBase(BaseModel):
    text: str = Field(..., min_length=1)
    qtype: QType = "short"
    options: Optional[list[str]] = None
    answer: Optional[str] = None
    marks: float = Field(1.0, gt=0)
    difficulty: str = "medium"
    topic: Optional[str] = None
    document_id: Optional[int] = None
    chapter_id: Optional[int] = None

    @model_validator(mode="after")
    def check_options(self):
        if self.options is not None:
            self.options = [o.strip() for o in self.options if o and o.strip()]
        if self.qtype == "mcq" and (not self.options or len(self.options) < 2):
            raise ValueError("MCQ questions need at least 2 options")
        if self.qtype == "true_false":
            self.options = ["True", "False"]
        if self.qtype in ("short", "broad"):
            self.options = None
        return self


class QuestionCreate(QuestionBase):
    source: Literal["manual", "upload", "ai"] = "manual"


class QuestionUpdate(QuestionBase):
    pass


class QuestionOut(QuestionBase):
    id: int
    source: str
    created_at: datetime

    class Config:
        from_attributes = True

    # Stored rows are trusted; skip create-time validation when reading them
    @model_validator(mode="after")
    def check_options(self):
        return self


class QuestionList(BaseModel):
    total: int
    items: list[QuestionOut]


class PaperRequest(BaseModel):
    title: str = "Question Paper"
    subtitle: Optional[str] = None
    duration: Optional[str] = None
    instructions: Optional[str] = None

    # Either pick exact questions...
    question_ids: Optional[list[int]] = None
    # ...or pick randomly from the bank by count per type, with optional filters
    num_mcq: int = Field(0, ge=0)
    num_true_false: int = Field(0, ge=0)
    num_short: int = Field(0, ge=0)
    num_broad: int = Field(0, ge=0)
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    document_id: Optional[int] = None
    chapter_id: Optional[int] = None

    num_sets: int = Field(1, ge=1, le=26)
    shuffle_questions: bool = True
    shuffle_options: bool = True
    include_answer_key: bool = True
    seed: Optional[int] = None
