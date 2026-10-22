import re
import fitz  # PyMuPDF
from typing import List, Tuple


def extract_pdf_text_by_page(pdf_path: str) -> List[Tuple[int, str]]:
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(len(doc)):
        text = doc.load_page(i).get_text("text") or ""
        pages.append((i + 1, text))
    doc.close()
    return pages


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# Lines like "Chapter 3", "CHAPTER IV: Motion", "Unit 2 - Cells", "Lesson 5"
HEADING_RE = re.compile(
    r"^\s*(chapter|unit|lesson|part|module)\s+([0-9]+|[ivxlcdm]+)\b[\s.:\-–—]*(.*)$",
    re.IGNORECASE,
)


def _heading_on_page(text: str) -> str | None:
    """Return a chapter heading if one appears in the first lines of a page."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:8]
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(line) < 120:
            title = line
            # Heading often sits on its own line with the name on the next line
            if not m.group(3).strip() and i + 1 < len(lines) and len(lines[i + 1]) < 100:
                title = f"{line}: {lines[i + 1]}"
            return title
    return None


def detect_chapters(pdf_path: str, pages: List[Tuple[int, str]]) -> List[dict]:
    """
    Split a PDF into chapters. Returns dicts with title, start_page, end_page, source.

    1. Use the PDF's bookmarks/table of contents (most reliable).
    2. Otherwise look for "Chapter N" style headings at the top of pages.
    3. Otherwise treat the whole document as one chapter.
    """
    total = len(pages)
    if total == 0:
        return []

    starts: list[tuple[str, int]] = []
    source = "toc"

    doc = fitz.open(pdf_path)
    toc = doc.get_toc(simple=True)  # [[level, title, page], ...]
    doc.close()

    if toc:
        # Use the top level; if it has only one entry (e.g. book title), use level 2
        for level in (1, 2):
            entries = [(t.strip(), p) for lvl, t, p in toc if lvl == level and t.strip() and p >= 1]
            if len(entries) >= 2:
                starts = entries
                break

    if not starts:
        source = "heading"
        for page_number, text in pages:
            title = _heading_on_page(text)
            if title:
                starts.append((title, page_number))

    if not starts:
        return [{"title": "Full document", "start_page": 1, "end_page": total, "source": "full"}]

    # Remove duplicates by start page, keep order
    starts.sort(key=lambda x: x[1])
    deduped: list[tuple[str, int]] = []
    for title, page in starts:
        if deduped and deduped[-1][1] == page:
            continue
        deduped.append((title, min(page, total)))

    chapters = []
    for i, (title, start) in enumerate(deduped):
        if i + 1 < len(deduped):
            end = max(start, deduped[i + 1][1] - 1)
        else:
            end = total
        chapters.append({"title": title[:500], "start_page": start, "end_page": end, "source": source})
    return chapters


def text_for_pages(pages: List[Tuple[int, str]], start_page: int, end_page: int) -> str:
    return "\n".join(text for num, text in pages if start_page <= num <= end_page).strip()
