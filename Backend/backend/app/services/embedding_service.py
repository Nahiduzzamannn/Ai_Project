"""
Embedding Service using a local fastembed model (free, runs on CPU, no API key).

The default model BAAI/bge-small-en-v1.5 produces 384-dimensional vectors.
The model is downloaded once (~70MB) on first use and loaded lazily so the app
starts fast.
"""

from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(settings.EMBEDDING_MODEL)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed many texts in one batch (much faster than one-by-one)."""
    if not texts:
        return []
    cleaned = [(t or "").strip() or " " for t in texts]
    return [vec.tolist() for vec in _model().embed(cleaned, batch_size=64)]


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for a single text.

    Returns empty list if text is empty.
    """
    text = (text or "").strip()
    if not text:
        return []
    return generate_embeddings([text])[0]
