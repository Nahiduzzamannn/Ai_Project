"""Manual one-page local llama.cpp OCR smoke test; requires the model server."""

import json
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.ocr_service import _llama_spotting


def main():
    image = Image.new("RGB", (1000, 520), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(r"C:\Windows\Fonts\Nirmala.ttf")
    font = ImageFont.truetype(str(font_path), 34) if font_path.exists() else ImageFont.load_default()
    for index, line in enumerate((
        "১. বাংলাদেশের রাজধানী কোথায়?",
        "ক) ঢাকা",
        "খ) চট্টগ্রাম",
        "২. What is 2 + 2?",
        "A) 3",
        "B) 4",
    )):
        draw.text((50, 35 + index * 75), line, fill="black", font=font)
    started = time.perf_counter()
    lines = _llama_spotting(image)
    print(json.dumps({"seconds": round(time.perf_counter() - started, 2), "lines": lines}, ensure_ascii=True))


if __name__ == "__main__":
    main()
