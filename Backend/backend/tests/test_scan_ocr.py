"""Focused checks for one-pass spotting, fallback, and durable OCR progress."""

import tempfile
import unittest
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import fitz
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.ocr_import import OcrImport
from app.services import ocr_service
from app.workers import ocr_worker


class SpottingTests(unittest.TestCase):
    def test_bangla_lines_and_boxes_are_preserved(self):
        locations = "".join(f"<|LOC_{n}|>" for n in (10, 20, 400, 20, 400, 50, 10, 50))
        lines = ocr_service.parse_spotting("১. প্রশ্ন কী?" + locations, 1000, 1000)
        self.assertEqual(lines, [{"text": "১. প্রশ্ন কী?", "bbox": [10, 20, 400, 50]}])

    def test_tesseract_runs_only_after_paddle_failure(self):
        image = Image.new("RGB", (100, 100), "white")
        with patch.object(ocr_service, "_llama_spotting", side_effect=RuntimeError("offline")), \
             patch.object(ocr_service, "_tesseract_image", return_value="fallback text") as fallback:
            page = ocr_service.recognize_page(1, image)
        self.assertEqual(page["method"], "tesseract")
        self.assertEqual(page["text"], "fallback text")
        fallback.assert_called_once()

    def test_spotting_boxes_map_to_original_image_after_resize(self):
        image = Image.new("RGB", (2000, 2000), "white")
        locations = "".join(f"<|LOC_{n}|>" for n in (100, 200, 300, 200, 300, 250, 100, 250))
        response = {"choices": [{"message": {"content": "Question" + locations}, "finish_reason": "stop"}]}
        with patch.object(ocr_service, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            lines = ocr_service._llama_spotting(image)
        self.assertEqual(lines[0]["bbox"], [200, 400, 600, 500])

    def test_question_number_and_options_are_kept_for_review(self):
        pages = [{"page": 1, "text": "১. প্রশ্ন কী?\nক) প্রথম\nখ) দ্বিতীয়"}]
        candidate = ocr_service.split_questions(pages)[0]
        self.assertEqual(candidate["text"], "১. প্রশ্ন কী?")
        self.assertEqual(candidate["qtype"], "mcq")
        self.assertEqual(candidate["options"], ["প্রথম", "দ্বিতীয়"])


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        OcrImport.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.session_patch = patch.object(ocr_worker, "SessionLocal", self.sessions)
        self.session_patch.start()
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.session_patch.stop()
        self.tempdir.cleanup()
        self.engine.dispose()

    def test_pdf_job_checkpoints_pages_and_completes(self):
        pdf_path = Path(self.tempdir.name) / "questions.pdf"
        with fitz.open() as document:
            for _ in range(2):
                page = document.new_page()
                page.insert_text((50, 50), "This PDF has embedded text")
            document.save(pdf_path)
        with self.sessions.begin() as db:
            row = OcrImport(filename="questions.pdf", subject="Bangla", storage_path=str(pdf_path),
                            pages=[], candidates=[], status="queued", processed_pages=0, total_pages=2)
            db.add(row)
            db.flush()
            import_id = row.id
        with patch.object(ocr_worker, "recognize_page", side_effect=lambda n, image: {
                "page": n, "text": f"{n}. Question?", "method": "paddle_bangla", "lines": []}) as recognize:
            self.assertEqual(ocr_worker.claim_next(), import_id)
            ocr_worker.process_import(import_id)
        self.assertEqual(recognize.call_count, 2)
        with self.sessions() as db:
            row = db.get(OcrImport, import_id)
            self.assertEqual(row.status, "completed")
            self.assertEqual(row.processed_pages, 2)
            self.assertEqual(len(row.pages), 2)
            self.assertEqual(len(row.candidates), 2)

    def test_stale_job_resumes_after_checkpoint(self):
        pdf_path = Path(self.tempdir.name) / "resume.pdf"
        with fitz.open() as document:
            document.new_page()
            document.new_page()
            document.save(pdf_path)
        first_page = {"page": 1, "text": "1. Earlier question?", "method": "paddle_bangla", "lines": []}
        with self.sessions.begin() as db:
            row = OcrImport(filename="resume.pdf", subject="Bangla", storage_path=str(pdf_path),
                            pages=[first_page], candidates=[], status="processing",
                            processed_pages=1, total_pages=2,
                            heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=1))
            db.add(row)
            db.flush()
            import_id = row.id
        with patch.object(ocr_worker, "recognize_page", return_value={
                "page": 2, "text": "2. New question?", "method": "paddle_bangla", "lines": []}) as recognize:
            self.assertEqual(ocr_worker.claim_next(), import_id)
            ocr_worker.process_import(import_id)
        recognize.assert_called_once()
        with self.sessions() as db:
            row = db.get(OcrImport, import_id)
            self.assertEqual(row.status, "completed")
            self.assertEqual([page["page"] for page in row.pages], [1, 2])


class ApiTests(unittest.TestCase):
    def test_upload_returns_queued_job_and_blocks_early_acceptance(self):
        from app.api.v1 import ocr as ocr_api
        from app.core.deps import get_db
        from app.main import app

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        OcrImport.__table__.create(engine)
        sessions = sessionmaker(bind=engine)
        tempdir = tempfile.TemporaryDirectory()
        original_upload_dir = ocr_api.UPLOAD_DIR
        ocr_api.UPLOAD_DIR = Path(tempdir.name)

        def test_db():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        try:
            image = Image.new("RGB", (100, 100), "white")
            raw = io.BytesIO()
            image.save(raw, format="PNG")
            with TestClient(app) as client:
                response = client.post("/api/v1/ocr/imports", files={"file": ("scan.png", raw.getvalue(), "image/png")},
                                       data={"subject": "Bangla"})
                self.assertEqual(response.status_code, 202)
                job = response.json()
                self.assertEqual(job["status"], "queued")
                self.assertEqual(job["total_pages"], 1)
                self.assertEqual(client.get(f"/api/v1/ocr/imports/{job['id']}").json()["processed_pages"], 0)
                rejected = client.post(f"/api/v1/ocr/imports/{job['id']}/questions", json={"questions": [{
                    "text": "Question?", "qtype": "short", "marks": 1, "difficulty": "medium"
                }]})
                self.assertEqual(rejected.status_code, 409)
        finally:
            app.dependency_overrides.pop(get_db, None)
            ocr_api.UPLOAD_DIR = original_upload_dir
            tempdir.cleanup()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
