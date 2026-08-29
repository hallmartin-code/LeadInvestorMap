"""Drawing primitives for the one-pager.

Everything here draws directly on the canvas and returns the height it consumed, so the
generator can measure a layout before committing to it and shrink where necessary.
"""

from __future__ import annotations

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, Table, TableStyle

from . import theme as T


def style(
    size: float = T.BODY_SIZE,
    *,
    bold: bool = False,
    color=T.BODY,
    leading: float | None = None,
    align: int = 0,
    italic: bool = False,
) -> ParagraphStyle:
    font = T.FONT_BOLD if bold else (T.FONT_ITALIC if italic else T.FONT)
    return ParagraphStyle(
        name=f"s{size}{bold}{italic}{align}{color}",
        fontName=font,
        fontSize=size,
        leading=leading or size * T.LEADING_RATIO,
        textColor=color,
        alignment=align,
        spaceBefore=0,
        spaceAfter=0,
    )


def escape(text: str | None) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para(text: str, para_style: ParagraphStyle) -> Paragraph:
    """A paragraph of plain text. Markup in the text is shown, not interpreted."""
    return Paragraph(escape(text), para_style)


def rich(template: str, para_style: ParagraphStyle, **values: str) -> Paragraph:
    """A paragraph with intentional inline markup.

    The template carries the tags; every substituted value is escaped, so content from a
    document can never inject markup of its own.
    """
    safe = {key: escape(value) for key, value in values.items()}
    return Paragraph(template.format(**safe), para_style)


def measure(flowable, width: float) -> float:
    try:
        return flowable.wrap(width, 10_000)[1]
    except Exception:  # pragma: no cover - defensive
        return 12.0


def truncate_to_width(text: str, width: float, font: str, size: float) -> str:
    """Hard single-line truncation, used where wrapping would break a table row."""
    if stringWidth(text, font, size) <= width:
        return text
    ellipsis = "..."
    while text and stringWidth(text + ellipsis, font, size) > width:
        text = text[:-1]
    return text.rstrip(" ,;:-") + ellipsis


# --- primitives ---------------------------------------------------------------------------


def rule(canvas, x: float, y: float, width: float, *, color=T.RULE, thickness: float = 0.5) -> None:
    canvas.setStrokeColor(color)
    canvas.setLineWidth(thickness)
    canvas.line(x, y, x + width, y)


def section_label(canvas, x: float, y: float, text: str, width: float | None = None) -> float:
    """A small capitalised section heading with a hairline under it."""
    canvas.setFont(T.FONT_BOLD, T.SECTION_SIZE)
    canvas.setFillColor(T.NAVY)
    canvas.drawString(x, y - T.SECTION_SIZE, text.upper())
    if width:
        rule(canvas, x, y - T.SECTION_SIZE - 3.5, width, color=T.RULE)
    return T.SECTION_SIZE + 6.5


def chip(
    canvas,
    x: float,
    y: float,
    text: str,
    colors: tuple,
    *,
    size: float = T.MICRO_SIZE,
    padding: float = 3.0,
    height: float = 9.5,
) -> float:
    """A small labelled tag. Returns its width. The word carries the meaning, not the tint."""
    fg, bg = colors
    text_width = stringWidth(text, T.FONT_BOLD, size)
    width = text_width + padding * 2
    canvas.setFillColor(bg)
    canvas.rect(x, y - height + 2.0, width, height, stroke=0, fill=1)
    canvas.setFillColor(fg)
    canvas.setFont(T.FONT_BOLD, size)
    canvas.drawString(x + padding, y - height + 4.9, text)
    return width


def tile(
    canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    value: str,
    *,
    emphasis: bool = False,
    note: str = "",
) -> None:
    """One cell of the round snapshot strip."""
    canvas.setFillColor(T.BAND if emphasis else T.PAPER)
    canvas.setStrokeColor(T.HAIRLINE)
    canvas.setLineWidth(0.5)
    canvas.rect(x, y - height, width, height, stroke=1, fill=1)

    canvas.setFont(T.FONT_BOLD, T.TILE_LABEL_SIZE)
    canvas.setFillColor(T.MUTED)
    canvas.drawString(x + 5, y - 10.5, label.upper())

    value_size = T.TILE_VALUE_SIZE
    available = width - 10
    while value_size > 6.5 and stringWidth(value, T.FONT_BOLD, value_size) > available:
        value_size -= 0.5
    canvas.setFont(T.FONT_BOLD, value_size)
    canvas.setFillColor(T.NAVY if emphasis else T.INK)
    canvas.drawString(x + 5, y - 23.5, truncate_to_width(value, available, T.FONT_BOLD, value_size))

    if note:
        canvas.setFont(T.FONT, T.TILE_LABEL_SIZE)
        canvas.setFillColor(T.FAINT)
        canvas.drawString(
            x + 5, y - height + 4.5, truncate_to_width(note, available, T.FONT, T.TILE_LABEL_SIZE)
        )


def table(
    rows: list[list],
    col_widths: list[float],
    *,
    header: bool = True,
    row_tint: bool = True,
    font_size: float = T.BODY_SIZE,
    padding: float = 3.0,
) -> Table:
    """A hairline-ruled table. Cells may be strings or Paragraphs."""
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ("FONTNAME", (0, 0), (-1, -1), T.FONT),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 0), (-1, -1), T.BODY),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, T.HAIRLINE),
    ]
    if header:
        commands += [
            ("FONTNAME", (0, 0), (-1, 0), T.FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, 0), max(6.2, font_size - 1.4)),
            ("TEXTCOLOR", (0, 0), (-1, 0), T.MUTED),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, T.RULE),
            ("BOTTOMPADDING", (0, 0), (-1, 0), padding + 1),
        ]
    if row_tint:
        start = 1 if header else 0
        for index in range(start, len(rows)):
            if (index - start) % 2 == 1:
                commands.append(("BACKGROUND", (0, index), (-1, index), T.PAPER))

    built = Table(rows, colWidths=col_widths, hAlign="LEFT")
    built.setStyle(TableStyle(commands))
    return built


def bullet_lines(
    canvas,
    x: float,
    y: float,
    width: float,
    items: list[str],
    *,
    font_size: float = T.BODY_SIZE,
    marker: str = "-",
    color=T.BODY,
    max_items: int | None = None,
    leading_gap: float = 1.5,
) -> float:
    """Draw wrapped bullet lines. Returns the height consumed."""
    consumed = 0.0
    body = style(font_size, color=color)
    shown = items if max_items is None else items[:max_items]
    for item in shown:
        text = f"{marker} {item}" if marker else item
        flow = para(text, body)
        height = measure(flow, width)
        flow.drawOn(canvas, x, y - consumed - height)
        consumed += height + leading_gap
    return consumed


def arrow_chain(
    canvas, x: float, y: float, width: float, steps: list[str], *, font_size: float = T.BODY_SIZE
) -> float:
    """Render a momentum path, wrapping onto further lines where needed."""
    if not steps:
        return 0.0
    separator = "  >  "
    lines: list[str] = []
    current = ""
    for step in steps:
        candidate = step if not current else current + separator + step
        if stringWidth(candidate, T.FONT, font_size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # A wrapped step keeps its arrow, so the chain still reads as a sequence.
            current = "> " + step
    if current:
        lines.append(current)

    consumed = 0.0
    canvas.setFont(T.FONT, font_size)
    canvas.setFillColor(T.BODY)
    for line in lines:
        canvas.drawString(x, y - consumed - font_size, truncate_to_width(line, width, T.FONT, font_size))
        consumed += font_size * T.LEADING_RATIO
    return consumed
