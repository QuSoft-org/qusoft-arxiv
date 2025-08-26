import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
from difflib import get_close_matches

# URL of the people page
URL = "https://qusoft.org/qusoft-people/"

# Output directory for images
OUTDIR = "qusofters/portraits"
os.makedirs(OUTDIR, exist_ok=True)

# Read names from Excel (first column)
EXCEL_PATH = "24-04-22-QuSoftDB.xlsx"
names_df = pd.read_excel(EXCEL_PATH, header=None)
names = names_df.iloc[:, 0].dropna().tolist()
def normalize_name(name):
    return name.strip().lower().replace(" ", "_")
normalized_names = [normalize_name(n) for n in names]

# Download the HTML
response = requests.get(URL)
soup = BeautifulSoup(response.text, "html.parser")

# Find all image tags

# Find all image tags
img_tags = soup.find_all("img")

# Collect all image sources
image_srcs = [img.get("src") for img in img_tags if img.get("src")]

print(f"Found {len(image_srcs)} images.")



# Download all images and rename using fuzzy matching to Excel names
for src in image_srcs:
    img_url = urljoin(URL, src)
    orig_fname = os.path.basename(urlparse(img_url).path)
    # Remove extension and normalize
    orig_base = os.path.splitext(orig_fname)[0].lower().replace(" ", "_")
    # Fuzzy match to normalized names
    match = get_close_matches(orig_base, normalized_names, n=1, cutoff=0.7)
    if match:
        fname = f"{match[0]}{os.path.splitext(orig_fname)[1]}"
    else:
        fname = orig_fname
    out_path = os.path.join(OUTDIR, fname)
    try:
        img_data = requests.get(img_url).content
        with open(out_path, "wb") as f:
            f.write(img_data)
        print(f"Downloaded {img_url} -> {out_path}")
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")

print("Done.")
