# Migration Plan: Scan Questions to Gemini Vision API

> **Status:** Completed (Verified & Tested)  
> **Last Updated:** 2026-11-14  
> **Author/Owner:** AI Assistant & Project Team  
> **Purpose:** Replace local heavy PaddleOCR-VL (~1.8 GB GGUF + Docker) with Google Gemini Vision API for high accuracy, instant processing (~2-3s/page), zero disk bloat, and Render Free Tier compatibility, while keeping Tesseract as an offline fallback.

---

## 1. Objectives & Architectural Requirements

1. **Render Free Tier Ready:**
   - Eliminated Docker container and the 1.8 GB `.runtime/models/` download.
   - Server memory consumption stays well below 512 MB RAM.
2. **Superior Accuracy & Speed:**
   - Reduced per-page latency from 70+ seconds to 2–3 seconds.
   - High-precision recognition of complex Bengali script, handwritten notes, noisy phone photos, and LaTeX math.
3. **Advanced Question Formatting:**
   - **Standard MCQs:** Single question with 4 options.
   - **Multi-statement MCQs (বহুপদী সমাপ্তিসূচক প্রশ্ন):** Roman statements (`i, ii, iii`) and "নিচের কোনটি সঠিক?" are preserved inside `text`, with only the final options (`i ও ii`, etc.) in `options`.
   - **Context/Stem Questions (উদ্দীপক ভিত্তিক প্রশ্ন):** Shared context prepended to each question text so questions remain self-contained.
   - **Creative / CQ Questions (সৃজনশীল প্রশ্ন):** Segment into `short` (ক, খ) and `broad` (গ, ঘ).
   - **Mathematical / Chemical formulas:** Converted into KaTeX/LaTeX format (`$...$` or `$$...$$`).
   - **No Double-Numbering:** Cleaned leading numbers (`১.`, `1.`, `প্রশ্ন ১:`) so question paper builders do not output `1. ১. প্রশ্ন`.
4. **Preserve Tesseract:**
   - Tesseract and `tessdata` are completely preserved. If `GEMINI_API_KEY` is missing or network is unreachable, it gracefully falls back to Tesseract.

---

## 2. Architecture Comparison

### Before (Local Docker + Brittle Regex)
```text
[Image / PDF Page]
       │
       ▼
[Docker: llama.cpp + PaddleOCR-VL-1.6 (1.8 GB GGUF)]  ──(Takes 70-90s)
       │
       ▼
[Raw Extracted Text with LOC tags]
       │
       ▼
[Regex split_questions()]  ──(Breaks on horizontal MCQs, multi-page, CQ)
       │
       ▼
[OcrTab Candidates]
```

### After (Cloud Gemini Vision - Direct Image to JSON)
```text
[Image / PDF Page]
       │
       ▼ (PyMuPDF renders 1 page to JPEG buffer)
[Gemini Vision API: gemini-3.5-flash] ──(Takes 2-3s)
       │
       ├──► 1. full_text: Full clean page text (for transcript/copy tab)
       └──► 2. questions: Structured JSON candidates (MCQ, Short, Broad, CQ, LaTeX)
       │
       ▼ (Fallback only if API key missing/offline: Tesseract ben+eng)
[OcrTab Candidates with Option/Answer Picker & Live KaTeX Preview]
```

---

## 3. Gemini Vision System Prompt & Schema

### Structured JSON Schema
```json
{
  "full_text": "পুরো পৃষ্ঠার পরিচ্ছন্ন বাংলা ও ইংরেজি টেক্সট...",
  "questions": [
    {
      "text": "প্রশ্ন (উদ্দীপক বা i, ii, iii স্টেটমেন্ট থাকলে তা সহ, কিন্তু শুরুর প্রশ্ন নম্বর ছাড়া)",
      "qtype": "mcq | short | broad | true_false",
      "options": ["ক) অপশন ১", "খ) অপশন ২", "গ) অপশন ৩", "ঘ) অপশন ৪"],
      "answer": "সঠিক অপশনের টেক্সট (যদি ছবিতে উত্তর চিহ্নিত থাকে বা নিশ্চিত হওয়া যায়, অন্যথায় null)",
      "marks": 1.0,
      "difficulty": "easy | medium | hard"
    }
  ]
}
```

---

## 4. Master Task Breakdown & Progress

### Phase 1: Configuration & Environment Setup
- [x] **Task 1.1:** Update `Backend/backend/app/core/config.py` to declare `GEMINI_API_KEY` and `GEMINI_MODEL` (`gemini-3.5-flash`).
- [x] **Task 1.2:** Write a verification helper to check if `GEMINI_API_KEY` is present and functional.

