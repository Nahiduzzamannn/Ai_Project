"""Page rendering, Gemini Vision extraction, Tesseract fallback, and question splitting."""

import base64
import io
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import fitz
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

log = logging.getLogger(__name__)

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

QUESTION_START = re.compile(r"^\s*(?:(?:প্রশ্ন|Q|Question)\s*)?(?:[0-9০-৯]{1,3}|[ivxlcdm]{1,4})\s*[.)।:—-]\s*.+", re.IGNORECASE)
OPTION_START = re.compile(r"^\s*(?:\(?[কখগঘঙচABCDabcd]\)?\s*[.)।:—-]|\([কখগঘঙচABCDabcd]\))\s*(.+)")
LOCATIONS = re.compile(r"<\|LOC_(\d{1,4})\|>")
LOCATION_GROUP = re.compile(r"(?:<\|LOC_\d{1,4}\|>){8}")
OTHER_SPECIAL = re.compile(r"<\|(?:im_end|im_start|endoftext|assistant|eot_id)\|>")

GEMINI_SYSTEM_PROMPT = """You are an expert exam question extractor and OCR assistant specializing in Bangladeshi curriculum (NCTB / HSC / SSC) and English examination papers.

Analyze the provided image of an exam page and extract all questions into a clean, structured JSON format with this exact schema:
{
  "full_text": "The entire verbatim text of the page in clean Bengali and English, retaining line breaks.",
  "questions": [
    {
      "text": "The question stem. Strip any leading question number (e.g. remove '১.', '1.', 'প্রশ্ন ১:'). If there are multi-statement conditions (like i, ii, iii) or a shared passage/context ('উদ্দীপক'), include them fully in this text field.",
      "qtype": "mcq | short | broad | true_false",
      "options": ["ক) অপশন ১", "খ) অপশন ২", "গ) অপশন ৩", "ঘ) অপশন ৪"],
      "answer": "Correct answer if explicitly marked or clear, else null",
      "marks": 1.0,
      "difficulty": "medium"
    }
  ]
}

CRITICAL RULES:
1. Strip leading question numbers from question text (e.g. '১. বায়ুমণ্ডলের প্রধান উপাদান কী?' becomes 'বায়ুমণ্ডলের প্রধান উপাদান কী?').
2. Multi-Statement MCQs (বহুপদী সমাপ্তিসূচক প্রশ্ন):
   - Example:
     উদ্ভিদের বৃদ্ধিতে সাহায্য করে—
     i. অক্সিন
     ii. জিব্বেরেলিন
     iii. অ্যাবসিসিক অ্যাসিড
     নিচের কোনটি সঠিক?
   - Put all the statements (i, ii, iii) and 'নিচের কোনটি সঠিক?' inside the 'text' field.
   - Put ONLY the final answer options (ক, খ, গ, ঘ) in the 'options' array.
3. Stem / Passage Based Questions (উদ্দীপক ভিত্তিক প্রশ্ন):
   - If a shared passage/context ('উদ্দীপক') applies to multiple questions, prepend the relevant passage context to each question's 'text' so every question is self-contained.
4. Creative / Subjective Questions (সৃজনশীল প্রশ্ন - CQ):
   - (ক) জ্ঞানমূলক & (খ) অনুধাবনমূলক: set qtype='short'.
   - (গ) প্রয়োগমূলক & (ঘ) উচ্চতর দক্ষতামূলক: set qtype='broad'.
5. Math and Science Formulas:
   - Format any formulas, superscripts, fractions, chemical reactions in LaTeX KaTeX notation (e.g. '$x^2 + y^2 = z^2$', '$\\frac{a}{b}$', '$H_2O$'). In JSON strings, use valid escaping for backslashes (e.g. '\\\\sqrt', '\\\\frac').
6. For non-MCQ questions (short, broad), 'options' MUST be null.
7. Return ONLY valid JSON, with no markdown code fences."""


