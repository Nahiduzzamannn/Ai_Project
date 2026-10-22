# Import all models here so Alembic can discover them
from app.models.document import Document  # noqa: F401

from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.chapter import Chapter  # noqa: F401
from app.models.question import Question  # noqa: F401
