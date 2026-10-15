"""Replace six taxonomically misleading animal covers in the current database.

The raw crawl snapshots are left intact. This migration changes only the live
animal records and only while they still point to the known wrong photo.
"""

import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

from PIL import Image


DB_PATH = Path(__file__).with_name("wildlife.db")

# animal id: (scientific name, old Commons file, replacement file, credit)
# A missing replacement removes the misleading photograph. Commons currently
# has no photograph identified to species level for Muntiacus putaoensis.
CORRECTIONS = {
    146: (
        "Milvus migrans",
        "Shikra_(Accipiter_badius)_in_Hyderabad_W2_IMG_8968.jpg",
        "Black_Kite_(50965138971).jpg",
        "Mike Prince · CC BY 2.0 · Wikimedia Commons",
    ),
    162: (
        "Acridotheres tristis",
        "Sturnus_vulgaris_vulgaris_2.jpg",
        "Common_myna,_(Acridotheres_tristis).jpg",
        "Hobbyfotowiki · CC0 · Wikimedia Commons",
    ),
    165: (
        "Sphenocichla roberti",
        "Bar-winged_Wren-Babbler_-_Eaglenest_-_India_FJ0A8141_(33475375613).jpg",
        "SphenocichlaRobertiGodwinAusten.jpg",
        "Sphenocichla roberti illustration · Wikimedia Commons",
    ),
    180: (
        "Lanius schach",
        "Red-backed_shrike.jpg",
        "Long-tailed_shrike-Lanius_schach.jpg",
        "Anagha devi · CC BY-SA 4.0 · Wikimedia Commons",
    ),
    183: (
        "Muntiacus putaoensis",
        "Muntjac_Deer_Barking.webm",
        None,
        None,
    ),
    194: (
        "Rhinoceros sondaicus",
        "One_horned_Rhino.jpg",
        "Rhinoceros_sondaicus_in_London_Zoo.jpg",
        "T. Dixon · public domain · Wikimedia Commons",
    ),
}


def commons_urls(filename):
    digest = hashlib.md5(filename.encode("utf-8")).hexdigest()
    encoded = quote(filename, safe="()_,.-")
    image_url = (
        "https://upload.wikimedia.org/wikipedia/commons/"
        f"{digest[0]}/{digest[:2]}/{encoded}"
    )
    page_url = f"https://commons.wikimedia.org/wiki/File:{encoded}"
    return image_url, page_url


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    changed = []
    try:
        with conn:
            for animal_id, (scientific, old_file, new_file, credit) in CORRECTIONS.items():
                row = conn.execute(
                    "SELECT scientific_name, source_image_url, source_urls "
                    "FROM animals WHERE id = ?",
                    (animal_id,),
                ).fetchone()
                if row is None or row["scientific_name"] != scientific:
                    raise ValueError(f"Animal {animal_id} no longer matches {scientific}")
                if old_file not in unquote(row["source_image_url"] or ""):
                    # A later editor may already have replaced this image.
                    continue

                sources = json.loads(row["source_urls"] or "[]")
                sources = [
                    source for source in sources
                    if old_file not in source.get("url", "")
                ]
                image_url, page_url = commons_urls(new_file) if new_file else (None, None)
                if page_url:
                    sources.append({"label": "ဓာတ်ပုံ — Wikimedia Commons", "url": page_url})
                conn.execute(
                    "UPDATE animals SET image_url = ?, source_image_url = ?, "
                    "image_credit = ?, source_urls = ? WHERE id = ?",
                    (
                        image_url, image_url, credit,
                        json.dumps(sources, ensure_ascii=False), animal_id,
                    ),
                )
                changed.append(animal_id)
    finally:
        conn.close()
    print(f"Corrected photo sources for animal ids: {changed}")


def cache_images():
    """Store verified replacement files locally so covers work without hotlinks."""
    destination_dir = Path(__file__).with_name("static") / "images" / "species"
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cached = []
    try:
        for animal_id, (scientific, _, new_file, _) in CORRECTIONS.items():
            if not new_file:
                continue
            remote_url, _ = commons_urls(new_file)
            row = conn.execute(
                "SELECT scientific_name, source_image_url FROM animals WHERE id = ?",
                (animal_id,),
            ).fetchone()
            if row is None or row["scientific_name"] != scientific:
                raise ValueError(f"Animal {animal_id} no longer matches {scientific}")
            if row["source_image_url"] != remote_url:
                raise ValueError(f"Animal {animal_id} has a different source image")

            request = Request(remote_url, headers={"User-Agent": "MyanmarWildlife/1.0 (species photo correction)"})
            with urlopen(request, timeout=30) as response:
                content = response.read()
            with Image.open(io.BytesIO(content)) as image:
                image.thumbnail((1440, 1440))
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGB")
                filename = f"verified_species_{animal_id}.webp"
                destination = destination_dir / filename
                image.save(destination, "WEBP", quality=85, method=6)
            with conn:
                conn.execute(
                    "UPDATE animals SET image_url = ? WHERE id = ? AND source_image_url = ?",
                    (f"/static/images/species/{filename}", animal_id, remote_url),
                )
            cached.append(animal_id)
    finally:
        conn.close()
    print(f"Cached verified local covers for animal ids: {cached}")


if __name__ == "__main__":
    if "--cache-images" in sys.argv:
        cache_images()
    else:
        main()
