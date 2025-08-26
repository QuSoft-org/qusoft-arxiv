# --- Begin new implementation based on main_with_cache.py ---
import arxiv
import os
import json
from openpyxl import load_workbook
from io import BytesIO

CACHE_FILE = "query_cache.json"
PORTRAITS_DIR = "qusofters/portraits"
TMP_DIR = "tmp_firstpages"
OUT_PDF = "qusoft_firstpages_2025.pdf"
STARTS_WITH = "25"
# STARTS_WITH = "2506"

os.makedirs(TMP_DIR, exist_ok=True)

def normalize_name(name):
    import unicodedata
    return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii').lower()

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


# Returns dict: normalized_name -> role

def get_qusoft_people_roles(file_path):
    workbook = load_workbook(file_path)
    sheet = workbook.active
    people_roles = {}
    # Name in col 1, Role in col 5
    for row in sheet.iter_rows(min_row=3):
        name_cell = row[0]
        role_cell = row[4] if len(row) > 4 else None
        if name_cell.value:
            norm_name = normalize_name(name_cell.value)
            role = role_cell.value if role_cell and role_cell.value else "Unknown"
            people_roles[norm_name] = role
    return people_roles

def search_arxiv_for_authors(qusoft_people, cache):
    client = arxiv.Client()
    results = []
    for person in qusoft_people:
        cache_key = f"arxiv:{person}"
        if cache_key in cache:
            person_results = cache[cache_key]
        else:
            print(f"Searching arXiv for papers by {person}...")
            search = arxiv.Search(
                query=f'au:"{person}"',
                max_results=10,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )
            person_results = []
            try:
                for result in client.results(search):
                    highlighted_authors = []
                    qusoft_author_count = 0
                    for author in result.authors:
                        normalized_author = normalize_name(author.name)
                        if normalized_author in qusoft_people:
                            highlighted_authors.append(f"**{author.name}**")
                            qusoft_author_count += 1
                        else:
                            highlighted_authors.append(author.name)
                    entry = {
                        "source": "arXiv",
                        "id": result.entry_id.split("/")[-1],
                        "link": result.entry_id,
                        "authors": ", ".join(highlighted_authors),
                        "title": result.title,
                        "revision": str(result.updated.replace(tzinfo=None)),
                        "qusoft_author_count": qusoft_author_count
                    }
                    person_results.append(entry)
            except arxiv.UnexpectedEmptyPageError as e:
                print(f"Warning: No results for {person} ({e})")
            cache[cache_key] = person_results
            save_cache(cache)
        results.extend(person_results)
    return results


def find_portrait(author):
    key = normalize_name(author).replace(" ", "_")
    for f in os.listdir(PORTRAITS_DIR):
        name = os.path.splitext(f)[0].lower()
        if key in name:
            return os.path.join(PORTRAITS_DIR, f)
    print(f"No portrait found for author '{author}'")
    return None

# Helper: create a PDF page with portraits and first page

# portrait_info: list of (portrait_path, role)

