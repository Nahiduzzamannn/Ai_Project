"""OCR imports preserve full page text and offer editable question candidates."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.config import settings
from app.models.ocr_import import OcrImport
from app.schemas.question import QuestionCreate, QuestionOut
from app.api.v1.questions import _save
from app.services.ocr_service import MAX_BYTES, validate_upload

router = APIRouter()
UPLOAD_DIR = Path(settings.OCR_UPLOAD_DIR)


def _details(row: OcrImport) -> dict:
    return {"id": row.id, "filename": row.filename, "subject": row.subject,
            "status": row.status, "processed_pages": row.processed_pages,
            "total_pages": row.total_pages, "error": row.error,
            "pages": row.pages, "candidates": row.candidates,
            "created_at": row.created_at}


class AcceptQuestions(BaseModel):
    questions: list[QuestionCreate] = Field(..., min_length=1, max_length=200)


@router.post("/ocr/imports", status_code=202)
async def create_ocr_import(
    file: UploadFile = File(...),
    subject: str = Form(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    raw = await file.read(MAX_BYTES + 1)
    try:
        total_pages = validate_upload(filename, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    UPLOAD_DIR.mkdir(exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    path.write_bytes(raw)
    row = OcrImport(filename=filename, subject=subject.strip(), storage_path=str(path),
                    pages=[], candidates=[], status="queued", processed_pages=0,
                    total_pages=total_pages)
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return _details(row)


@router.get("/ocr/imports")
def list_ocr_imports(db: Session = Depends(get_db)):
    rows = db.scalars(select(OcrImport).order_by(OcrImport.created_at.desc()).limit(100)).all()
    return [{"id": row.id, "filename": row.filename, "subject": row.subject,
             "page_count": row.total_pages, "candidate_count": len(row.candidates),
             "status": row.status, "processed_pages": row.processed_pages,
             "total_pages": row.total_pages, "error": row.error,
             "created_at": row.created_at} for row in rows]


@router.get("/ocr/imports/{import_id}")
def get_ocr_import(import_id: int, db: Session = Depends(get_db)):
    row = db.get(OcrImport, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="OCR import not found")
    return _details(row)


@router.get("/ocr/imports/{import_id}/file")
def get_ocr_file(import_id: int, db: Session = Depends(get_db)):
    row = db.get(OcrImport, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="OCR import not found")
    path = Path(row.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Source file is missing")
    media_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                   ".jpeg": "image/jpeg", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff"}
    return FileResponse(path, media_type=media_types[path.suffix.lower()], content_disposition_type="inline")


@router.post("/ocr/imports/{import_id}/questions", response_model=list[QuestionOut])
def accept_ocr_questions(import_id: int, body: AcceptQuestions, db: Session = Depends(get_db)):
    row = db.get(OcrImport, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="OCR import not found")
    if row.status != "completed":
        raise HTTPException(status_code=409, detail="OCR import is not complete")
    items = [QuestionCreate(**{**q.model_dump(), "source": "ocr", "ocr_import_id": row.id,
                               "topic": q.topic or row.subject}) for q in body.questions]
    return _save(db, items)