def robust_json_loads(raw: str) -> dict:
    """Robustly parse LLM JSON responses, repairing LaTeX backslashes, trailing commas, and markdown fences."""
    if not raw or not isinstance(raw, str):
        return {}

    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if match:
            text = match.group(1).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text).strip()

    # 1. Direct parse attempt
    try:
        return json.loads(text, strict=False)
    except Exception:
        pass

    # 2. Repair unescaped LaTeX backslashes in JSON strings:
    # Match any single backslash NOT preceded by another backslash that is:
    # - followed by [bfnrtu] and a letter (e.g. \frac, \times, \theta, \beta, \rho, \nu, \uparrow)
    # - followed by any ASCII letter other than [bfnrtu] (e.g. \sqrt, \alpha, \cdot, \pm, \approx, etc.)
    # - followed by non-escape characters / symbols (e.g. \{, \}, \$, \_, \%, \!)
    pattern = re.compile(r'(?<!\\)\\(?=(?:[bfnrtu][a-zA-Z]|[ac-eg-mo-qsv-zAC-EG-MO-QSV-Z]|[^"\\/bfnrtu\s]))')
    repaired = pattern.sub(r'\\\\', text)

    try:
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # 3. Strip trailing commas before closing } or ]
    repaired_no_commas = re.sub(r',\s*([\]}])', r'\1', repaired)
    try:
        return json.loads(repaired_no_commas, strict=False)
    except Exception:
        pass

    # 4. Aggressive fallback: escape any unescaped backslash and strip trailing commas
    aggressive = re.sub(r'(?<!\\)\\(?![/\\"])', r'\\\\', text)
    aggressive = re.sub(r',\s*([\]}])', r'\1', aggressive)
    return json.loads(aggressive, strict=False)


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


