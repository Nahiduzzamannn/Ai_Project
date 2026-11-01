"""Local Bangla/English OCR and conservative question segmentation."""

import io
import os
import re
import shutil
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30
LANGUAGES = "ben+eng"
LOCAL_TESSDATA = Path(__file__).resolve().parents[4] / ".runtime" / "tessdata"
if LOCAL_TESSDATA.exists():
    os.environ["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA)
if not shutil.which("tesseract") and os.name == "nt":
    windows_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_tesseract.exists():
        pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)
QUESTION_START = re.compile(r"^\s*(?:প্রশ্ন\s*)?(?:[0-9০-৯]{1,3}\s*[.)।:—-]|[০-৯]{1,3}\s*[.)।:—-])\s*(.+)")
OPTION_START = re.compile(r"^\s*(?:\(?[কখগঘঙচABCDabcd]\)?\s*[.)।:—-]|\([কখগঘঙচABCDabcd]\))\s*(.+)")


def _ocr_image(image: Image.Image) -> str:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if max(image.size) < 1800:
        scale = 1800 / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return pytesseract.image_to_string(image, lang=LANGUAGES, config="--psm 6", timeout=45).strip()


def extract_pages(filename: str, raw: bytes, subject: str = "", force_ocr: bool = False) -> list[dict]:
    extension = Path(filename).suffix.lower()
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("File must be between 1 byte and 20 MB")
    if extension == ".pdf":
        try:
            doc = fitz.open(stream=raw, filetype="pdf")
        except Exception as exc:
            raise ValueError("Invalid PDF") from exc
        try:
            if len(doc) > MAX_PAGES:
                raise ValueError(f"PDF has more than {MAX_PAGES} pages")
            pages = []
            for index, page in enumerate(doc):
                native = page.get_text("text", sort=True).strip()
                bangla_subject = any(word in subject.lower() for word in ("বাংলা", "গণিত", "বিজ্ঞান", "ইতিহাস", "সমাজ"))
                bangla_chars = sum("\u0980" <= char <= "\u09ff" for char in native)
                if len(native) >= 40 and not force_ocr and (not bangla_subject or bangla_chars >= 10):
                    pages.append({"page": index + 1, "text": native, "method": "embedded_text"})
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
                    with Image.open(io.BytesIO(pix.tobytes("png"))) as image:
                        text = _ocr_image(image)
                    pages.append({"page": index + 1, "text": text, "method": "ocr"})
            return pages
        finally:
            doc.close()
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        try:
            with Image.open(io.BytesIO(raw)) as image:
                return [{"page": 1, "text": _ocr_image(image), "method": "ocr"}]
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid image") from exc
    raise ValueError("Upload a PDF, PNG, JPG, WebP or TIFF file")


def split_questions(pages: list[dict]) -> list[dict]:
    """Keep ambiguous text intact for teacher review instead of guessing answers."""
    candidates = []
    for page in pages:
        blocks = []
        current = []
        for raw_line in page["text"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = QUESTION_START.match(line)
            if match:
                if current:
                    blocks.append(current)
                current = [match.group(1)]
            elif current:
                current.append(line)
        if current:
            blocks.append(current)
        if not blocks and page["text"].strip():
            blocks = [[line.strip() for line in page["text"].splitlines() if line.strip()]]
        for lines in blocks:
            stem = []
            options = []
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
                candidates.append({
                    "text": text,
                    "qtype": "mcq" if len(options) >= 2 else "short",
                    "options": options if len(options) >= 2 else None,
                    "page": page["page"],
                })
    return candidates
