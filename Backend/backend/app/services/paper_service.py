"""
Question paper builder: takes questions from the bank, makes N shuffled sets
(Set A, Set B, ...) and renders them into one PDF with reportlab.

Each set has the same questions, but the question order inside every section
(and the MCQ option order, if enabled) is shuffled differently per set.
Shuffling is seeded so the same seed always produces the same paper.
"""

import io
import os
import random
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

SECTION_ORDER = ["mcq", "true_false", "short", "broad"]
SECTION_TITLES = {
    "mcq": "Multiple Choice Questions",
    "true_false": "True / False",
    "short": "Short Answer Questions",
    "broad": "Broad Questions",
}
OPTION_LABELS = "abcdefghij"


def _register_font() -> tuple[str, str]:
    """Use a Unicode font with HarfBuzz shaping so Bengali and English text render properly."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled_kalpurush = os.path.join(base_dir, "assets", "fonts", "Kalpurush.ttf")

    candidates = [
        # 1. Bundled Kalpurush font (works universally on Windows and Linux)
        (bundled_kalpurush, bundled_kalpurush),
        # 2. Windows Nirmala UI (TTC collection)
        (r"C:\Windows\Fonts\Nirmala.ttc", r"C:\Windows\Fonts\Nirmala.ttc"),
        # 3. Linux system fonts
        ("/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"),
        # 4. Fallback system fonts
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                if regular.lower().endswith(".ttc"):
                    pdfmetrics.registerFont(TTFont("PaperFont", regular, subfontIndex=0))
                    pdfmetrics.registerFont(TTFont("PaperFont-Bold", bold, subfontIndex=1 if regular == bold else 0))
                else:
                    pdfmetrics.registerFont(TTFont("PaperFont", regular))
                    pdfmetrics.registerFont(TTFont("PaperFont-Bold", bold))
                return "PaperFont", "PaperFont-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def set_label(i: int) -> str:
    return chr(ord("A") + i) if i < 26 else str(i + 1)


def build_sets(questions: list[dict], num_sets: int, shuffle_questions: bool,
               shuffle_options: bool, seed: int) -> list[dict]:
    """
    Returns [{"label": "A", "sections": [(qtype, [question, ...]), ...]}, ...].
    Each question dict gets "display_options" and "answer_label" for that set.
    """
    by_type: dict[str, list[dict]] = {t: [] for t in SECTION_ORDER}
    for q in questions:
        by_type.setdefault(q["qtype"], []).append(q)

    sets = []
    for i in range(num_sets):
        rng = random.Random(f"{seed}-{i}")
        sections = []
        for qtype in SECTION_ORDER:
            items = [dict(q) for q in by_type.get(qtype, [])]
            if not items:
                continue
            # Set A keeps the original order; later sets are shuffled
            if shuffle_questions and i > 0:
                rng.shuffle(items)
            for q in items:
                opts = list(q.get("options") or [])
                if qtype == "mcq" and shuffle_options and i > 0:
                    rng.shuffle(opts)
                q["display_options"] = opts
                q["answer_label"] = None
                if opts and q.get("answer"):
                    ans = q["answer"].strip().lower()
                    for idx, o in enumerate(opts):
                        if o.strip().lower() == ans:
                            q["answer_label"] = OPTION_LABELS[idx]
                            break
            sections.append((qtype, items))
        sets.append({"label": set_label(i), "sections": sections})
    return sets


def _fmt_marks(m: float) -> str:
    return str(int(m)) if float(m).is_integer() else f"{m:g}"


def render_pdf(
    sets: list[dict],
    title: str,
    subtitle: str | None = None,
    duration: str | None = None,
    instructions: str | None = None,
    include_answer_key: bool = True,
) -> bytes:
    font, font_bold = _register_font()
    styles = getSampleStyleSheet()
    s_title = ParagraphStyle("t", parent=styles["Title"], fontName=font_bold, fontSize=16, spaceAfter=2,
                             wordWrap="LTR", shaping=True)
    s_sub = ParagraphStyle("s", parent=styles["Normal"], fontName=font, fontSize=11, alignment=TA_CENTER,
                           wordWrap="LTR", shaping=True)
    s_section = ParagraphStyle("sec", parent=styles["Heading2"], fontName=font_bold, fontSize=12,
                               spaceBefore=10, spaceAfter=4, wordWrap="LTR", shaping=True)
    s_q = ParagraphStyle("q", parent=styles["Normal"], fontName=font, fontSize=10.5, leading=15,
                         wordWrap="LTR", shaping=True)
    s_opt = ParagraphStyle("o", parent=s_q, leftIndent=18, wordWrap="LTR", shaping=True)
    s_small = ParagraphStyle("sm", parent=s_q, fontSize=9.5, leading=13, wordWrap="LTR", shaping=True)

    s_meta_l = ParagraphStyle("ml", parent=s_small, fontName=font_bold, wordWrap="LTR", shaping=True)
    s_meta_c = ParagraphStyle("mc", parent=s_small, fontName=font_bold, alignment=TA_CENTER, wordWrap="LTR", shaping=True)
    s_meta_r = ParagraphStyle("mr", parent=s_small, fontName=font_bold, alignment=TA_RIGHT, wordWrap="LTR", shaping=True)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=title)
    story = []

    for set_idx, qset in enumerate(sets):
        if set_idx > 0:
            story.append(PageBreak())
        total_marks = sum(q["marks"] for _, items in qset["sections"] for q in items)
        story.append(Paragraph(escape(title).replace("\n", "<br/>"), s_title))
        if subtitle:
            story.append(Paragraph(escape(subtitle).replace("\n", "<br/>"), s_sub))
        story.append(Spacer(1, 4))

        meta = Table(
            [[Paragraph(f"Set: {qset['label']}", s_meta_l),
              Paragraph(f"Time: {duration}" if duration else "", s_meta_c),
              Paragraph(f"Full marks: {_fmt_marks(total_marks)}", s_meta_r)]],
            colWidths=[doc.width / 3] * 3,
        )
        meta.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(meta)
        if instructions:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<i>{escape(instructions).replace(chr(10), '<br/>')}</i>", s_small))

        number = 1
        for qtype, items in qset["sections"]:
            section_marks = sum(q["marks"] for q in items)
            story.append(Paragraph(
                f"{SECTION_TITLES.get(qtype, qtype.title())} "
                f"<font size=9>({len(items)} questions, {_fmt_marks(section_marks)} marks)</font>",
                s_section,
            ))
            for q in items:
                formatted_text = escape(q["text"]).replace("\n", "<br/>")
                block = [Paragraph(
                    f"<b>{number}.</b> {formatted_text} "
                    f"<font size=9 color='#555555'>[{_fmt_marks(q['marks'])}]</font>",
                    s_q,
                )]
                if q["display_options"] and qtype == "mcq":
                    for idx, opt in enumerate(q["display_options"]):
                        formatted_opt = escape(opt).replace("\n", "<br/>")
                        block.append(Paragraph(f"({OPTION_LABELS[idx]}) {formatted_opt}", s_opt))
                elif qtype == "true_false":
                    block.append(Paragraph("(True / False)", s_opt))
                block.append(Spacer(1, 6))
                story.append(KeepTogether(block))
                number += 1

    if include_answer_key:
        for qset in sets:
            story.append(PageBreak())
            story.append(Paragraph(escape(f"Answer Key — Set {qset['label']}").replace("\n", "<br/>"), s_title))
            story.append(Paragraph(escape(title).replace("\n", "<br/>"), s_sub))
            story.append(Spacer(1, 8))
            number = 1
            for qtype, items in qset["sections"]:
                story.append(Paragraph(SECTION_TITLES.get(qtype, qtype), s_section))
                for q in items:
                    if q.get("answer_label"):
                        ans = f"({q['answer_label']}) {q['answer']}"
                    else:
                        ans = q.get("answer") or "—"
                    formatted_ans = escape(ans).replace("\n", "<br/>")
                    story.append(Paragraph(f"<b>{number}.</b> {formatted_ans}", s_small))
                    story.append(Spacer(1, 3))
                    number += 1

    doc.build(story)
    return buf.getvalue()
