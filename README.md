# QuSoft arXiv Scanner

A unified Python script that searches arXiv for papers by QuSoft authors and generates both Excel reports and annotated PDF collections.

## Features

- **Intelligent Search**: Uses advanced strategies to handle Unicode characters in author names
- **Excel Export**: Generates formatted spreadsheets with hyperlinks and QuSoft author highlighting
- **PDF Generation**: Creates annotated first pages with author portraits, QR codes, and highlighting
- **Comprehensive Caching**: Avoids redundant API calls and PDF downloads
- **Flexible Filtering**: Support for year-based filtering and author-specific searches

## Directory Structure

The script creates and uses the following directories:

```
cache/
├── query_cache.json          # Cached arXiv search results
└── downloaded_pdfs/          # Downloaded PDF files
qusofters/portraits/          # Author portrait images
tmp_firstpages/              # Temporary files for PDF generation
```

## Configuration

Edit the configuration section in `qusoft_arxiv_scanner.py`:

```python
# Filter configuration
STARTS_WITH = "25"  # Only include papers starting with this (e.g., "25" for 2025 papers)

# Authors filter: Process specific authors only
AUTHORS = []  # Process all authors
# AUTHORS = ["Llorenç Escolà-Farràs", "Christian Schaffner"]  # Only these authors

# Feature flags
SUBMISSION_TO_QIP_BOX = False  # Add QIP submission checkbox to PDFs
ENABLE_HTTP_LOGGING = False    # Enable detailed HTTP request logging
```

## Usage

### Basic Usage (All Authors, All Years)
```bash
python qusoft_arxiv_scanner.py
```

### Filter by Specific Authors
Edit the `AUTHORS` list in the script:
```python
AUTHORS = ["Llorenç Escolà-Farràs", "Christian Schaffner"]
```

### Filter by Year
Edit the `STARTS_WITH` variable:
```python
STARTS_WITH = "25"    # 2025 papers
STARTS_WITH = "2510"  # October 2025 papers
```

## Output Files

- `qusoft_papers.xlsx` - Excel spreadsheet with all found papers
- `qusoft_firstpages_2025.pdf` - Annotated PDF first pages (filtered papers)

## Requirements

Install required packages:
```bash
pip install arxiv openpyxl PyMuPDF qrcode[pil] requests pillow
```

## Unicode Name Handling

The script uses intelligent search strategies to handle Unicode characters:

1. **Exact searches**: `au:"Llorenç Escolà-Farràs"`
2. **Fallback searches**: `Llorenc AND Escol` (for Unicode issues)
3. **Verification**: Confirms target author is actually present in results

## Cache Management

- Query results are cached in `cache/query_cache.json`
- PDF files are cached in `cache/downloaded_pdfs/`
- Delete cache files to force fresh searches

## Troubleshooting

### No papers found for Unicode names
The script automatically handles this with fallback searches.

### Portrait images not found
Place author images in `qusofters/portraits/` with normalized filenames.

### PDF generation fails
Install PyMuPDF: `pip install PyMuPDF`

## Migration from Old Scripts

This script replaces:
- `main_with_cache.py` (Excel generation)
- `make_qusoft_firstpages.py` (PDF generation)

All functionality is preserved while improving organization and adding better error handling.

To run the script, use the following command:

```bash
python main.py
```

## Requirements

- Python 3.x
- [List any other dependencies or libraries required]

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/cschaffner/qusoft-arxiv.git
    ```
2. Navigate to the project directory:
    ```bash
    cd arxiv
    ```
3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [List any resources, libraries, or contributors you want to acknowledge]
