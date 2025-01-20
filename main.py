import arxiv
import ssl
import certifi
import feedparser
from openpyxl import load_workbook, Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from unicodedata import normalize
from datetime import datetime


def normalize_name(name):
    """
    Normalize a name by removing special characters and converting to plain text.
    """
    return normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii').lower()


def get_qusoft_people(file_path):
    # Load the QuSoft database Excel sheet
    workbook = load_workbook(file_path)
    sheet = workbook.active

    # Extract and normalize names from column A, starting from row 3
    qusoft_people = [
        normalize_name(row[0].value) for row in sheet.iter_rows(min_row=3, max_col=1) if row[0].value
    ]
    return qusoft_people


def search_arxiv_for_authors(qusoft_people):
    # Initialize the arXiv client
    client = arxiv.Client()

    # Collect results for all QuSoft people
    results = []
    for person in qusoft_people:
        print(f"Searching arXiv for papers by {person}...")
        search = arxiv.Search(
            query=f'au:"{person}"',  # Search for the author's name without date restriction
            max_results=20,  # Limit results per author
            sort_by=arxiv.SortCriterion.SubmittedDate
        )

        for result in client.results(search):
            # Highlight QuSoft authors in the author list
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
                "revision": result.updated.replace(tzinfo=None),
                "qusoft_author_count": qusoft_author_count
            }
            results.append(entry)

    return results


def search_iacr_for_authors(qusoft_people):
    # URL of the IACR ePrint Archive RSS feed
    rss_url = "https://eprint.iacr.org/rss/rss.xml"

    # Disable SSL verification
    ssl_context = ssl._create_unverified_context()

    # Parse the RSS feed
    feed = feedparser.parse(rss_url, request_headers={})

    results = []
    for entry in feed.entries:
        # Extract authors from the entry
        authors = entry.get("authors", [])

        # Normalize and check for QuSoft authors
        highlighted_authors = []
        qusoft_author_count = 0
        for author in authors:
            normalized_author = normalize_name(author)
            if normalized_author in qusoft_people:
                highlighted_authors.append(f"**{author}**")
                qusoft_author_count += 1
            else:
                highlighted_authors.append(author)

        if qusoft_author_count > 0:
            # Parse the publication date
            pub_date = datetime(*entry.published_parsed[:6])

            result_entry = {
                "source": "IACR ePrint",
                "id": entry.link.split("/")[-1],
                "link": entry.link,
                "authors": ", ".join(highlighted_authors),
                "title": entry.title,
                "revision": pub_date,
                "qusoft_author_count": qusoft_author_count
            }
            results.append(result_entry)

    return results


def save_to_excel(data, output_file):
    # Create an Excel workbook and select the active worksheet
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "QuSoft Papers"

    # Add column headers
    headers = ["source", "id", "list of authors", "title", "revision", "qusoft_author_count"]
    sheet.append(headers)

    # Populate rows with data
    for entry in data:
        row = [
            entry["source"],  # Source (arXiv or IACR ePrint)
            entry["id"],  # Paper ID
            entry["authors"],  # Authors with highlighted QuSoft people
            entry["title"],  # Paper title
            entry["revision"],  # Revision date
            entry["qusoft_author_count"]  # Count of QuSoft-affiliated authors
        ]
        sheet.append(row)

        # Add hyperlink to Paper ID
        id_cell = sheet.cell(row=sheet.max_row, column=2)
        id_cell.hyperlink = entry["link"]
        id_cell.style = "Hyperlink"

    # Define a table range
    table_range = f"A1:F{sheet.max_row}"
    table = Table(displayName="QuSoftTable", ref=table_range)

    # Add a table style
    style = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=True
    )
    table.tableStyleInfo = style
    sheet.add_table(table)

    # Save the workbook
    workbook.save(output_file)
    print(f"Data saved to {output_file}")


if __name__ == "__main__":
    # Load QuSoft people list
    qusoft_people_file = "QuSoftDB.xlsx"
    qusoft_people = get_qusoft_people(qusoft_people_file)

    # Search arXiv for QuSoft authors
    arxiv_papers = search_arxiv_for_authors(qusoft_people)
    # arxiv_papers = []

    # Search IACR ePrint Archive for QuSoft authors
    # iacr_papers = search_iacr_for_authors(qusoft_people)
    iacr_papers = []

    # Combine results
    all_papers = arxiv_papers + iacr_papers

    # Save the results to an Excel file
    output_file = "qusoft_papers.xlsx"
    save_to_excel(all_papers, output_file)
