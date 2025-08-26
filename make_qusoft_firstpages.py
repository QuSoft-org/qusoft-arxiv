
# --- Begin new implementation based on main_with_cache.py ---
import arxiv
import os
import json
from openpyxl import load_workbook
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

CACHE_FILE = "query_cache.json"
PORTRAITS_DIR = "qusofters/portraits"
TMP_DIR = "tmp_firstpages"
OUT_PDF = "qusoft_firstpages_2025.pdf"
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
    key = author.lower().replace(" ", "_")
    for f in os.listdir(PORTRAITS_DIR):
        name = os.path.splitext(f)[0].lower()
        if key in name:
            return os.path.join(PORTRAITS_DIR, f)
    return None

# Helper: create a PDF page with portraits and first page

# portrait_info: list of (portrait_path, role)

def create_combined_page(portrait_info, first_page_pdf_path):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    top_margin = 180  # More whitespace on top
    y = height - top_margin
    x = 50
    for p_path, role in portrait_info:
        try:
            img = Image.open(p_path)
            role_str = str(role).lower() if role else ""
            if "student" in role_str:
                img.thumbnail((200, 200))
                c.drawImage(ImageReader(img), x, y, width=120, height=120)
                x += 140
            elif "postdoc" in role_str:
                img.thumbnail((160, 160))
                c.drawImage(ImageReader(img), x, y, width=100, height=100)
                x += 120
            else:
                img.thumbnail((120, 120))
                c.drawImage(ImageReader(img), x, y, width=80, height=80)
                x += 100
        except Exception:
            continue
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(first_page_pdf_path, first_page=1, last_page=1)
        if images:
            firstpage_img_path = os.path.join(TMP_DIR, "firstpage_temp.png")
            images[0].save(firstpage_img_path)
            # Make PDF part bigger and leave more space above
            c.drawImage(firstpage_img_path, 40, 50, width=width-80, height=y-20)
    except ImportError:
        print("pdf2image not installed, skipping first page image overlay.")
        pass
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def main():
    qusoft_people_file = "24-04-22-QuSoftDB.xlsx"
    people_roles = get_qusoft_people_roles(qusoft_people_file)
    qusoft_people = list(people_roles.keys())
    cache = load_cache()
    arxiv_papers = search_arxiv_for_authors(qusoft_people, cache)
    papers_2025 = [p for p in arxiv_papers if p["id"].startswith("2507")]
    writer = PdfWriter()

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
                portrait_info.append((portrait, role))
            else:
                print(f"Warning: No portrait found for author '{a}' in paper {arxiv_id}")
        if portrait_info:
            try:
                combined_pdf = create_combined_page(portrait_info, pdf_path)
                writer.add_page(combined_pdf.pages[0])
            except Exception as e:
                print(f"Error combining portraits for {arxiv_id}: {e}")
                reader = PdfReader(pdf_path)
                writer.add_page(reader.pages[0])
        else:
            reader = PdfReader(pdf_path)
            writer.add_page(reader.pages[0])

    with open(OUT_PDF, "wb") as f:
        writer.write(f)
    print(f"Created {OUT_PDF}")

if __name__ == "__main__":
    main()
# --- End new implementation ---
