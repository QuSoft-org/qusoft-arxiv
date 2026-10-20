"""Make the annotated first page of a paper, for printing and for the website.

The original first page is scaled down, QuSoft affiliations are highlighted in
yellow and QuSoft authors in orange, portraits go along the top (alumni get
their QuSoft years underneath) next to a QR code to the arXiv page, and the
paper's page is cropped to its content and scaled to fill the rest.
Portraits and the QR code are stamp annotations, so they can still be dragged
around in a PDF editor before printing.
"""

import io
from pathlib import Path

import fitz  # PyMuPDF
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .common import CONFIG, find_portrait, is_alumnus, tenure

CFG = CONFIG["first_page"]
AFFILIATION_WORDS = ["QuSoft", "CWI", "University of Amsterdam", "Centrum voor Wiskunde en Informatica", "Centrum Wiskunde"]
YELLOW = (1, 1, 0)
ORANGE = (1, 0.7, 0)


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _font(size_px):
    """Helvetica as shipped with PyMuPDF, so the en dash renders on every machine."""
    return ImageFont.truetype(io.BytesIO(fitz.Font("helv").buffer), size_px)


def _year_lines(years):
    """'2018–2022' becomes ['2018–', '2022'], so labels fit under narrow portraits."""
    if "–" in years:
        start, end = years.split("–", 1)
        return [f"{start}–", end]
    return years.split(" ", 1) if years.startswith("until ") else [years]


