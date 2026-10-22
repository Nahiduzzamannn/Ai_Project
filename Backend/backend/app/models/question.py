from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # "mcq", "true_false", "short" or "broad"
    qtype: Mapped[str] = mapped_column(String(20), nullable=False, default="short", index=True)
    # MCQ options as a list of strings (null for other types)
    options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    marks: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # "manual", "upload" or "ai"
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    document_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    chapter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