def _gemini_vision_extract(image: Image.Image, api_key: str | None = None) -> dict:
    key_to_use = api_key or (settings.gemini_api_keys[0] if settings.gemini_api_keys else None)
    if not key_to_use:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    # Resize if extremely large to save bandwidth
    if max(image.size) > 2400:
        scale = 2400 / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

    model_clean = (settings.GEMINI_MODEL or "gemini-3.5-flash").removeprefix("models/")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_clean}:generateContent?key={key_to_use}"
    payload = {
        "contents": [{
            "parts": [
                {"text": GEMINI_SYSTEM_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    for attempt in range(2):
        try:
            with urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidate = data["candidates"][0]
                part = candidate["content"]["parts"][0]
                raw_json = part["text"].strip()
                return robust_json_loads(raw_json)
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
            is_transient = "503" in str(exc) or "timeout" in str(exc).lower()
            if attempt == 0 and is_transient:
                log.info("Gemini transient issue (%s), retrying in 2s...", exc)
                time.sleep(2)
                continue
            raise RuntimeError(f"Gemini Vision API error: {exc}") from exc


def _tesseract_image(image: Image.Image) -> str:
    if max(image.size) < 1800:
        scale = 1800 / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return pytesseract.image_to_string(image, lang="ben+eng", config="--psm 6", timeout=45).strip()


def recognize_page(number: int, image: Image.Image, total_pages: int = 1) -> dict:
    """Extract page using Gemini Vision, with local Tesseract as fallback."""
    gemini_error_msg = ""
    page_label = f"Page {number}/{total_pages}" if total_pages > 1 else f"Image (Page {number})"

    api_keys = settings.gemini_api_keys
    # 1. Primary: Gemini Vision API (try all configured keys in sequence)
    if api_keys:
        for idx, key in enumerate(api_keys, 1):
            key_masked = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"
            log.info("[%s] Sending to Gemini Vision API (%s) using Key %d/%d (%s)...",
                     page_label, settings.GEMINI_MODEL, idx, len(api_keys), key_masked)
            t0 = time.time()
            try:
                data = _gemini_vision_extract(image, api_key=key)
                elapsed = time.time() - t0
                questions = data.get("questions") or []
                cleaned_q = []
                for q in questions:
                    if isinstance(q, dict) and q.get("text"):
                        raw_opts = q.get("options")
                        valid_opts = [str(o).strip() for o in raw_opts if str(o).strip()] if raw_opts and isinstance(raw_opts, list) else None
                        raw_qtype = q.get("qtype") if q.get("qtype") in ("mcq", "short", "broad", "true_false") else "short"
                        # Degrade to short if Gemini classified as MCQ but missed/returned fewer than 2 options
                        if raw_qtype == "mcq" and (not valid_opts or len(valid_opts) < 2):
                            raw_qtype = "short"
                            valid_opts = None

                        cleaned_q.append({
                            "text": str(q["text"]).strip(),
                            "qtype": raw_qtype,
                            "options": valid_opts,
                            "answer": str(q["answer"]).strip() if q.get("answer") else None,
                            "marks": float(q.get("marks") or (1.0 if raw_qtype == "mcq" else 2.0)),
                            "difficulty": str(q.get("difficulty") or "medium"),
                            "page": number,
                        })
                log.info("[%s] ✓ Gemini Vision completed in %.2fs with Key %d/%d (Extracted %d questions)",
                         page_label, elapsed, idx, len(api_keys), len(cleaned_q))
                return {
                    "page": number,
                    "text": str(data.get("full_text") or "").strip(),
                    "method": "gemini_vision",
                    "questions": cleaned_q,
                    "lines": [],
                }
            except Exception as gemini_err:
                elapsed = time.time() - t0
                gemini_error_msg = str(gemini_err)[:300]
                log.warning("[%s] ⚠ Gemini Vision Key %d/%d failed after %.2fs: %s",
                            page_label, idx, len(api_keys), elapsed, gemini_error_msg)
                if idx < len(api_keys):
                    if "429" in gemini_error_msg or "resource_exhausted" in gemini_error_msg.lower():
                        log.info("[%s] Rate limit reached on Key %d/%d. Waiting 3s before switching...", page_label, idx, len(api_keys))
                        time.sleep(3.0)
                    log.info("[%s] Rotating to next Gemini API key...", page_label)
        log.warning("[%s] ⚠ All configured Gemini API keys failed or exhausted. Falling back to Tesseract OCR...", page_label)
    else:
        gemini_error_msg = "GEMINI_API_KEY is not set"
        log.warning("[%s] ⚠ GEMINI_API_KEY is not set. Switching to offline Tesseract...", page_label)

    # 2. Fallback to Tesseract OCR (ben+eng)
    log.info("[%s] Running fallback Tesseract OCR (ben+eng)...", page_label)
    t0 = time.time()
    try:
        text = _tesseract_image(image)
        elapsed = time.time() - t0
        log.info("[%s] ✓ Tesseract OCR completed in %.2fs (%d characters)", page_label, elapsed, len(text))
        return {
            "page": number,
            "text": text,
            "method": "tesseract",
            "questions": [],
            "lines": [],
            "error": gemini_error_msg,
        }
    except Exception as tesseract_error:
        elapsed = time.time() - t0
        log.error("[%s] ✗ Both Gemini Vision and Tesseract failed after %.2fs: %s", page_label, elapsed, tesseract_error)
        return {
            "page": number,
            "text": "",
            "method": "failed",
            "questions": [],
            "lines": [],
            "error": f"Gemini: {gemini_error_msg}; Tesseract: {tesseract_error}"[:500],
        }


def split_questions(pages: list[dict]) -> list[dict]:
    """Collect Gemini-extracted questions, or fallback to regex splitting for Tesseract pages."""
    candidates = []
    tesseract_pages = []

    for page in pages:
        page_num = page.get("page", 1)
        page_questions = page.get("questions") or []
        if page_questions:
            for q in page_questions:
                q_copy = dict(q)
                q_copy["page"] = page_num
                candidates.append(q_copy)
        else:
            tesseract_pages.append(page)

    # If any page used Tesseract fallback without structured questions, use regex parser
    if tesseract_pages:
        for page in tesseract_pages:
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
                clean_text = re.sub(r"^\s*(?:(?:প্রশ্ন|Q|Question)\s*)?(?:[0-9০-৯]{1,3}|[ivxlcdm]{1,4})\s*[.)।:—-]\s*", "", text, flags=re.IGNORECASE).strip() or text
                if clean_text:
                    candidates.append({
                        "text": clean_text,
                        "qtype": "mcq" if len(options) >= 2 else "short",
                        "options": options if len(options) >= 2 else None,
                        "answer": None,
                        "marks": 1.0 if len(options) >= 2 else 2.0,
                        "difficulty": "medium",
                        "page": page["page"],
                    })

    return candidates