def create_combined_page(portrait_info, first_page_pdf_path):
    import fitz
    from PIL import Image
    import tempfile
    import os

    # Open the first page of the PDF
    src_doc = fitz.open(first_page_pdf_path)
    src_page = src_doc[0]

    # Create a new blank page with same size
    width, height = src_page.rect.width, src_page.rect.height
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    # Scale down the first page and insert it lower
    scale = 0.85
    new_width = width * scale
    new_height = height * scale
    x_offset = (width - new_width) / 2
    y_offset = 160  # leave space for portraits at the top
    page.show_pdf_page(
        fitz.Rect(x_offset, y_offset, x_offset + new_width, y_offset + new_height),
        src_doc,
        0
    )

    # Highlight 'QuSoft', 'CWI' etc. in yellow
    highlight_words = ["QuSoft", "CWI", "University of Amsterdam", "Centrum voor Wiskunde en Informatica"]
    for word in highlight_words:
        for inst in page.search_for(word, quads=True):
            highlight = page.add_highlight_annot(inst)
            highlight.set_colors(stroke=(1,1,0))  # yellow
            highlight.update()

    # Add normalized author names to highlight_words
    highlight_words = [norm_name for _, _, norm_name in portrait_info]
    for word in highlight_words:
        for inst in page.search_for(word, quads=True):
            highlight = page.add_highlight_annot(inst)
            highlight.set_colors(stroke=(1,0.7,0))  # light orange
            highlight.update()



    first_page_text = src_page.get_text()
    if "qusoft" not in first_page_text.lower():
        print(f"Warning: 'QuSoft' not found on first page of PDF")
        # add text annotation
        rect = fitz.Rect(20,170,400,190)
        page.add_freetext_annot(rect, "'QuSoft' not mentioned on first page", fontsize=12, text_color=(1, 0, 0))


    # Add portraits as stamps at the top
    x = 50
    y = 40
    for p_path, role, _ in portrait_info:
        if not os.path.exists(p_path):
            print(f"Warning: Portrait not found: {p_path}")
            continue
        # Set portrait size by role
        role_str = str(role).lower() if role else ""
        if "students" in role_str or "support" in role_str:
            w, h = 120, 120
        elif "postdoc" in role_str:
            w, h = 100, 100
        else:
            w, h = 80, 80
        rect = fitz.Rect(x, y, x + w, y + h)
        # Convert image to RGB and PNG
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img_png:
            img = Image.open(p_path).convert("RGB")
            img.save(tmp_img_png.name, "PNG")
            pix = fitz.Pixmap(tmp_img_png.name)
            page.add_stamp_annot(rect, stamp=pix)
        x += w + 20


    # add QIP submission question:
    if 580-x > 180:
        x_pos = x
        y_pos = 70
    else:
        x_pos = 300
        y_pos = 170
    page.add_freetext_annot((x_pos, y_pos, x_pos + 160, y_pos + 40), "submission to QIP2026?  YES             NO", fontsize=12, text_color=(0, 0, 0))
    page.draw_rect((x_pos+33, y_pos + 15, x_pos + 43, y_pos + 25))
    page.draw_rect((x_pos+91, y_pos + 15, x_pos + 101, y_pos + 25))

    return doc


def main():
    qusoft_people_file = "24-04-22-QuSoftDB.xlsx"
    people_roles = get_qusoft_people_roles(qusoft_people_file)
    qusoft_people = list(people_roles.keys())
    cache = load_cache()
    arxiv_papers = search_arxiv_for_authors(qusoft_people, cache)
    papers_2025 = [p for p in arxiv_papers if p["id"].startswith(STARTS_WITH)]
    papers_2025.sort(key=lambda p: p["id"], reverse=True)
    seen_ids = set()
    unique_papers_2025 = []
    for p in papers_2025:
        if p["id"] not in seen_ids:
            unique_papers_2025.append(p)
            seen_ids.add(p["id"])
    papers_2025 = unique_papers_2025

    import fitz
    output_doc = fitz.open()

    for paper in papers_2025:
        arxiv_id = paper["id"]
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        pdf_path = os.path.join(TMP_DIR, f"{arxiv_id}.pdf")
        cache_key = f"pdf:{arxiv_id}"
        if cache.get(cache_key) == "downloaded" and os.path.exists(pdf_path):
            pass
        else:
            print(f"Downloading PDF for {arxiv_id}...")
            import requests
            r = requests.get(pdf_url)
            with open(pdf_path, "wb") as f:
                f.write(r.content)
            cache[cache_key] = "downloaded"
            save_cache(cache)
        author_names = [a.strip().replace("**","") for a in paper["authors"].split(",")]
        portrait_info = []
        for a in author_names:
            norm_a = normalize_name(a)
            portrait = find_portrait(a)
            role = people_roles.get(norm_a, "Unknown")
            if portrait:
                portrait_info.append((portrait, role, norm_a))
            else:
                print(f"Warning: No portrait found for author '{a}' in paper {arxiv_id}")
        try:
            combined_doc = create_combined_page(portrait_info, pdf_path)
            output_doc.insert_pdf(combined_doc)
        except Exception as e:
            print(f"Error combining portraits for {arxiv_id}: {e}")
            output_doc.insert_pdf(fitz.open(pdf_path))

    output_doc.save(OUT_PDF)
    print(f"Created {OUT_PDF}")

if __name__ == "__main__":
    main()
# --- End new implementation ---
