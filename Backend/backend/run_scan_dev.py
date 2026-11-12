"""Start local llama.cpp Docker, OCR worker, and FastAPI in one backend terminal.

Run from Backend/backend using the project virtual environment:
    ..\.venv\Scripts\python.exe run_scan_dev.py
"""

import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / ".runtime" / "models" / "paddleocr-vl-1.6-bangla" / "gguf"
CONTAINER = "ai-project-scan-ocr-dev"
IMAGE = "ghcr.io/ggml-org/llama.cpp@sha256:086942d6ac097c894d9d5bbaf8085c53af85e113fbb9d6d61b3748863c86aa5f"


def wait_for_model(seconds: int = 180) -> None:
    for elapsed in range(seconds):
        try:
            with urlopen("http://127.0.0.1:8081/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        if elapsed % 10 == 0:
            print("Waiting for local Paddle OCR model to load...", flush=True)
        time.sleep(1)
    raise RuntimeError("llama.cpp did not become ready; inspect its Docker logs")


def main() -> int:
    model = MODEL_DIR / "PaddleOCR-VL-1.6-Bangla.gguf"
    projector = MODEL_DIR / "mmproj-spotting.gguf"
    if not model.is_file() or not projector.is_file():
        raise SystemExit(f"Download the Bangla model and vision projector into {MODEL_DIR} first")
    command = [
        "docker", "run", "--detach", "--rm", "--name", CONTAINER,
        "--publish", "127.0.0.1:8081:8081",
        "--mount", f"type=bind,source={MODEL_DIR},target=/models,readonly",
        IMAGE,
        "-m", "/models/PaddleOCR-VL-1.6-Bangla.gguf",
        "--mmproj", "/models/mmproj-spotting.gguf",
        "--host", "0.0.0.0", "--port", "8081", "--alias", "paddleocr-vl-1.6-bangla",
        "--temp", "0", "--special", "--parallel", "1", "--ctx-size", "8192",
    ]
    subprocess.run(command, check=True)
    worker = None
    try:
        wait_for_model()
        worker = subprocess.Popen([sys.executable, "-m", "app.workers.ocr_worker"], cwd=Path(__file__).parent)
        print("OCR worker ready. Starting FastAPI on http://127.0.0.1:8000", flush=True)
        return subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app",
                               "--reload", "--port", "8000"], cwd=Path(__file__).parent).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
        subprocess.run(["docker", "stop", CONTAINER], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
