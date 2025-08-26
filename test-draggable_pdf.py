import fitz
from PIL import Image

input_pdf = "draggable_annotations.pdf"
portrait_img = "qusofters/portraits/lynn_engelberts.jpg"
tmp_pdf = "portrait_stamp.pdf"
output_pdf = "output_with_stamp.pdf"

img = Image.open(portrait_img).convert("RGB")
img.save(tmp_pdf, "PNG", resolution=100.0)
doc = fitz.open(input_pdf)
page = doc[0]
rect = fitz.Rect(50, 100, 200, 250)
page.add_stamp_annot(rect, stamp=tmp_pdf)
doc.save(output_pdf)