import fitz  # PyMuPDF
import os
from PIL import Image

# Paths
TMP_DIR = "tmp_firstpages"
PORTRAITS_DIR = "qusofters/portraits"
OUT_PDF = "qusoft_firstpages_2025_annotated.pdf"
FIRSTPAGE_PDF = os.path.join(TMP_DIR, "qusoft_firstpages_2025.pdf")  # Input PDF with first page only
os.makedirs(TMP_DIR, exist_ok=True)

# Example portrait info: list of (filename, x, y, width, height)
# You should generate this from your data
portrait_info = [
    (os.path.join(PORTRAITS_DIR, "lynn_engelberts.jpg"), 50, 100, 150, 150),
    (os.path.join(PORTRAITS_DIR, "sebastian_verschoor.jpg"), 220, 100, 120, 120),
    (os.path.join(PORTRAITS_DIR, "jonas_helsen.jpg"), 360, 100, 90, 90),
]

def add_portrait_annotations(pdf_path, portrait_info, out_pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]  # First page
    for img_path, x, y, w, h in portrait_info:
        if not os.path.exists(img_path):
            print(f"Warning: Portrait not found: {img_path}")
            continue
        rect = fitz.Rect(x, y, x + w, y + h)
        pix = fitz.Pixmap(img_path)
        annot = page.add_stamp_annot(rect, stamp=pix)
    doc.save(out_pdf_path)
    print(f"Saved annotated PDF to {out_pdf_path}")

if __name__ == "__main__":
    add_portrait_annotations(FIRSTPAGE_PDF, portrait_info, OUT_PDF)
