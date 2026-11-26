#!/usr/bin/env python3
"""Render a project Markdown document to an A4 PDF (documentation tool, not pipeline).

Supports the subset our docs use: headings, paragraphs, bullet / numbered lists, pipe
tables, fenced code, inline ``**bold**``, ``*italic*``, ```code``` and links, and simple
Mermaid ``flowchart LR/TD`` chains (``A[Label] --> B[Label]``), drawn as box diagrams.

Usage::

    python tools/md2pdf.py docs/stages/STAGE_0_recon.md docs/stages/STAGE_0_recon.pdf

Requires ``requirements-docs.txt`` (reportlab, markdown-it-py).
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (ListFlowable, ListItem, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
NAVY, TEAL, GREY = colors.HexColor("#0F1B2D"), colors.HexColor("#0E9F8E"), colors.HexColor("#5B6573")


def _fonts() -> tuple[str, str, str]:
    try:
        pdfmetrics.registerFont(TTFont("Body", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Mono", str(FONT_DIR / "DejaVuSansMono.ttf")))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body",
                           boldItalic="Body-Bold")
        return "Body", "Body-Bold", "Mono"
    except Exception:  # noqa: BLE001 - fall back to core fonts
        return "Helvetica", "Helvetica-Bold", "Courier"


BODY, BOLD, MONO = _fonts()
S = {
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=15, leading=18, textColor=NAVY,
                         spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=11, leading=13.5, textColor=TEAL,
                         spaceBefore=6, spaceAfter=2),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=10, leading=12, textColor=NAVY,
                         spaceBefore=4, spaceAfter=1),
    "p": ParagraphStyle("p", fontName=BODY, fontSize=9, leading=11.6, alignment=TA_LEFT,
                        spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8, leading=9.8),
    "cellh": ParagraphStyle("cellh", fontName=BOLD, fontSize=8, leading=9.8,
                            textColor=colors.white),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=7.5, leading=9,
                           backColor=colors.HexColor("#F2F4F7"), borderPadding=3),
}


_DEVA_RUN = re.compile(r"[ऀ-ॿ]+(?:[\s.][ऀ-ॿ]+)*")


def _deva_fallback(text: str) -> str:
    """reportlab cannot shape Devanagari: render runs as italic IAST transliteration."""
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        return _DEVA_RUN.sub("[hi]", text)
    return _DEVA_RUN.sub(
        lambda m: "\x01" + transliterate(m.group(0), sanscript.DEVANAGARI, sanscript.IAST) + "\x02",
        text)


def inline(text: str) -> str:
    """Convert inline Markdown to reportlab mini-HTML."""
    t = html.escape(_deva_fallback(text), quote=False)
    t = t.replace("\x01", "<i>").replace("\x02", "</i>")
    t = re.sub(r"`([^`]+)`", lambda m: f'<font face="{MONO}">{m.group(1)}</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)
    return t


def mermaid(src: str, width: float) -> Drawing:
    """Draw a simple left-to-right chain from ``A[x] --> B[y]`` lines."""
    labels: dict[str, str] = {}
    order: list[str] = []
    edges: list[tuple[str, str]] = []
    for line in src.splitlines():
        parts = re.split(r"\s*-->\s*(?:\|[^|]*\|\s*)?", line.strip())
        if len(parts) < 2:
            continue
        ids = []
        for part in parts:
            m = re.match(r"(\w+)(?:[\[\(\{]+\"?([^\]\)\}\"]+)\"?[\]\)\}]+)?", part)
            if not m:
                continue
            nid = m.group(1)
            if m.group(2):
                labels[nid] = m.group(2)
            if nid not in order:
                order.append(nid)
            ids.append(nid)
        edges += list(zip(ids, ids[1:]))
    n = max(len(order), 1)
    box_w = min(92.0, (width - 8 * (n - 1)) / n)
    gap = (width - n * box_w) / max(n - 1, 1)
    h = 34.0
    d = Drawing(width, h + 8)
    pos = {nid: i * (box_w + gap) for i, nid in enumerate(order)}
    for nid, x in pos.items():
        d.add(Rect(x, 4, box_w, h, rx=5, ry=5, fillColor=colors.HexColor("#E8F6F4"),
                   strokeColor=TEAL, strokeWidth=0.8))
        words = labels.get(nid, nid).replace("<br/>", " ").split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 > box_w / 4.4 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        for j, ln in enumerate(lines[:3]):
            y = 4 + h / 2 + (len(lines[:3]) - 1) * 4.5 - j * 9 - 2.5
            d.add(String(x + box_w / 2, y, ln, fontName=BODY, fontSize=6.8,
                         textAnchor="middle", fillColor=NAVY))
    for a, b in edges:
        if a in pos and b in pos and pos[b] > pos[a]:
            x1, x2, y = pos[a] + box_w, pos[b], 4 + h / 2
            d.add(Line(x1, y, x2 - 3, y, strokeColor=GREY, strokeWidth=0.8))
            d.add(Polygon([x2, y, x2 - 4, y + 2.2, x2 - 4, y - 2.2], fillColor=GREY,
                          strokeColor=GREY))
    return d


def table(rows: list[list[str]], width: float) -> Table:
    """A styled table; first row is the header."""
    ncol = max(len(r) for r in rows)
    data = [[Paragraph(inline(c), S["cellh" if i == 0 else "cell"]) for c in r + [""] * (ncol - len(r))]
            for i, r in enumerate(rows)]
    lens = [max(len(r[j]) if j < len(r) else 0 for r in rows) + 4 for j in range(ncol)]
    widths = [width * x / sum(lens) for x in lens]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D1DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def convert(md: str, out: Path) -> None:
    """Render Markdown text ``md`` to the PDF file ``out``."""
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=13 * mm, bottomMargin=13 * mm)
    width = A4[0] - 32 * mm
    flow: list = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            flow.append(Paragraph(inline(" ".join(para)), S["p"]))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            flush()
            lang = ln[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            if lang == "mermaid":
                flow.append(mermaid("\n".join(block), width))
                flow.append(Spacer(1, 4))
            else:
                flow.append(Preformatted("\n".join(block), S["code"]))
                flow.append(Spacer(1, 4))
        elif m := re.match(r"(#{1,3})\s+(.*)", ln):
            flush()
            flow.append(Paragraph(inline(m.group(2)), S["h" + str(len(m.group(1)))]))
        elif ln.strip().startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            flow.append(table(rows, width))
            flow.append(Spacer(1, 5))
            continue
        elif re.match(r"\s*([-*]|\d+\.)\s+", ln):
            flush()
            numbered = bool(re.match(r"\s*\d+\.", ln))
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                        and not re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                    text += " " + lines[i].strip()
                    i += 1
                items.append(ListItem(Paragraph(inline(text), S["p"]), leftIndent=10))
            flow.append(ListFlowable(items, bulletType="1" if numbered else "bullet",
                                     start="1" if numbered else None, leftIndent=12,
                                     bulletFontSize=7, bulletFontName=BODY))
            continue
        elif not ln.strip() or ln.strip() == "---":
            flush()
        elif ln.startswith(">"):
            flush()
            flow.append(Paragraph("<i>" + inline(ln.lstrip("> ")) + "</i>", S["p"]))
        else:
            para.append(ln.strip())
        i += 1
    flush()
    doc.build(flow)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: md2pdf.py INPUT.md OUTPUT.pdf")
        return 2
    convert(Path(sys.argv[1]).read_text(encoding="utf-8"), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
