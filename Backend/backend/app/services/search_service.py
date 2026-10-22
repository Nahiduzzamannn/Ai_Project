"""
Elasticsearch service: keyword (BM25) search over chapters, chunks and questions.

pgvector handles semantic search; Elasticsearch handles exact/keyword matching.
The two are combined in the chapter search (hybrid search).

If Elasticsearch is not reachable every function degrades gracefully:
indexing is skipped and search functions return None so callers can fall
back to Postgres.
"""

import logging
import time

from app.core.config import settings

log = logging.getLogger(__name__)

CHAPTERS = f"{settings.ES_INDEX_PREFIX}_chapters"
CHUNKS = f"{settings.ES_INDEX_PREFIX}_chunks"
QUESTIONS = f"{settings.ES_INDEX_PREFIX}_questions"

MAPPINGS = {
    CHAPTERS: {
        "properties": {
            "document_id": {"type": "integer"},
            "document_title": {"type": "text"},
            "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
            "content": {"type": "text"},
            "start_page": {"type": "integer"},
            "end_page": {"type": "integer"},
        }
    },
    CHUNKS: {
        "properties": {
            "document_id": {"type": "integer"},
            "page_number": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text"},
        }
    },
    QUESTIONS: {
        "properties": {
            "text": {"type": "text"},
            "options": {"type": "text"},
            "answer": {"type": "text"},
            "qtype": {"type": "keyword"},
            "difficulty": {"type": "keyword"},
            "topic": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
            "document_id": {"type": "integer"},
            "chapter_id": {"type": "integer"},
        }
    },
}

_client = None
_last_failure = 0.0
RETRY_AFTER_SECONDS = 30


def get_client():
    """Return a connected Elasticsearch client, or None if ES is unavailable."""
    global _client, _last_failure
    if _client is not None:
        return _client
    if time.time() - _last_failure < RETRY_AFTER_SECONDS:
        return None
    try:
        from elasticsearch import Elasticsearch

        kwargs = {"request_timeout": 10}
        if settings.ELASTICSEARCH_API_KEY:
            kwargs["api_key"] = settings.ELASTICSEARCH_API_KEY
        client = Elasticsearch(settings.ELASTICSEARCH_URL, **kwargs)
        if not client.ping():
            raise ConnectionError(f"Cannot reach {settings.ELASTICSEARCH_URL}")
        for index, mapping in MAPPINGS.items():
            if not client.indices.exists(index=index):
                client.indices.create(index=index, mappings=mapping)
        _client = client
        log.info("Connected to Elasticsearch at %s", settings.ELASTICSEARCH_URL)
        return _client
    except Exception as e:
        _last_failure = time.time()
        log.warning("Elasticsearch unavailable (%s); using Postgres fallback", e)
        return None


def is_available() -> bool:
    return get_client() is not None


def _bulk(actions: list[dict]):
    es = get_client()
    if es is None or not actions:
        return
    from elasticsearch import helpers
    try:
        helpers.bulk(es, actions, refresh=True)
    except Exception as e:
        log.warning("Elasticsearch bulk indexing failed: %s", e)


def _delete_by_query(index: str, query: dict):
    es = get_client()
    if es is None:
        return
    try:
        es.delete_by_query(index=index, query=query, refresh=True, conflicts="proceed")
    except Exception as e:
        log.warning("Elasticsearch delete failed: %s", e)


# ---------- Documents (chapters + chunks) ----------

def index_document(document, chapters, chunks):
    """(Re)index all chapters and chunks of one document."""
    delete_document(document.id)
    actions = [
        {
            "_index": CHAPTERS,
            "_id": str(ch.id),
            "_source": {
                "document_id": document.id,
                "document_title": document.title,
                "title": ch.title,
                "content": ch.content,
                "start_page": ch.start_page,
                "end_page": ch.end_page,
            },
        }
        for ch in chapters
    ]
    actions += [
        {
            "_index": CHUNKS,
            "_id": str(c.id),
            "_source": {
                "document_id": document.id,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "content": c.content,
            },
        }
        for c in chunks
    ]
    _bulk(actions)


