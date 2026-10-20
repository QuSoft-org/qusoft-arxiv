#!/usr/bin/env python3
"""Download portraits from the QuSoft people page into qusofters/portraits/.

Images are matched to people in people.csv by file name and saved as
'firstname_lastname.jpg'. Existing portraits are kept unless --overwrite is given.
Check new files by eye before committing them.

    python scripts/download_portraits.py
"""

import argparse
import sys
from difflib import get_close_matches
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from bs4 import BeautifulSoup

from qusoft.common import find_portrait, load_people, name_key, path

URL = "https://qusoft.org/qusoft-people/"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--overwrite", action="store_true", help="replace portraits that already exist")
    args = ap.parse_args()

    people = load_people()
    slugs = {name_key(n).replace(" ", "_"): n for n in people}
    out_dir = path("paths", "portraits_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    page = requests.get(URL, timeout=30)
    page.raise_for_status()
    sources = [img.get("src") for img in BeautifulSoup(page.text, "html.parser").find_all("img") if img.get("src")]
    print(f"Found {len(sources)} images on {URL}")

    saved = 0
    for src in sources:
        url = urljoin(URL, src)
        file = Path(urlparse(url).path)
        guess = name_key(file.stem.replace("-", " ").replace("_", " ")).replace(" ", "_")
        match = get_close_matches(guess, slugs, n=1, cutoff=0.7)
        if not match:
            continue
        person = slugs[match[0]]
        if find_portrait(person) and not args.overwrite:
            continue
        target = out_dir / f"{match[0]}{file.suffix.lower()}"
        try:
            target.write_bytes(requests.get(url, timeout=30).content)
            saved += 1
            print(f"  {person}: {target.name}")
        except requests.RequestException as e:
            print(f"  could not download {url}: {e}")

    missing = sorted(n for n in people if not find_portrait(n))
    print(f"Saved {saved} portraits. Still without a portrait: {len(missing)}")
    for n in missing:
        print(f"  {n}")


if __name__ == "__main__":
    main()
