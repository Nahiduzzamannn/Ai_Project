"""Focused checks for Gemini Vision extraction, Tesseract fallback, and durable OCR progress."""

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


class VisionExtractionTests(unittest.TestCase):
    def test_gemini_vision_extracts_clean_questions_and_options(self):
        image = Image.new("RGB", (100, 100), "white")
        mock_response = {
            "full_text": "১. সালোকসংশ্লেষণ কী?\nক) প্রথম\nখ) দ্বিতীয়",
            "questions": [
                {
                    "text": "সালোকসংশ্লেষণ কী?",
                    "qtype": "mcq",
                    "options": ["ক) প্রথম", "খ) দ্বিতীয়"],
                    "answer": "ক) প্রথম",
                    "marks": 1.0,
                    "difficulty": "easy",
                }
            ],
        }
        with patch.object(ocr_service, "_gemini_vision_extract", return_value=mock_response):
            page = ocr_service.recognize_page(1, image)
        self.assertEqual(page["method"], "gemini_vision")
        self.assertEqual(len(page["questions"]), 1)
        self.assertEqual(page["questions"][0]["text"], "সালোকসংশ্লেষণ কী?")
        self.assertEqual(page["questions"][0]["options"], ["ক) প্রথম", "খ) দ্বিতীয়"])

    def test_gemini_rotates_to_second_key_on_failure(self):
        image = Image.new("RGB", (100, 100), "white")
        mock_success = {
            "full_text": "সফল টেক্সট",
            "questions": [{"text": "প্রশ্ন ১", "qtype": "short", "options": None}],
        }
        with patch.object(ocr_service.settings, "GEMINI_API_KEY", "bad_key,good_key"):
            def fake_extract(img, api_key=None):
                if api_key == "bad_key":
                    raise RuntimeError("Quota exceeded (429)")
                return mock_success

            with patch.object(ocr_service, "_gemini_vision_extract", side_effect=fake_extract):
                page = ocr_service.recognize_page(1, image)

        self.assertEqual(page["method"], "gemini_vision")
        self.assertEqual(len(page["questions"]), 1)
        self.assertEqual(page["questions"][0]["text"], "প্রশ্ন ১")

    def test_mcq_without_options_degrades_to_short_to_prevent_422(self):
        image = Image.new("RGB", (100, 100), "white")
        mock_response = {
            "full_text": "কোন অপশন নেই এমন প্রশ্ন",
            "questions": [{
                "text": "অপশনহীন প্রশ্ন",
                "qtype": "mcq",
                "options": [],
                "answer": None,
            }],
        }
        with patch.object(ocr_service, "_gemini_vision_extract", return_value=mock_response):
            page = ocr_service.recognize_page(1, image)

        self.assertEqual(page["questions"][0]["qtype"], "short")
        self.assertIsNone(page["questions"][0]["options"])

    def test_tesseract_runs_when_gemini_fails(self):
        image = Image.new("RGB", (100, 100), "white")
        with patch.object(ocr_service, "_gemini_vision_extract", side_effect=RuntimeError("offline")), \
             patch.object(ocr_service, "_tesseract_image", return_value="fallback text") as fallback:
            page = ocr_service.recognize_page(1, image)
        self.assertEqual(page["method"], "tesseract")
        self.assertEqual(page["text"], "fallback text")
        fallback.assert_called_once()

    def test_question_number_is_cleaned_for_tesseract_fallback(self):
        pages = [{"page": 1, "text": "১. প্রশ্ন কী?\nক) প্রথম\nখ) দ্বিতীয়"}]
        candidate = ocr_service.split_questions(pages)[0]
        # Leading number '১.' is cleaned to avoid double numbering in question paper builders
        self.assertEqual(candidate["text"], "প্রশ্ন কী?")
        self.assertEqual(candidate["qtype"], "mcq")
        self.assertEqual(candidate["options"], ["প্রথম", "দ্বিতীয়"])


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
        with patch.object(ocr_worker, "recognize_page", side_effect=lambda n, image, *args, **kwargs: {
                "page": n, "text": f"{n}. Question?", "method": "gemini_vision",
                "questions": [{"text": f"Question {n}?", "qtype": "short", "options": None, "page": n}]}):
            self.assertEqual(ocr_worker.claim_next(), import_id)
            ocr_worker.process_import(import_id)
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
        first_page = {"page": 1, "text": "1. Earlier question?", "method": "gemini_vision",
                      "questions": [{"text": "Earlier question?", "qtype": "short", "options": None, "page": 1}]}
        with self.sessions.begin() as db:
            row = OcrImport(filename="resume.pdf", subject="English", storage_path=str(pdf_path),
                            pages=[first_page], candidates=[], status="processing", processed_pages=1,
                            total_pages=2, heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=1200))
            db.add(row)
            db.flush()
            import_id = row.id
        with patch.object(ocr_worker, "recognize_page", side_effect=lambda n, image, *args, **kwargs: {
                "page": n, "text": "2. Second question?", "method": "gemini_vision",
                "questions": [{"text": "Second question?", "qtype": "short", "options": None, "page": n}]}) as recognize:
            self.assertEqual(ocr_worker.claim_next(), import_id)
            ocr_worker.process_import(import_id)
        self.assertEqual(recognize.call_count, 1)
        with self.sessions() as db:
            row = db.get(OcrImport, import_id)
            self.assertEqual(row.status, "completed")
            self.assertEqual(row.processed_pages, 2)
            self.assertEqual(len(row.pages), 2)


class ApiTests(unittest.TestCase):
    def setUp(self):
        from app.main import app
        from app.core.deps import get_db

        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        OcrImport.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def override_get_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        from app.main import app
        from app.core.deps import get_db

        app.dependency_overrides.pop(get_db, None)
        self.tempdir.cleanup()
        self.engine.dispose()

    def test_accept_questions_requires_completed_import(self):
        with self.sessions.begin() as db:
            row = OcrImport(filename="scan.png", subject="History", storage_path="missing.png",
                            pages=[], candidates=[], status="queued", processed_pages=0, total_pages=1)
            db.add(row)
            db.flush()
            import_id = row.id
        res = self.client.post(f"/api/v1/ocr/imports/{import_id}/questions",
                               json={"questions": [{"text": "When?", "qtype": "short"}]})
        self.assertEqual(res.status_code, 409)


if __name__ == "__main__":
    unittest.main()