def index_chapter(document, chapter):
    _bulk([{
        "_index": CHAPTERS,
        "_id": str(chapter.id),
        "_source": {
            "document_id": document.id,
            "document_title": document.title,
            "title": chapter.title,
            "content": chapter.content,
            "start_page": chapter.start_page,
            "end_page": chapter.end_page,
        },
    }])


def delete_chapter(chapter_id: int):
    es = get_client()
    if es is None:
        return
    try:
        es.delete(index=CHAPTERS, id=str(chapter_id), refresh=True)
    except Exception:
        pass


def delete_document(document_id: int):
    for index in (CHAPTERS, CHUNKS):
        _delete_by_query(index, {"term": {"document_id": document_id}})


def search_chapters(q: str, document_id: int | None = None, size: int = 10) -> list[dict] | None:
    """BM25 chapter search. Title matches count 3x more than body matches."""
    es = get_client()
    if es is None:
        return None
    query: dict = {
        "bool": {
            "should": [
                {"multi_match": {"query": q, "fields": ["title^3", "content"]}},
                {"match_phrase": {"title": {"query": q, "boost": 5}}},
            ],
            "minimum_should_match": 1,
        }
    }
    if document_id:
        query["bool"]["filter"] = [{"term": {"document_id": document_id}}]
    try:
        res = es.search(index=CHAPTERS, query=query, size=size, source=["title"])
        return [{"id": int(h["_id"]), "score": h["_score"]} for h in res["hits"]["hits"]]
    except Exception as e:
        log.warning("Elasticsearch chapter search failed: %s", e)
        return None


def search_chunks(
    q: str,
    size: int = 10,
    document_id: int | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
) -> list[dict] | None:
    """BM25 chunk search, optionally limited to one document / page range."""
    es = get_client()
    if es is None:
        return None
    filters: list[dict] = []
    if document_id:
        filters.append({"term": {"document_id": document_id}})
    if page_from is not None and page_to is not None:
        filters.append({"range": {"page_number": {"gte": page_from, "lte": page_to}}})
    query = {"bool": {"must": [{"match": {"content": q}}], "filter": filters}}
    try:
        res = es.search(index=CHUNKS, query=query, size=size, source=False)
        return [{"id": int(h["_id"]), "score": h["_score"]} for h in res["hits"]["hits"]]
    except Exception as e:
        log.warning("Elasticsearch chunk search failed: %s", e)
        return None


# ---------- Question bank ----------

def _question_source(q) -> dict:
    return {
        "text": q.text,
        "options": " | ".join(q.options or []),
        "answer": q.answer or "",
        "qtype": q.qtype,
        "difficulty": q.difficulty,
        "topic": q.topic or "",
        "document_id": q.document_id,
        "chapter_id": q.chapter_id,
    }


def index_questions(questions):
    _bulk([
        {"_index": QUESTIONS, "_id": str(q.id), "_source": _question_source(q)}
        for q in questions
    ])


def delete_question(question_id: int):
    es = get_client()
    if es is None:
        return
    try:
        es.delete(index=QUESTIONS, id=str(question_id), refresh=True)
    except Exception:
        pass


def search_question_ids(q: str, size: int = 500) -> list[int] | None:
    """Full-text search over question text, options, answer and topic."""
    es = get_client()
    if es is None:
        return None
    try:
        res = es.search(
            index=QUESTIONS,
            query={
                "multi_match": {
                    "query": q,
                    "fields": ["text^2", "topic^2", "options", "answer"],
                    "fuzziness": "AUTO",
                }
            },
            size=size,
            source=False,
        )
        return [int(h["_id"]) for h in res["hits"]["hits"]]
    except Exception as e:
        log.warning("Elasticsearch question search failed: %s", e)
        return None