### Phase 2: Core Vision Service (`app/services/ocr_service.py`)
- [x] **Task 2.1:** Implement `_gemini_vision_extract(image: Image.Image) -> dict` in `ocr_service.py` using `google-genai`.
- [x] **Task 2.2:** Formulate system prompt for Bangladeshi/English question patterns (multi-statement MCQs, stems, LaTeX KaTeX).
- [x] **Task 2.3:** Implement clean question stem stripping (remove leading numbers).
- [x] **Task 2.4:** Update `recognize_page(number, image)` to prioritize Gemini Vision, and fall back to Tesseract if API key is unset or network fails.
- [x] **Task 2.5:** Keep Tesseract intact and working (retained `pytesseract` and `.runtime/tessdata`).

### Phase 3: Background Worker & Dev Runner (`ocr_worker.py` & `run_scan_dev.py`)
- [x] **Task 3.1:** Update `app/workers/ocr_worker.py` to ingest Gemini's structured `questions` list directly into `candidates`, retaining `full_text` in `row.pages`.
- [x] **Task 3.2:** Update `Backend/backend/run_scan_dev.py` to remove Docker requirement and run FastAPI + OCR worker directly without local model downloads.

### Phase 4: Frontend UI Enhancements (`OcrTab.jsx`)
- [x] **Task 4.1:** Update method badge to show "Gemini Vision" (or "Tesseract fallback" if offline).
- [x] **Task 4.2:** Allow teacher to pick the correct MCQ option using radio buttons before saving to Question Bank.
- [x] **Task 4.3:** Add an "+ প্রশ্ন যোগ করুন" button so teachers can manually create candidates, and delete button to remove candidates.

### Phase 5: Testing & Verification
- [x] **Task 5.1:** Create unit tests in `Backend/backend/tests/test_scan_ocr.py` testing JSON parsing, multi-statement MCQs, and Tesseract fallback.
- [x] **Task 5.2:** Run the test suite and verify end-to-end question extraction.
- [x] **Task 5.3:** Added `google-genai` to `Backend/backend/requirements.txt`.

### Phase 6: Bengali PDF Font Fix & UI Enhancements
- [x] **Task 6.1:** Polling interval relaxed from 2s to 5s in `OcrTab.jsx` to reduce network/server load.
- [x] **Task 6.2:** Upgraded file upload input in `OcrTab.jsx` to a clean dashed-border card with styled button, helper text, and selected file details.
- [x] **Task 6.3:** Render KaTeX equations (`$...$`) inside MCQ radio options and question preview in `OcrTab.jsx`.
- [x] **Task 6.4:** Fixed broken Bengali font / tofu boxes in Question Paper PDF generation (`paper_service.py`):
  - Bundled `Kalpurush.ttf` into `Backend/backend/app/assets/fonts/`.
  - Added `uharfbuzz` to `requirements.txt` for HarfBuzz complex text shaping (conjuncts, reph, kar placement).
  - Enabled `wordWrap="LTR"` and `shaping=True` on all ReportLab styles.
  - Converted newlines to `<br/>` in passages/stems.

### Phase 7: Multi-Key Rotation, Validation Toast & Teacher UX Fixes
- [x] **Task 7.1:** Support comma-separated `GEMINI_API_KEY` with automatic key rotation and Tesseract fallback on exhausted quota.
- [x] **Task 7.2:** Client-side pre-validation for MCQ options with top-right animated Toast and auto-scroll to the offending card.
- [x] **Task 7.3:** Highlight invalid candidate card with red border, inline warning, and one-click "Short প্রশ্নে রূপান্তর করুন" quick fix.
- [x] **Task 7.4:** Dynamic Subject (বিষয়) searchable combobox showing only previously used topics from the teacher's question bank.
- [x] **Task 7.5:** Removed auto-selection of past scans on initial page load and cleared selection on new file select to prevent misleading status alerts.

---

## 5. Execution Log
| Date | Task ID | Description | Result / Note |
| :--- | :--- | :--- | :--- |
| 2026-11-14 | Setup | Created master migration plan | Plan published in root directory |
| 2026-11-14 | Phase 1 | Config setup & live key check | Key validated with `gemini-3.5-flash` |
| 2026-11-14 | Phase 2 | Rewrite `ocr_service.py` | Integrated Gemini Vision with prompt rules & Tesseract fallback |
| 2026-11-14 | Phase 3 | Modernize `run_scan_dev.py` | Removed Docker container lifecycle; runs clean worker + uvicorn |
| 2026-11-14 | Phase 4 | Update `OcrTab.jsx` | Added MCQ answer selection, add/delete candidate buttons |
| 2026-11-14 | Phase 5 | Tests & Build | All 6 unit tests passed; frontend build succeeded |
| 2026-11-14 | Phase 6 | PDF Bengali Fonts & UI Polish | Bundled Kalpurush + uharfbuzz, 5s polling, KaTeX options preview |
| 2026-11-15 | Phase 7 | Multi-Key Rotation & UX Overhaul | Comma-separated keys, Toast notifications, Combobox, clean selection |
