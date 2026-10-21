#!/usr/bin/env python3
"""Fetch portraits from the QuSoft people page into qusofters/portraits/.

Each person card on qusoft.org is matched to people.csv by the name on the card.
Portraits are saved as 'firstname_lastname.jpg' (black and white, at most 800 px, JPEG).

    python scripts/download_portraits.py            # add missing portraits, report changed photos
    python scripts/download_portraits.py --update   # also replace portraits whose photo changed on qusoft.org

The website's "no picture" placeholder is skipped, and so are images with a
generic file name (like 'Asset-1.png'), since it isn't clear who they show.
Check new files by eye before committing them.
"""

import argparse
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageOps, ImageStat

from qusoft.common import PersonMatcher, find_portrait, load_people, name_key, normalize_name, path

URL = "https://qusoft.org/qusoft-people/"
TITLES = re.compile(r"^((prof|dr|ir|drs|mr|ms|msc|bsc|em)\.?\s+)+", re.I)
PLACEHOLDER = re.compile(r"no-picture|^asset-\d+$", re.I)
MAX_PX = 800
CHANGED = 18  # mean grey-level difference (0-255) above which two photos count as different


def cards():
    """(name on card, original image URL) for every person on the people page."""
    html = requests.get(URL, timeout=30)
    html.raise_for_status()
    for item in BeautifulSoup(html.text, "html.parser").select(".jet-listing-grid__item"):
        texts = list(item.stripped_strings)
        src = next((i["src"] for i in item.find_all("img") if i.get("src") and not i["src"].startswith("data:")), None)
        if texts and src:
            # Images are served through a resizing CDN; take the original behind it.
            yield TITLES.sub("", texts[0]).strip(), "https://" + src.split("https://")[-1]


def match_person(card_name, people, matcher):
    """Match a card to people.csv; also allows a short first name ('Alex' for 'Alexander')."""
    hit = matcher(card_name)
    if hit:
        return hit
    first, *_, last = normalize_name(card_name).split() or [""]
    found = [n for n in people
             if normalize_name(n).split()[-1] == last
             and (normalize_name(n).split()[0].startswith(first) or first.startswith(normalize_name(n).split()[0]))]
    return found[0] if len(found) == 1 else None


def fetch(url):
    data = requests.get(url, timeout=60)
    data.raise_for_status()
    img = Image.open(io.BytesIO(data.content))
    img = ImageOps.grayscale(ImageOps.exif_transpose(img).convert("RGB"))  # portraits are black and white
    img.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    return img


def difference(a, b):
    small = [ImageOps.fit(i.convert("L"), (48, 48), Image.LANCZOS) for i in (a, b)]
    return ImageStat.Stat(ImageChops.difference(*small)).mean[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="replace portraits whose photo changed on qusoft.org")
    args = ap.parse_args()

    people = load_people()
    matcher = PersonMatcher(people)
    out_dir = path("paths", "portraits_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    added, changed, skipped, unknown, seen = [], [], [], [], set()
    for card_name, url in cards():
        person = match_person(card_name, people, matcher)
        if not person:
            unknown.append(card_name)
            continue
        seen.add(person)
        if PLACEHOLDER.search(Path(url).stem):
            if "no-picture" not in url:
                skipped.append(f"{person} ({Path(url).name})")
            continue
        current = find_portrait(person)
        if current and current.suffix.lower() == ".svg":
            current = None
        try:
            img = fetch(url)
        except Exception as e:
            print(f"  could not download {url}: {e}")
            continue
        target = out_dir / f"{name_key(person).replace(' ', '_').replace('.', '')}.jpg"
        if current:
            if difference(Image.open(current), img) < CHANGED:
                continue
            changed.append(person)
            if not args.update:
                continue
            if current != target:
                current.unlink()
        else:
            added.append(person)
        img.save(target, "JPEG", quality=88)

    print(f"Added {len(added)} portraits: {', '.join(added) or '-'}")
    verb = "Replaced" if args.update else "Photo changed on qusoft.org (use --update to replace)"
    print(f"{verb}: {len(changed)}: {', '.join(changed) or '-'}")
    if skipped:
        print(f"Skipped, unclear who the image shows: {', '.join(skipped)}")
    if unknown:
        print(f"On qusoft.org but not in people.csv: {', '.join(unknown)}")
    missing = sorted(n for n in people if not find_portrait(n))
    print(f"Still without a portrait: {len(missing)}")
    for n in missing:
        print(f"  {n}{'' if n in seen else ' (not on qusoft.org)'}")


if __name__ == "__main__":
    main()
