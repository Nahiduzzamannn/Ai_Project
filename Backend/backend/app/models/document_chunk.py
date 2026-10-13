from sqlalchemy import Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from pgvector.sqlalchemy import Vector

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(
    Vector(1536),  # OpenAI embedding size
    nullable=True,
)


    # relationship back to document
    document = relationship("Document", back_populates="chunks")