from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfgen import canvas

from app.models import Report


def markdown_bytes(report: Report) -> bytes:
    return report.markdown.encode("utf-8")


def pdf_bytes(report: Report) -> bytes:
    registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 48
    top = height - 52
    line_height = 15

    pdf.setTitle(report.title)
    pdf.setFont("STSong-Light", 14)
    y = top
    for raw_line in report.markdown.splitlines():
        line = raw_line.strip() or " "
        while len(line) > 58:
            y = _draw_line(pdf, line[:58], left, y, line_height, height)
            line = line[58:]
        y = _draw_line(pdf, line, left, y, line_height, height)

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def _draw_line(canvas_obj: canvas.Canvas, line: str, x: int, y: float, line_height: int, height: float) -> float:
    if y < 48:
        canvas_obj.showPage()
        canvas_obj.setFont("STSong-Light", 14)
        y = height - 52
    canvas_obj.drawString(x, y, line)
    return y - line_height

