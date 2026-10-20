"""Make the annotated first page of a paper, for printing and for the website.

The original first page is scaled down, QuSoft affiliations are highlighted in
yellow and QuSoft authors in orange, portraits go along the top (alumni get
their QuSoft years underneath), and a QR code links to the arXiv page.
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


def _portrait_image(portrait_path, size_pt, years):
    """Square portrait at print resolution, with the years written underneath for alumni."""
    res = CFG["portrait_resolution"]
    px = int(size_pt * res)
    img = ImageOps.fit(Image.open(portrait_path).convert("RGB"), (px, px), Image.LANCZOS)
    overlay = CFG["alumni_year_overlay"]
    extra_pt = 0
    if years and overlay["enabled"]:
        extra_pt = overlay["font_size"] + 2 * overlay["padding"] + 2
        canvas = Image.new("RGB", (px, px + int(extra_pt * res)), "white")
        canvas.paste(img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=overlay["font_size"] * res)
        width = draw.textlength(years, font=font)
        draw.text(((px - width) / 2, px + overlay["padding"] * res), years,
                  fill=tuple(overlay["color"]), font=font)
        img = canvas
    return img, size_pt + extra_pt


def _highlight(page, text, color):
    for quad in page.search_for(text, quads=True):
        annot = page.add_highlight_annot(quad)
        annot.set_colors(stroke=color)
        annot.update()


def make_first_page(paper, source_pdf, people):
    """Return a one-page fitz.Document for this paper."""
    src = fitz.open(source_pdf)
    width, height = src[0].rect.width, src[0].rect.height
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)

    scale, top = 0.85, 160
    x0 = (width - width * scale) / 2
    page.show_pdf_page(fitz.Rect(x0, top, x0 + width * scale, top + height * scale), src, 0)
    src.close()

    for word in AFFILIATION_WORDS:
        _highlight(page, word, YELLOW)
    for author in paper["authors"]:
        if author["person"]:
            _highlight(page, author["name"], ORANGE)

    # Portraits along the top, in author order.
    x, y = 50, 40
    for author in paper["authors"]:
        person = author["person"]
        portrait = find_portrait(person) if person else None
        if not portrait:
            continue
        info = people.get(person, {})
        size = CFG["portrait_sizes"].get(info.get("role"), CFG["portrait_sizes"]["default"])
        if x + size > width - 20:  # wrap to a second row rather than run off the page
            x, y = 50, y + 100
        img, h = _portrait_image(portrait, size, tenure(info) if is_alumnus(info) else "")
        page.add_stamp_annot(fitz.Rect(x, y, x + size, y + h), stamp=fitz.Pixmap(_png(img)))
        x += size + 20

    if CFG["submission_to_qip_box"]:
        bx, by = (x, 70) if width - 30 - x > 180 else (300, 170)
        page.add_freetext_annot((bx, by, bx + 160, by + 40), "submission to QIP?  YES             NO",
                                fontsize=12, text_color=(0, 0, 0))
        page.draw_rect((bx + 33, by + 15, bx + 43, by + 25))
        page.draw_rect((bx + 91, by + 15, bx + 101, by + 25))

    qr = qrcode.make(paper["link"], box_size=4, border=1).convert("RGB")
    q = 70
    page.add_stamp_annot(fitz.Rect(width - q - 15, height - q - 20, width - 15, height - 20),
                         stamp=fitz.Pixmap(_png(qr)))
    return doc


def save_first_page(doc, pdf_out, thumb_out):
    """Write the page as a compact PDF and a WebP thumbnail for the website."""
    Path(pdf_out).parent.mkdir(parents=True, exist_ok=True)
    Path(thumb_out).parent.mkdir(parents=True, exist_ok=True)
    doc.save(pdf_out, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)

    page = doc[0]
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
