# Scan questions OCR upgrade: backend plan

Status: plan approved in conversation; implementation follows the plan commit.

## Scope and current behavior

Only `POST /api/v1/ocr/imports` and the Scan questions import flow change. The
document, chapter, RAG, question bank, and paper generation flows retain their
current processing paths. The current OCR import endpoint performs extraction in
the HTTP request, stores the uploaded source under the relative `uploaded_ocr/`
directory, and saves page text and candidate questions in `ocr_imports`.

The first release keeps that local source-file storage. A worker must run on the
same machine and have access to the same directory. A later Render deployment
must use a persistent disk mounted for that directory, or migrate source files
to shared object storage before putting the worker in a separate service.

## Desired pipeline

1. Accept a PDF or supported image (current 20 MB and 30-page limits). Create
   an `ocr_imports` row with `queued` status and persist the source file before
   returning the import ID. Do not perform OCR in the request.
2. A single OCR worker claims the oldest queued import from PostgreSQL. It
   renders **every** PDF page with PyMuPDF, regardless of embedded text, and
   reads images with Pillow. Embedded text is not a shortcut or trigger.
3. For each page, make one full-page `Spotting:` request to a local llama.cpp
   process running `hasanmdsadadul/PaddleOCR-VL-1.6-Bangla`. Request location
   tokens (`--special`). Parse line text and eight 0–1000 coordinate tokens,
   map coordinates to page pixels, and sort lines in reading order. Preserve
   Unicode text and raw model output for diagnosis where useful.
4. Honor image EXIF orientation and PDF page rotation. Scale the input to the
   model's documented spotting limit. Defer automatic deskew and denoising
   until representative scans show a measurable benefit; never apply either
   blindly.
5. If llama.cpp is unavailable, times out, or returns empty, malformed, or
   unusable spotting output, run existing Tesseract `ben+eng` for that page.
   Record which engine produced each page. A superficially valid OCR result
   still goes to teacher review; do not silently treat Tesseract as a quality
   judge. If both engines fail, retain a page error and continue other pages.
6. After each page, commit page text, boxes where available, progress counts,
   and error information to PostgreSQL. When all pages finish, run the existing
   question/option splitter on ordered text and mark the import `completed` or
   `failed` as appropriate. Preserve the existing candidate shape used by the
   review screen and `POST /ocr/imports/{id}/questions`.

## API and data contract

- `POST /api/v1/ocr/imports`: multipart `file` and `subject`; returns `202`
  with import ID, filename, subject, status, and progress. Remove `force_ocr`.
- `GET /api/v1/ocr/imports/{id}`: returns existing fields plus `status`,
  `processed_pages`, `total_pages`, and a short `error` when applicable. While
  processing, `pages` may contain completed pages and `candidates` may be empty.
- `GET /api/v1/ocr/imports`: include status and progress for previous scans.
- Existing `/file` and `/questions` routes remain. Reject accepting questions
  until the import is complete.
- Existing page JSON keeps `page`, `text`, and `method`; add optional `lines`
  with text and bounding box coordinates. Candidate JSON remains compatible.

Add a migration for job status, progress, timestamps/lease information, and
error fields on `ocr_imports`. Existing rows become `completed`, with progress
based on their saved pages. Keep the original `pages`/`candidates` JSON columns.

## Queue and process lifetime

PostgreSQL is the durable queue; no Redis or Celery is required for this stage.
One worker process claims one import at a time using a transaction and row
locking (for example `FOR UPDATE SKIP LOCKED`). A lease/heartbeat and startup
recovery must return stale `processing` jobs to `queued` after an interrupted
worker, without creating duplicate imports. The worker checkpoints completed
pages so a retry can resume from the first unfinished page. Put a finite
timeout on each llama.cpp request, then use the page-level Tesseract fallback.

llama.cpp's own request queue only controls inference slots. It is not the
durable PDF queue or source of progress. Start its server once, keep the model
loaded, and limit concurrency to one on CPU until benchmarks justify more.

For local development, run the API, one worker, and llama.cpp on the same
machine. An optional launcher can start these processes together. A Render
deployment can package them in one service while source files remain local;
separate services require shared storage. The web API must stay responsive
while OCR runs.

## Model runtime and environment

Pin the model revision and compatible llama.cpp build. Download weights to a
local model directory outside Git. Configure the local inference URL, model
paths, request timeout, worker polling interval, and upload directory via
environment variables. Keep the published BF16 GGUF and vision projector as
the initial correctness baseline. Quantized GGUF, RAM use, and Bangla accuracy
must be benchmarked before setting a low-memory deployment target. Docker is
packaging only; it does not change inference memory requirements. No paid OCR
API or Qwen model is part of this plan.

## Validation and deployment gate

- Compare Paddle one-pass OCR and current Tesseract on representative printed,
  scanned, English, Bangla, mixed-language, math-heavy, and MCQ pages. Measure
  character errors, missing question/options, reading order, box accuracy,
  seconds/page, and peak RAM. Review equations manually; this fine-tune does
  not establish reliable math transcription from its published evaluation.
- Verify a multi-page job can be viewed during processing, survives browser
  refresh, resumes after worker termination, and records page-level fallback.
- Verify all PDF pages use OCR even when embedded text exists. Verify existing
  import review and question acceptance still work; other tabs remain usable.
- Benchmark on the actual CPU hardware before selecting a Render/VPS size.
  The published BF16 checkpoint is not a credible 2 GB RAM deployment target.

## Expected backend files

- `app/api/v1/ocr.py`: short upload request, progress contract, acceptance gate.
- `app/services/ocr_service.py`: page rendering, one-pass OCR, parsing, fallback.
- New llama.cpp client and worker modules under `app/services/` or `app/workers/`.
- `app/models/ocr_import.py` and a new Alembic migration: durable job state.
- `app/core/config.py`, `.env.example`, `requirements.txt`, and runtime setup
  documentation: configuration and dependencies.
- Focused tests for spotting parsing, fallback, migration, and job lifecycle.

Model reference: https://huggingface.co/hasanmdsadadul/PaddleOCR-VL-1.6-Bangla
