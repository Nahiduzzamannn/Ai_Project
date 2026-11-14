r"""Start background OCR worker and FastAPI in one backend terminal.

Run from Backend/backend using the project virtual environment:
    ..\.venv\Scripts\python.exe run_scan_dev.py
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent.parent
    venv_py = root_dir / ".venv" / "Scripts" / "python.exe"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    worker = None
    try:
        # Start background OCR worker (powered by Gemini Vision API with Tesseract fallback)
        print("Starting Scan Questions OCR worker (Gemini Vision)...", flush=True)
        worker = subprocess.Popen([py_exec, "-m", "app.workers.ocr_worker"], cwd=backend_dir)
        print("OCR worker started. Starting FastAPI on http://127.0.0.1:8000", flush=True)
        return subprocess.run([py_exec, "-m", "uvicorn", "app.main:app",
                               "--reload", "--port", "8000"], cwd=backend_dir).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
            print("OCR worker stopped.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
