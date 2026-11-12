# Run the Scan questions OCR backend locally

This affects the **Scan questions** page only. It uses a local Bangla
PaddleOCR-VL-1.6 fine-tune through llama.cpp, with Tesseract `ben+eng` as a
page-level fallback. Every PDF page is rendered and OCR'd. The uploaded source
file remains in `uploaded_ocr/`, and PostgreSQL stores job progress and results.
No paid OCR API is used.

## One-time setup on Windows

1. Make sure PostgreSQL is running and `Backend/backend/.env` has the working
   `DATABASE_URL`. Install Tesseract for fallback. On this development machine,
   Tesseract 5.5.3 was installed with `winget install --id
   tesseract-ocr.tesseract --exact` and the `ben` and `eng` files from the
   official `tessdata_fast` repository were placed in the ignored
   `.runtime/tessdata/` directory. The backend detects that directory and
   sets `TESSDATA_PREFIX` automatically.
   If you are using the existing local PostgreSQL container, start it with
   `docker start ai-project-db` before running the backend.
2. Install Docker Desktop. The development launcher uses the official
   llama.cpp CPU server image; the image is pulled automatically on first run.
3. From the repository root, download the two model files into the ignored
   `.runtime` directory. The exact model revision used for development is
   `1429249a4aff1455812af052e58701cf2462684c`:

   ```powershell
   Backend\.venv\Scripts\hf.exe download hasanmdsadadul/PaddleOCR-VL-1.6-Bangla gguf/PaddleOCR-VL-1.6-Bangla.gguf gguf/mmproj-spotting.gguf --revision 1429249a4aff1455812af052e58701cf2462684c --local-dir .runtime/models/paddleocr-vl-1.6-bangla
   ```

   These files occupy about 1.8 GB on disk. They are deliberately excluded
   from Git. The development launcher pins the llama.cpp CPU image by digest.
4. Apply the migration:

   ```powershell
   cd Backend\backend
   ..\.venv\Scripts\python.exe -m alembic upgrade head
   ```

## Run with the frontend in two terminals

Backend terminal, from `Backend/backend`:

```powershell
..\.venv\Scripts\python.exe run_scan_dev.py
```

The launcher starts llama.cpp in a local Docker container, waits for its model
to load, starts one PostgreSQL-backed OCR worker, and runs FastAPI on port 8000.
It stops the worker and its Docker container when the backend command exits.
The llama.cpp port is published only on `127.0.0.1:8081`.

Frontend terminal, from `Frontend`:

```powershell
npm.cmd run dev
```

Open `http://localhost:5173`. The Scan questions page checks an active job
every two seconds. Jobs are processed one at a time and their status is saved
in PostgreSQL. A browser refresh does not cancel a job. If the worker process
is interrupted, its claim becomes eligible for recovery after the stale-job
interval; already checkpointed pages are retained.

For a manual smoke check while llama.cpp is running:

```powershell
..\.venv\Scripts\python.exe smoke_scan_ocr.py
```

The development test on a 1000 x 520 synthetic Bangla/English MCQ image took
about 70 seconds on this machine and returned six text lines with boxes. This
is one observation, not a throughput guarantee. Full PDF pages and 30-page
uploads can take much longer on CPU.

## Optional configuration

Defaults are in `.env.example`:

| Variable | Default | Purpose |
|---|---|---|
| `OCR_UPLOAD_DIR` | `uploaded_ocr` | Source-file directory shared by API and worker |
| `OCR_LLAMA_URL` | `http://127.0.0.1:8081/v1/chat/completions` | Local inference endpoint |
| `OCR_LLAMA_MODEL` | `paddleocr-vl-1.6-bangla` | llama.cpp model alias |
| `OCR_LLAMA_TIMEOUT` | `300` | Seconds before a page falls back to Tesseract |
| `OCR_WORKER_POLL_SECONDS` | `2` | Delay between checks for queued jobs |
| `OCR_STALE_SECONDS` | `900` | Delay before a dead worker's job can be reclaimed |

Keep `OCR_STALE_SECONDS` greater than the longest single page's Paddle timeout
plus Tesseract fallback time. The worker can also be run alone with
`..\.venv\Scripts\python.exe -m app.workers.ocr_worker`.

## Later deployment

The local launcher is for development; Render does not run Docker inside a
Docker service. A Render CPU deployment needs a container image containing the
backend, llama.cpp binary, Tesseract, and a worker process, or services with a
shared source-file store. While uploads stay on the local filesystem, the API
and worker must share the same mounted persistent directory. Render's 512 MB
free tier cannot run this BF16 model. Benchmark the chosen CPU and memory plan
before deployment. The application also needs authentication before public
internet access, as the root README notes.

The fine-tuned model's weights are labeled CC BY-SA 4.0. Review that license
for a client deployment: https://huggingface.co/hasanmdsadadul/PaddleOCR-VL-1.6-Bangla
