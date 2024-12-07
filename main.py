# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.
import arxiv
from openpyxl import Workbook


def find_lami():
    # Initialize the arXiv client
    client = arxiv.Client()

    # Define the search query
    search = arxiv.Search(
        query='au:"Ludovico Lami"',
        max_results=10,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    # Prepare data for Excel
    data = []
    for result in client.results(search):
        # Convert timezone-aware datetime to naive datetime
        revision_naive = result.updated.replace(tzinfo=None)

        entry = {
            "arxivid": result.entry_id.split("/")[-1],  # Extract the arXiv ID
            "authors": ", ".join([author.name for author in result.authors]),
            "title": result.title,
            "revision": revision_naive
        }
        data.append(entry)

    # Save data to Excel
    save_to_excel(data)


def save_to_excel(data):
    # Create an Excel workbook and select the active worksheet
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lami's Papers"

    # Add column headers
    headers = ["arxivid", "list of authors", "title", "revision"]
    sheet.append(headers)

    # Populate rows with data
    for entry in data:
        sheet.append([entry["arxivid"], entry["authors"], entry["title"], entry["revision"]])

    # Save the workbook
    workbook.save("lami_papers.xlsx")
    print("Data saved to lami_papers.xlsx")


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    find_lami()
