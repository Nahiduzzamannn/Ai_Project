from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), default="content_pdf")
    status: Mapped[str] = mapped_column(String(30), default="UPLOADED")

    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One document -> many chunks
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )