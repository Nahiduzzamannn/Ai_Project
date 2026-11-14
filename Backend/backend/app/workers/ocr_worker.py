"""One-at-a-time PostgreSQL-backed Scan questions OCR worker.

Run from Backend/backend with: python -m app.workers.ocr_worker
"""

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ocr_import import OcrImport
from app.services.ocr_service import iter_page_images, recognize_page, split_questions

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def claim_next() -> int | None:
    """Recover stale claims and atomically claim the oldest queued import."""
    with SessionLocal.begin() as db:
        stale_before = utcnow() - timedelta(seconds=settings.OCR_STALE_SECONDS)
        db.execute(update(OcrImport).where(
            OcrImport.status == "processing",
            or_(OcrImport.heartbeat_at < stale_before, OcrImport.heartbeat_at.is_(None)),
        ).values(status="queued", heartbeat_at=None))
        row = db.scalar(select(OcrImport).where(OcrImport.status == "queued")
                        .order_by(OcrImport.id).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.status = "processing"
        row.heartbeat_at = utcnow()
        row.error = None
        return row.id


def process_import(import_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(OcrImport, import_id)
        if row is None:
            return
        filename = row.filename
        total_pages = row.total_pages
        source = Path(row.storage_path)
        already_done = row.processed_pages

    log.info("-" * 65)
    log.info("[Job #%s] Starting OCR: '%s' (%d total page(s), %d already done)",
             import_id, filename, total_pages, already_done)
    log.info("-" * 65)

    try:
        if not source.exists():
            raise FileNotFoundError(f"Source file is missing: {source}")
        for number, image in iter_page_images(source):
            if number <= already_done:
                continue
            with SessionLocal.begin() as db:
                row = db.get(OcrImport, import_id)
                row.heartbeat_at = utcnow()
            result = recognize_page(number, image, total_pages=total_pages)
            with SessionLocal.begin() as db:
                row = db.get(OcrImport, import_id)
                row.pages = [*row.pages, result]
                row.processed_pages = len(row.pages)
                row.heartbeat_at = utcnow()
        with SessionLocal.begin() as db:
            row = db.get(OcrImport, import_id)
            if row.processed_pages != row.total_pages:
                raise RuntimeError("OCR page count did not match the uploaded file")
            row.candidates = split_questions(row.pages)
            num_candidates = len(row.candidates)
            row.status = "completed" if any(page["text"].strip() for page in row.pages) else "failed"
            if row.status == "failed":
                row.error = "No text recognized. Try a clearer image or scan."
            row.heartbeat_at = None

        log.info("[Job #%s] ✓ Done! Extracted %d question candidate(s) from %d page(s).",
                 import_id, num_candidates, total_pages)
        log.info("-" * 65)
    except Exception as exc:
        log.exception("[Job #%s] ✗ OCR import failed: %s", import_id, exc)
        with SessionLocal.begin() as db:
            row = db.get(OcrImport, import_id)
            if row is not None:
                row.status = "failed"
                row.error = str(exc)[:500]
                row.heartbeat_at = None


def run(once: bool = False) -> None:
    while True:
        try:
            import_id = claim_next()
            if import_id is not None:
                process_import(import_id)
            elif once:
                return
            else:
                time.sleep(settings.OCR_WORKER_POLL_SECONDS)
        except KeyboardInterrupt:
            return
        except Exception:
            log.exception("OCR worker loop failed")
            if once:
                raise
            time.sleep(settings.OCR_WORKER_POLL_SECONDS)
        if once:
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Scan questions OCR imports")
    parser.add_argument("--once", action="store_true", help="Process at most one import and exit")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [OCR-WORKER] %(message)s",
        datefmt="%H:%M:%S",
    )
    run(once=args.once)
