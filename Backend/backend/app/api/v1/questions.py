"""
Question bank endpoints:
- GET    /questions: list / filter / full-text search (Elasticsearch, Postgres fallback)
- GET    /questions/topics: distinct topics for filters
- GET    /questions/template.csv: example CSV for bulk upload
- POST   /questions: add one question
- POST   /questions/bulk: add many questions (e.g. AI-generated ones)
- POST   /questions/upload: bulk upload from a .csv or .json file
- PUT    /questions/{id}, DELETE /questions/{id}
- POST   /questions/paper: build a shuffled multi-set question paper PDF
"""

import csv
import io
import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.question import Question
from app.schemas.question import (
    PaperRequest, QuestionCreate, QuestionList, QuestionOut, QuestionUpdate,
)
from app.services import paper_service, search_service

router = APIRouter()

CSV_COLUMNS = ["text", "qtype", "options", "answer", "marks", "difficulty", "topic"]
CSV_EXAMPLE = [
    ["What is the powerhouse of the cell?", "mcq", "Nucleus|Mitochondria|Ribosome|Golgi body",
     "Mitochondria", "1", "easy", "Cell Biology"],
    ["Plants make food by photosynthesis.", "true_false", "", "True", "1", "easy", "Plants"],
    ["Define osmosis.", "short", "", "Movement of water across a semi-permeable membrane...",
     "2", "medium", "Cell Biology"],
    ["Explain the process of photosynthesis.", "broad", "", "", "5", "hard", "Plants"],
]


def _apply_filters(stmt, qtype, topic, difficulty, document_id, chapter_id, source):
    if qtype:
        stmt = stmt.where(Question.qtype == qtype)
    if topic:
        stmt = stmt.where(Question.topic == topic)
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if document_id:
        stmt = stmt.where(Question.document_id == document_id)
    if chapter_id:
        stmt = stmt.where(Question.chapter_id == chapter_id)
    if source:
        stmt = stmt.where(Question.source == source)
    return stmt