def _portrait_image(portrait_path, size_pt, years):
    """Square portrait at print resolution, with the years written underneath for alumni."""
    res = CFG["portrait_resolution"]
    px = int(size_pt * res)
    img = ImageOps.fit(Image.open(portrait_path).convert("RGB"), (px, px), Image.LANCZOS)
    overlay = CFG["alumni_year_overlay"]
    extra_pt = 0
    if years and overlay["enabled"]:
        lines = _year_lines(years)
        line_pt = overlay["font_size"] * 1.2
        extra_pt = overlay["padding"] + line_pt * len(lines)
        canvas = Image.new("RGB", (px, px + int(extra_pt * res)), "white")
        canvas.paste(img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _font(int(overlay["font_size"] * res))
        for i, line in enumerate(lines):
            draw.text((px / 2, (size_pt + overlay["padding"] + line_pt * i) * res), line,
                      fill=tuple(overlay["color"]), font=font, anchor="mt")
        img = canvas
    return img, size_pt + extra_pt


def _highlight(shape, src_page, clip, matrix, text, color):
    """Paint highlight colour where `text` appears; the paper's page is drawn on top of it.

    Real highlight annotations break the embedded fonts of some papers once saved
    (a PyMuPDF quirk), so the colour is part of the page instead.
    """
    for quad in src_page.search_for(text, quads=True, clip=clip):
        shape.draw_rect(quad.rect * matrix)
    shape.finish(color=None, fill=color)


def _content_box(page):
    """The part of a page that has text, images or drawings on it, without the empty margins."""
    rects = [fitz.Rect(b[:4]) for b in page.get_text("blocks")]
    rects += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    rects += [d["rect"] for d in page.get_drawings() if d["rect"].width < page.rect.width * 0.98]
    box = fitz.Rect()
    for r in rects:
        if r.is_valid and not r.is_empty:
            box |= r
    box = (box + (-6, -6, 6, 6)) & page.rect
    return box if box.is_valid and box.width > 50 and box.height > 50 else page.rect


MARGIN, GAP, QR = 24, 12, 64


def _portrait_rows(paper, people, right_edge):
    """Lay portraits out left to right in author order, wrapping into rows."""
    items = []
    for author in paper["authors"]:
        person = author["person"]
        portrait = find_portrait(person) if person else None
        if portrait:
            info = people.get(person, {})
            sizes = CFG["portrait_sizes"]
            role = "Alumni" if is_alumnus(info) else info.get("role")
            size = sizes.get(role, sizes["default"])
            img, h = _portrait_image(portrait, size, tenure(info) if is_alumnus(info) else "")
            items.append((img, size, h))
    rows, row, x = [], [], MARGIN
    for item in items:
        if row and x + item[1] > right_edge:
            rows.append(row)
            row, x = [], MARGIN
        row.append(item)
        x += item[1] + GAP
    if row:
        rows.append(row)
    return rows


def _qip_box(page, x, band, width):
    """'Submission to QIP?  [ ] yes  [ ] no', next to the last portrait row if it fits, else below it."""
    parts, fs = ["Submission to QIP?", "yes", "no"], 11
    w = sum(fitz.get_text_length(t, fontsize=fs) for t in parts) + 3 * (fs + 14)
    if width - MARGIN - QR - GAP - x >= w:
        y = band - GAP - fs - 4
    else:
        x, y, band = MARGIN, band, band + fs + 4 + GAP
    page.insert_text((x, y + fs), parts[0], fontsize=fs)
    x += fitz.get_text_length(parts[0], fontsize=fs) + 14
    for label in parts[1:]:
        page.draw_rect(fitz.Rect(x, y + 1, x + fs, y + 1 + fs), width=0.8)
        page.insert_text((x + fs + 4, y + fs), label, fontsize=fs)
        x += fs + 4 + fitz.get_text_length(label, fontsize=fs) + 14
    return band


def make_first_page(paper, source_pdf, people):
    """Return a one-page fitz.Document for this paper."""
    src = fitz.open(source_pdf)
    width, height = src[0].rect.width, src[0].rect.height
    clip = _content_box(src[0])
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)

    # Top band: portraits on the left, QR code on the right.
    rows = _portrait_rows(paper, people, width - MARGIN - QR - GAP)
    y = MARGIN
    for row in rows:
        row_h = max(h for _, _, h in row)
        x = MARGIN
        for img, size, h in row:
            top = y  # portraits share a top line; alumni years hang below
            page.add_stamp_annot(fitz.Rect(x, top, x + size, top + h), stamp=fitz.Pixmap(_png(img)))
            x += size + GAP
        y += row_h + GAP
    last_x = x if rows else MARGIN
    band = max(y - GAP, MARGIN + QR) + GAP

    qr = qrcode.make(paper["link"], box_size=4, border=1).convert("RGB")
    page.add_stamp_annot(fitz.Rect(width - MARGIN - QR, MARGIN, width - MARGIN, MARGIN + QR),
                         stamp=fitz.Pixmap(_png(qr)))

    if CFG["submission_to_qip_box"]:
        band = _qip_box(page, last_x, band, width)

    # The paper's own first page, cropped to its content and as large as fits below the band.
    avail_w, avail_h = width - 2 * MARGIN, height - band - MARGIN / 2
    scale = min(avail_w / clip.width, avail_h / clip.height)
    w, h = clip.width * scale, clip.height * scale
    x0 = (width - w) / 2
    matrix = fitz.Matrix(1, 0, 0, 1, -clip.x0, -clip.y0) * fitz.Matrix(scale, scale) * fitz.Matrix(1, 0, 0, 1, x0, band)

    shape = page.new_shape()
    for word in AFFILIATION_WORDS:
        _highlight(shape, src[0], clip, matrix, word, YELLOW)
    for author in paper["authors"]:
        if author["person"]:
            _highlight(shape, src[0], clip, matrix, author["name"], ORANGE)
    shape.commit()

    page.show_pdf_page(fitz.Rect(x0, band, x0 + w, band + h), src, 0, clip=clip)
    src.close()
    return doc


def save_first_page(doc, pdf_out, thumb_out):
    """Write the page as a compact PDF and a WebP thumbnail for the website."""
    Path(pdf_out).parent.mkdir(parents=True, exist_ok=True)
    Path(thumb_out).parent.mkdir(parents=True, exist_ok=True)
    doc.save(pdf_out, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)

    # Render from the saved file: the in-memory page no longer has the source PDF's fonts.
    with fitz.open(pdf_out) as saved:
        page = saved[0]
        zoom = CFG["thumbnail_width"] / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), annots=True)
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(thumb_out, "WEBP", quality=72, method=6)


def has_qusoft_on_first_page(source_pdf):
    try:
        with fitz.open(source_pdf) as doc:
            return len(doc) > 0 and "qusoft" in doc[0].get_text().lower()
    except Exception as e:
        print(f"    could not read {source_pdf}: {e}")
        return False
