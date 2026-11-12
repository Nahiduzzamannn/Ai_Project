"""Page rendering, Bangla spotting, Tesseract fallback, and question splitting."""

import base64
import io
import json
import os
import re
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import fitz
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30
MAX_SPOTTING_PIXELS = 1_605_632
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
LOCAL_TESSDATA = Path(__file__).resolve().parents[4] / ".runtime" / "tessdata"
if LOCAL_TESSDATA.exists():
    os.environ["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA)
if not shutil.which("tesseract") and os.name == "nt":
    windows_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_tesseract.exists():
        pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)

QUESTION_START = re.compile(r"^\s*(?:প্রশ্ন\s*)?[0-9০-৯]{1,3}\s*[.)।:—-]\s*.+")
OPTION_START = re.compile(r"^\s*(?:\(?[কখগঘঙচABCDabcd]\)?\s*[.)।:—-]|\([কখগঘঙচABCDabcd]\))\s*(.+)")
LOCATIONS = re.compile(r"<\|LOC_(\d{1,4})\|>")
LOCATION_GROUP = re.compile(r"(?:<\|LOC_\d{1,4}\|>){8}")
OTHER_SPECIAL = re.compile(r"<\|(?:im_end|im_start|endoftext|assistant|eot_id)\|>")


def validate_upload(filename: str, raw: bytes) -> int:
    """Validate a queued upload and return the number of pages."""
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("File must be between 1 byte and 20 MB")
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        try:
            with fitz.open(stream=raw, filetype="pdf") as document:
                count = len(document)
                if document.needs_pass or count == 0:
                    raise ValueError("PDF must have readable pages and no password")
                if count > MAX_PAGES:
                    raise ValueError(f"PDF has more than {MAX_PAGES} pages")
                return count
        except (fitz.FileDataError, fitz.EmptyFileError) as exc:
            raise ValueError("Invalid PDF") from exc
    if extension in IMAGE_EXTENSIONS:
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            return 1
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid image") from exc
    raise ValueError("Upload a PDF, PNG, JPG, WebP or TIFF file")


def iter_page_images(path: Path):
    """Render every PDF page, including pages with embedded text."""
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as document:
            for number, page in enumerate(document, 1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                    yield number, image.convert("RGB")
    else:
        with Image.open(path) as image:
            yield 1, ImageOps.exif_transpose(image).convert("RGB")


def _spotting_image(image: Image.Image) -> Image.Image:
    if image.width * image.height <= MAX_SPOTTING_PIXELS:
        return image
    scale = (MAX_SPOTTING_PIXELS / (image.width * image.height)) ** 0.5
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def parse_spotting(raw: str, width: int, height: int) -> list[dict]:
    """Parse line text and four 0–1000-space corners from a Spotting response."""
    lines = []
    previous_end = 0
    for match in LOCATION_GROUP.finditer(raw):
        text = OTHER_SPECIAL.sub("", raw[previous_end:match.start()]).strip()
        previous_end = match.end()
        values = [int(value) for value in LOCATIONS.findall(match.group())]
        if not text or len(values) != 8 or any(value > 1000 for value in values):
            continue
        xs, ys = values[::2], values[1::2]
        box = [round(min(xs) * width / 1000), round(min(ys) * height / 1000),
               round(max(xs) * width / 1000), round(max(ys) * height / 1000)]
        if box[2] > box[0] and box[3] > box[1]:
            lines.append({"text": text, "bbox": box})
    return lines  # Retain model order; teacher can review reading order.


def _llama_spotting(image: Image.Image) -> list[dict]:
    original_size = image.size
    image = _spotting_image(image)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    payload = {
        "model": settings.OCR_LLAMA_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
            {"type": "text", "text": "Spotting:"},
        ]}],
        "temperature": 0,
        "max_tokens": 4096,
        "stream": False,
    }
    request = Request(settings.OCR_LLAMA_URL, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=settings.OCR_LLAMA_TIMEOUT) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Local Paddle OCR unavailable: {exc}") from exc
    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("Paddle OCR response was cut off")
        content = choice["message"]["content"]
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        lines = parse_spotting(content, *original_size)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("Invalid Paddle OCR response") from exc
    if not lines:
        raise RuntimeError("Paddle OCR returned no readable lines with boxes")
    return lines


def _tesseract_image(image: Image.Image) -> str:
    if max(image.size) < 1800:
        scale = 1800 / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return pytesseract.image_to_string(image, lang="ben+eng", config="--psm 6", timeout=45).strip()


def recognize_page(number: int, image: Image.Image) -> dict:
    """One Bangla spotting call, with Tesseract only if it fails."""
    try:
        lines = _llama_spotting(image)
        return {"page": number, "text": "\n".join(line["text"] for line in lines),
                "method": "paddle_bangla", "lines": lines}
    except Exception as paddle_error:
        try:
            text = _tesseract_image(image)
            return {"page": number, "text": text, "method": "tesseract", "lines": [],
                    "error": str(paddle_error)[:300]}
        except Exception as tesseract_error:
            return {"page": number, "text": "", "method": "failed", "lines": [],
                    "error": f"Paddle: {paddle_error}; Tesseract: {tesseract_error}"[:500]}


def split_questions(pages: list[dict]) -> list[dict]:
    """Keep ambiguous text intact for teacher review instead of guessing answers."""
    candidates = []
    for page in pages:
        blocks, current = [], []
        for raw_line in page["text"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if QUESTION_START.match(line):
                if current:
                    blocks.append(current)
                current = [line]
            elif current:
                current.append(line)
        if current:
            blocks.append(current)
        if not blocks and page["text"].strip():
            blocks = [[line.strip() for line in page["text"].splitlines() if line.strip()]]
        for lines in blocks:
            stem, options = [], []
            for line in lines:
                option = OPTION_START.match(line)
                if option and stem:
                    options.append(option.group(1))
                elif options:
                    options[-1] += " " + line
                else:
                    stem.append(line)
            text = "\n".join(stem).strip()
            if text:
                candidates.append({"text": text, "qtype": "mcq" if len(options) >= 2 else "short",
                                   "options": options if len(options) >= 2 else None,
                                   "page": page["page"]})
    return candidates