@router.get("/questions", response_model=QuestionList)
def list_questions(
    q: str | None = Query(None, description="Full-text search"),
    qtype: str | None = None,
    topic: str | None = None,
    difficulty: str | None = None,
    document_id: int | None = None,
    chapter_id: int | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = _apply_filters(select(Question), qtype, topic, difficulty, document_id, chapter_id, source)
    ranked_ids: list[int] | None = None
    if q and q.strip():
        ranked_ids = search_service.search_question_ids(q.strip())
        if ranked_ids is not None:
            stmt = stmt.where(Question.id.in_(ranked_ids or [-1]))
        else:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Question.text.ilike(like), Question.topic.ilike(like),
                                  Question.answer.ilike(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if ranked_ids:
        # Keep Elasticsearch relevance order
        rows = db.scalars(stmt).all()
        order = {qid: i for i, qid in enumerate(ranked_ids)}
        rows = sorted(rows, key=lambda r: order.get(r.id, 1e9))[offset: offset + limit]
    else:
        rows = db.scalars(stmt.order_by(Question.created_at.desc(), Question.id.desc())
                          .offset(offset).limit(limit)).all()
    return {"total": total, "items": rows}


@router.get("/questions/topics", response_model=list[str])
def list_topics(db: Session = Depends(get_db)):
    return [t for t in db.scalars(
        select(Question.topic).where(Question.topic.is_not(None)).distinct().order_by(Question.topic)
    ) if t]


@router.get("/questions/template.csv")
def csv_template():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(CSV_EXAMPLE)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="question_template.csv"'},
    )


def _save(db: Session, items: list[QuestionCreate]) -> list[Question]:
    rows = [Question(**item.model_dump()) for item in items]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    search_service.index_questions(rows)
    return rows


@router.post("/questions", response_model=QuestionOut)
def create_question(body: QuestionCreate, db: Session = Depends(get_db)):
    return _save(db, [body])[0]


@router.post("/questions/bulk", response_model=list[QuestionOut])
def create_questions_bulk(body: list[QuestionCreate], db: Session = Depends(get_db)):
    if not body:
        raise HTTPException(status_code=400, detail="No questions given")
    return _save(db, body)


def _parse_upload(filename: str, raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    if filename.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("questions", [])
        if not isinstance(data, list):
            raise ValueError("JSON must be a list of questions or {\"questions\": [...]}")
        return data
    if filename.endswith(".csv"):
        rows = []
        for row in csv.DictReader(io.StringIO(text)):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("text"):
                continue
            opts = row.get("options") or ""
            rows.append({
                "text": row["text"],
                "qtype": (row.get("qtype") or row.get("type") or "short").lower(),
                "options": [o for o in opts.split("|")] if opts else None,
                "answer": row.get("answer") or None,
                "marks": float(row["marks"]) if row.get("marks") else 1.0,
                "difficulty": (row.get("difficulty") or "medium").lower(),
                "topic": row.get("topic") or None,
            })
        return rows
    raise ValueError("Upload a .csv or .json file")


@router.post("/questions/upload")
async def upload_questions(
    file: UploadFile = File(...),
    topic: str | None = Query(None, description="Topic to use when a row has none"),
    db: Session = Depends(get_db),
):
    name = (file.filename or "").lower()
    try:
        raw_items = _parse_upload(name, await file.read())
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    valid: list[QuestionCreate] = []
    errors: list[dict] = []
    for i, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            errors.append({"row": i, "error": "Not an object"})
            continue
        item = {**item, "source": "upload"}
        if topic and not item.get("topic"):
            item["topic"] = topic
        try:
            valid.append(QuestionCreate(**item))
        except ValidationError as e:
            errors.append({"row": i, "error": "; ".join(err["msg"] for err in e.errors())})

    saved = _save(db, valid) if valid else []
    return {"imported": len(saved), "failed": len(errors), "errors": errors[:50]}


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, body: QuestionUpdate, db: Session = Depends(get_db)):
    row = db.get(Question, question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Question not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    search_service.index_questions([row])
    return row


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    row = db.get(Question, question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(row)
    db.commit()
    search_service.delete_question(question_id)
    return {"deleted": question_id}


@router.post("/questions/paper")
def build_paper(body: PaperRequest, db: Session = Depends(get_db)):
    """
    Build a question paper PDF with `num_sets` sets (A, B, C...).
    Questions come from `question_ids`, or are picked at random from the bank
    by count per type (num_mcq, num_short, ...) with optional filters.
    """
    seed = body.seed if body.seed is not None else random.randrange(1_000_000)
    rng = random.Random(seed)

    if body.question_ids:
        found = {q.id: q for q in db.scalars(
            select(Question).where(Question.id.in_(body.question_ids))
        )}
        missing = [i for i in body.question_ids if i not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Questions not found: {missing}")
        chosen = [found[i] for i in body.question_ids]
    else:
        wanted = {"mcq": body.num_mcq, "true_false": body.num_true_false,
                  "short": body.num_short, "broad": body.num_broad}
        if sum(wanted.values()) == 0:
            raise HTTPException(status_code=400, detail="Choose questions or set how many of each type")
        chosen = []
        for qtype, n in wanted.items():
            if n <= 0:
                continue
            pool = db.scalars(_apply_filters(
                select(Question), qtype, body.topic, body.difficulty,
                body.document_id, body.chapter_id, None,
            ).order_by(Question.id)).all()
            if len(pool) < n:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only {len(pool)} '{qtype}' questions match the filters, but {n} requested",
                )
            chosen += rng.sample(pool, n)

    questions = [
        {"id": q.id, "qtype": q.qtype, "text": q.text, "options": q.options,
         "answer": q.answer, "marks": q.marks}
        for q in chosen
    ]
    sets = paper_service.build_sets(
        questions, body.num_sets, body.shuffle_questions, body.shuffle_options, seed
    )
    pdf = paper_service.render_pdf(
        sets, body.title, body.subtitle, body.duration, body.instructions, body.include_answer_key
    )
    filename = f"question_paper_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Paper-Seed": str(seed),
        },
    )
