# Scan questions OCR upgrade: frontend plan

Status: plan approved in conversation; implementation follows the plan commit.

## Scope

Only the Scan questions page (`src/components/OcrTab.jsx`) and its OCR API
functions (`src/api.js`) change. Existing question review, editing, preview,
and save-to-bank behavior remain. Other tabs keep their current behavior.

## User flow

1. The teacher selects an image or PDF and a subject, then clicks **OCR**.
2. The upload returns quickly with an import ID and `queued` status. The page
   shows that the file was accepted and displays its current status.
3. While an import is `queued` or `processing`, call
   `GET /api/v1/ocr/imports/{id}` every **2 seconds**. Show completed pages out
   of total pages. Do not submit a second poll while the previous one is still
   pending; stop polling when the component unmounts or another import opens.
4. On `completed`, stop polling and show the existing candidate review and
   full extracted text. On `failed`, show the saved error and a clear way to
   upload again. Page-level Tesseract fallback should be visible through the
   page method, without interrupting review.
5. A refresh or reopening a previous import resumes status display and polling.
   The server's import record, rather than browser memory, is the source of
   truth. The original PDF/image preview still uses the existing `/file` URL.

Remove the `force_ocr` checkbox and form field. Every PDF page is OCR'd by the
backend; the user no longer needs to choose between embedded text and OCR.

## API contract expected from the backend

- `POST /ocr/imports` returns HTTP 202 with at least `id`, `status`,
  `processed_pages`, and `total_pages` (the total may be filled shortly after
  upload if page counting is deferred).
- `GET /ocr/imports/{id}` adds those progress fields and an optional `error`
  while preserving `pages`, `candidates`, `filename`, and `subject`.
- Status values: `queued`, `processing`, `completed`, `failed`.
- `GET /ocr/imports` includes statuses for the previous-scan buttons.

## Validation

- One image and a multi-page PDF show live progress without freezing the page.
- Polling occurs about every 2 seconds only while a job is active, including
  after refresh or opening an older active import.
- Completed imports keep the existing edit, option, source preview, and save
  experience. Failed imports stop polling and show a useful error.
- Other tabs continue to load and work during OCR processing.

## Expected frontend files

- `src/api.js`: upload contract and status requests.
- `src/components/OcrTab.jsx`: remove `force_ocr`, show progress, and poll.
- Existing UI components may be reused; avoid broad changes to other tabs.
