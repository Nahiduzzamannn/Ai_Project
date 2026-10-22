"""
RAG chat: retrieve the most relevant chunks for a chat message (hybrid
pgvector + Elasticsearch search), then ask the AI agent to answer and/or
write exam questions grounded in those chunks.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import llm_service, search_service
from app.services.embedding_service import generate_embedding

RRF_K = 60
MAX_HISTORY = 8          # previous messages sent to the AI
MAX_HISTORY_CHARS = 2500  # per message

SYSTEM_PROMPT = """You are a helpful teaching assistant inside a question-bank app.
You chat with a teacher about their textbook and write exam questions for them.

Rules:
- Base every answer and question ONLY on the numbered context passages given with the
  latest message. Cite passages like [1] or [2] in your reply.
- If the context does not contain the answer, say so honestly.
- Reply in the same language the teacher writes in (e.g. Bangla or English).
- When the teacher asks for questions (or asks to change, add or make harder/easier
  questions), put them in "questions". Otherwise "questions" must be [].
- When revising earlier questions, return the full revised list.
- Question rules:
  "mcq": exactly 4 options, "answer" is the exact text of the correct option, no "A)" prefixes.
  "true_false": options ["True", "False"], answer "True" or "False".
  "short": 1-3 sentence answer. "broad": a short paragraph model answer.
  Default marks: mcq 1, true_false 1, short 2, broad 5. difficulty: easy, medium or hard.

Always reply with JSON only, in exactly this shape:
{"reply": "<your message to the teacher, markdown allowed>",
 "questions": [{"qtype": "mcq", "text": "...", "options": ["...","...","...","..."], "answer": "...", "marks": 1, "difficulty": "medium"}]}"""


def _rrf(rankings: list[list[int]]) -> list[int]:
    scores: dict[int, float] = {}
    for ids in rankings:
        for rank, cid in enumerate(ids):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def retrieve(
    db: Session,
    query: str,
    document_id: int | None = None,
    chapter: Chapter | None = None,
) -> list[DocumentChunk]:
    """
    Pick chunks for the prompt, within LLM_CONTEXT_CHARS.
    - Hybrid ranking: pgvector similarity + Elasticsearch BM25, fused with RRF.
    - In chapter scope, after the best matches we also add chunks spread over the
      whole chapter, so generic requests ("make 5 MCQ") cover the full chapter.
    """
    budget = settings.LLM_CONTEXT_CHARS
    if chapter:
        document_id = chapter.document_id

    base = select(DocumentChunk).where(DocumentChunk.embedding.is_not(None))
    if document_id:
        base = base.where(DocumentChunk.document_id == document_id)
    if chapter:
        base = base.where(DocumentChunk.page_number.between(chapter.start_page, chapter.end_page))

    qvec = generate_embedding(query)
    vector_ids = [
        c.id for c in db.scalars(base.order_by(DocumentChunk.embedding.cosine_distance(qvec)).limit(20))
    ]
    es_hits = search_service.search_chunks(
        query, size=20, document_id=document_id,
        page_from=chapter.start_page if chapter else None,
        page_to=chapter.end_page if chapter else None,
    )
    rankings = [vector_ids] + ([[h["id"] for h in es_hits]] if es_hits else [])
    ranked_ids = _rrf(rankings)

    chunks = {c.id: c for c in db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ranked_ids)))}
    picked: list[DocumentChunk] = []
    used = 0
    # Best matches take up to 60% of the budget in chapter scope, all of it otherwise
    match_budget = budget * 0.6 if chapter else budget
    for cid in ranked_ids:
        c = chunks.get(cid)
        if c and used + len(c.content) <= match_budget:
            picked.append(c)
            used += len(c.content)

    if chapter:
        all_chunks = db.scalars(base.order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)).all()
        rest = [c for c in all_chunks if c.id not in {p.id for p in picked}]
        if rest:
            avg = sum(len(c.content) for c in rest) / len(rest)
            n = int((budget - used) // max(avg, 1))
            if n > 0:
                step = len(rest) / min(n, len(rest))
                for i in range(min(n, len(rest))):
                    c = rest[int(i * step)]
                    if used + len(c.content) <= budget:
                        picked.append(c)
                        used += len(c.content)

    return picked


def _history_message(m: dict) -> dict:
    content = m.get("content") or ""
    if m.get("role") == "assistant" and m.get("questions"):
        # Show the AI its earlier questions so follow-ups like "make Q2 harder" work
        content += "\n\nQuestions I wrote:\n" + json.dumps(m["questions"], ensure_ascii=False)
    return {"role": m["role"], "content": content[-MAX_HISTORY_CHARS:]}


def chat(
    db: Session,
    messages: list[dict],
    document_id: int | None = None,
    chapter: Chapter | None = None,
) -> dict:
    """messages: [{"role": "user"|"assistant", "content": str, "questions"?: [...]}]"""
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    # Use the last two user turns as the search query, so follow-ups keep their topic
    query = " ".join(user_msgs[-2:])
    if chapter:
        query = f"{chapter.title} {query}"

    chunks = retrieve(db, query, document_id, chapter)
    doc_titles = {
        d.id: d.title for d in db.scalars(
            select(Document).where(Document.id.in_({c.document_id for c in chunks} or {-1}))
        )
    }
    sources = [
        {
            "n": i + 1,
            "chunk_id": c.id,
            "document_id": c.document_id,
            "document_title": doc_titles.get(c.document_id, ""),
            "page_number": c.page_number,
            "snippet": " ".join(c.content.split())[:300],
        }
        for i, c in enumerate(chunks)
    ]
    context = "\n\n".join(
        f"[{i + 1}] ({doc_titles.get(c.document_id, '')}, page {c.page_number})\n{c.content}"
        for i, c in enumerate(chunks)
    ) or "(no matching text found in the documents)"

    scope = f'Chapter "{chapter.title}" (pages {chapter.start_page}-{chapter.end_page})' if chapter else (
        f'Document "{doc_titles.get(document_id, "")}"' if document_id else "All uploaded documents"
    )
    history = [_history_message(m) for m in messages[:-1][-MAX_HISTORY:]]
    last = messages[-1]["content"]
    prompt = f"Scope: {scope}\n\nContext passages:\n{context}\n\nTeacher's message:\n{last}"

    data = llm_service.chat_json(
        [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": prompt}]
    )
    reply = str(data.get("reply") or "").strip() if isinstance(data, dict) else ""
    raw_questions = data.get("questions", []) if isinstance(data, dict) else []
    questions = [
        q for q in (llm_service.clean_question(q, "medium") for q in raw_questions if isinstance(q, dict)) if q
    ]
    topic = chapter.title if chapter else (doc_titles.get(document_id) if document_id else None)
    for q in questions:
        q.update(
            topic=topic,
            document_id=chapter.document_id if chapter else document_id,
            chapter_id=chapter.id if chapter else None,
            source="ai",
        )
    return {"reply": reply or "(no reply)", "questions": questions, "sources": sources}
