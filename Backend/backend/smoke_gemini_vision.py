"""Smoke check for Gemini Vision extraction with Tesseract fallback."""

import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.ocr_service import recognize_page, split_questions

img_path = Path(__file__).resolve().parents[2] / ".runtime" / "bangla_sample_page1.png"

if not img_path.exists():
    raise SystemExit(f"Sample image not found at {img_path}")

print("Testing recognize_page with Gemini Vision...")
img = Image.open(img_path)
page_result = recognize_page(1, img, total_pages=1)

print("\n--- OCR / Vision Result ---")
print("Method used:", page_result["method"])
print("Error (if any):", page_result.get("error"))
print("Extracted questions count:", len(page_result.get("questions", [])))

candidates = split_questions([page_result])
print(f"Total candidates ready for review: {len(candidates)}")
for i, c in enumerate(candidates[:3], 1):
    print(f"\nCandidate {i} [{c['qtype']}]:")
    print("Stem:", c["text"][:100], "..." if len(c["text"]) > 100 else "")
    if c.get("options"):
        print("Options:", c["options"])
