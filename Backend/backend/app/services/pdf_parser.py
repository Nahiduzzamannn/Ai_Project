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
        start = end - overlap
        if start < 0:
            start = 0
    return chunks