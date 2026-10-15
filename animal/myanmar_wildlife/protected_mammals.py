"""Import the 77 totally protected mammals of the Protected Wildlife List (2020).

The Myanmar Biodiversity Portal that ``crawler.py`` reads publishes only 82
species, and fewer than a third of this legal list appears there.  The rest —
every whale, dolphin, pangolin, otter and linsang on the schedule — has to come
from somewhere else, so this importer assembles each record from the public
sources in ``species_sources`` and records which one every field came from.

Unlike ``crawler.py`` this importer is **additive**: it never deletes a row.  A
species already imported from the portal keeps its portal text and portal
photograph and is only marked as protected; a species that is missing is
created.  Running it twice changes nothing the second time.
"""

from __future__ import annotations

import argparse
import json
import provenance
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from config import Config
from db import init_db
from species_sources import (
    DESCRIPTION_LIMIT,
    english_names,
    EN_WIKI,
    MY_WIKI,
    article_images,
    assign_sections,
    choose_photograph,
    commons_title,
    credit_line,
    fetch_image_info,
    fetch_iucn_statuses,
    fetch_taxonomy,
    fetch_wikipedia,
    is_webp,
    licence_of,
    myanmar_names,
    normalize_scientific,
    photograph_score,
    save_webp,
    slugify,
    split_sections,
    trim,
    utc_now,
)

APP_DIR = Path(__file__).resolve().parent
LIST_PATH = APP_DIR / "data" / "totally_protected_mammals_2020.json"
CACHE_PATH = APP_DIR / "data" / "protected_mammals_2020_crawl.json"
IMAGE_DIR = APP_DIR / "static" / "images" / "species"

# The list is a legal instrument, so its wording is stored verbatim rather than
# recomputed per row.
BASIS_DIRECT = "ကာကွယ်ထားသည့် တောရိုင်းတိရစ္ဆာန်များစာရင်းတွင် မျိုးစိတ်အလိုက် တိုက်ရိုက် ပါဝင်သည်။"
PROTECTION_MY = "အပြည့်အဝ ကာကွယ်ထားသော မျိုးစိတ်"
PROTECTION_EN = "Totally protected"

MAMMAL_CATEGORY = ("နို့တိုက်သတ္တဝါ", "Mammals", "မြန်မာနိုင်ငံရှိ နို့တိုက်သတ္တဝါများ", "mammal")

# Marks the rows this importer owns, so a re-run refreshes its own records
# while still only marking the ones the portal crawler published.
RECORD_PREFIX = "protected_mammal_2020_"

def crawl(species: list[dict]) -> list[dict]:
    """Assemble one complete record per listed species."""
    scientific = [item["scientific_name"] for item in species]
    print(f"Resolving {len(scientific)} species on English Wikipedia …")
    english = fetch_wikipedia(EN_WIKI, scientific, langlink="my")

    burmese_titles = sorted(
        {page["langlink"] for page in english.values() if page.get("langlink")}
    )
    print(f"Reading {len(burmese_titles)} Burmese Wikipedia articles …")
    burmese = fetch_wikipedia(MY_WIKI, burmese_titles) if burmese_titles else {}

    qids = [page["qid"] for page in english.values() if page.get("qid")]
    print(f"Reading IUCN categories for {len(qids)} Wikidata items …")
    statuses = fetch_iucn_statuses(qids)

    files = [page["image_file"] for page in english.values() if page.get("image_file")]
    print(f"Reading licences for {len(files)} Wikipedia lead images …")
    lead_images = fetch_image_info(files)

    records = []
    for item in species:
        name = item["scientific_name"]
        page = english.get(name)
        if not page:
            print(f"  ! no English Wikipedia article for {name}")
            records.append({**item, "_unresolved": True})
            continue

        lead, raw_sections = split_sections(page["extract"])
        sections = assign_sections(raw_sections)
        my_page = burmese.get(page["langlink"]) if page.get("langlink") else None
        my_lead, my_raw = split_sections(my_page["extract"]) if my_page else ("", [])
        my_sections = assign_sections(my_raw)

        physical = sections.get("physical")
        description = my_lead or lead
        description_language = "my" if my_lead else "en"
        if not my_lead and physical:
            description = f"{lead}\n\n{physical}"
        description = trim(description, DESCRIPTION_LIMIT)

        taxonomy = fetch_taxonomy(name)

        preferred = None
        if page.get("image_file"):
            title = commons_title(page["image_file"])
            info = lead_images.get(title)
            if info:
                preferred = (title, info)
        candidates = []
        if not preferred or photograph_score(*preferred, name, page["title"]) is None:
            candidates = article_images(EN_WIKI, page["title"])
            if my_page:
                candidates += article_images(MY_WIKI, my_page["title"])
            candidates = list(dict.fromkeys(candidates))
        chosen = choose_photograph(name, page["title"], preferred, candidates)
        licence = licence_of(*chosen) if chosen else None
        substituted = bool(chosen) and (not preferred or chosen[0] != preferred[0])

        record = {
            **item,
            "wikidata_qid": page.get("qid"),
            "en_title": page["title"],
            "en_url": f"https://en.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}",
            "my_title": my_page["title"] if my_page else None,
            "my_url": (
                f"https://my.wikipedia.org/wiki/{quote(my_page['title'].replace(' ', '_'))}"
                if my_page
                else None
            ),
            "description": description,
            "description_language": description_language,
            "habitat": my_sections.get("habitat") or sections.get("habitat"),
            "diet": my_sections.get("diet") or sections.get("diet"),
            "distribution": my_sections.get("distribution") or sections.get("distribution"),
            "threats": sections.get("threats"),
            "conservation": sections.get("conservation"),
            "use_and_trade": sections.get("use_trade"),
            "behaviour": my_sections.get("behaviour") or sections.get("behaviour"),
            "physical_description": physical,
            "global_iucn_status": statuses.get(page.get("qid")),
            "species_order": (taxonomy.get("order") or None),
            "species_family": (taxonomy.get("family") or None),
            "gbif": taxonomy,
            "image": licence,
            "image_file": chosen[0] if chosen else None,
            "lead_image_rejected": substituted,
        }
        records.append(record)
        print(
            f"  {item['no']:>2}. {item['name_en']:<45} "
            f"{'my' if description_language == 'my' else 'en'}  "
            f"{record['global_iucn_status'] or '--'}  "
            f"{'NO PHOTO' if not licence else ('photo*' if substituted else 'photo')}"
        )
    return records


# --------------------------------------------------------------------------
# Photographs
# --------------------------------------------------------------------------


def download_images(records: list[dict], *, force: bool = False) -> list[str]:
    """Fetch each Commons photograph and store it beside the portal's own."""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for record in records:
        if record.get("_unresolved"):
            continue
        image = record.get("image")
        if not image or not image.get("download_url"):
            # No file on Commons could be shown to be a photograph of this
            # species.  The record is published without one; the page already
            # says so, which is the honest answer.
            record["_image_url"] = None
            missing.append(record["name_en"])
            continue
        filename = f"{record['linked_name']}.webp"
        destination = IMAGE_DIR / filename
        record["_image_url"] = f"/static/images/species/{filename}"
        if not force and destination.exists() and is_webp(destination.read_bytes()):
            continue
        size = save_webp(image["download_url"], destination)
        print(f"  photo {filename} ({size // 1024} KB)")
    return missing


def source_list(record: dict) -> list[dict]:
    sources = []
    if record.get("my_url"):
        sources.append({"label": "မြန်မာ ဝီကီပီးဒီးယား", "url": record["my_url"]})
    if record.get("en_url"):
        sources.append({"label": "English Wikipedia", "url": record["en_url"]})
    if record.get("wikidata_qid"):
        sources.append(
            {
                "label": "Wikidata",
                "url": f"https://www.wikidata.org/wiki/{record['wikidata_qid']}",
            }
        )
    if (record.get("gbif") or {}).get("gbif_key"):
        sources.append(
            {
                "label": "GBIF Backbone Taxonomy",
                "url": f"https://www.gbif.org/species/{record['gbif']['gbif_key']}",
            }
        )
    if (record.get("image") or {}).get("file_page"):
        sources.append({"label": "ဓာတ်ပုံ — Wikimedia Commons", "url": record["image"]["file_page"]})
    return sources


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------


# Written for every row this importer owns, in the order ``values`` builds them.
RECORD_COLUMNS = (
    "name_my", "name_en", "scientific_name", "category_id", "habitat_my",
    "description_my", "diet_my", "image_url", "region_my",
    "source_record_id", "source_url", "source_name", "source_image_url",
    "linked_name", "other_name", "species_order", "species_family",
    "global_iucn_status", "portal_data", "crawled_at", "source_urls",
    "protection_status_my", "protection_status_en", "protection_law_my",
    "protection_basis_my", "image_credit", "taxon_rank",
    "iucn_justification_my", "physical_description_my", "distribution_my",
    "behaviour_my", "threats_my", "conservation_actions_my",
    "conservation_needs_my", "use_trade_my", "wild_population_my",
    "protected_areas_my", "ecosystems_my", "kba_my",
)


def record_id(record: dict) -> str:
    return f"{RECORD_PREFIX}{slugify(record['scientific_name']).lower()}"


def mammal_category_id(conn: sqlite3.Connection) -> int:
    name_my, name_en = MAMMAL_CATEGORY[0], MAMMAL_CATEGORY[1]
    row = conn.execute(
        "SELECT id FROM categories WHERE name_en = ? OR name_my = ?", (name_en, name_my)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO categories (name_my, name_en, description_my, icon) VALUES (?, ?, ?, ?)",
        MAMMAL_CATEGORY,
    )
    return cursor.lastrowid


def existing_by_scientific_name(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM animals").fetchall()
    index = {}
    for row in rows:
        key = normalize_scientific(row["scientific_name"])
        if key:
            index.setdefault(key, row)
    return index


def merge_aliases(conn: sqlite3.Connection, animal_id: int, aliases: list[str], name_my: str):
    held = {
        row["alias_my"]
        for row in conn.execute(
            "SELECT alias_my FROM animal_aliases WHERE animal_id = ?", (animal_id,)
        )
    }
    added = 0
    for alias in aliases:
        if alias and alias != name_my and alias not in held:
            conn.execute(
                "INSERT INTO animal_aliases (animal_id, alias_my) VALUES (?, ?)",
                (animal_id, alias),
            )
            held.add(alias)
            added += 1
    return added


def import_records(records: list[dict], catalogue: dict, *, backup: bool = True):
    database = Path(Config.DATABASE)
    backup_path = None
    if backup and database.exists() and database.stat().st_size:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = database.with_name(f"{database.name}.bak-{stamp}")
        shutil.copy2(database, backup_path)

    init_db()
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    crawled_at = utc_now()
    law = catalogue["legal_basis_my"]
    created, marked, skipped = [], [], []

    try:
        conn.execute("BEGIN IMMEDIATE")
        category_id = mammal_category_id(conn)
        existing = existing_by_scientific_name(conn)

        for record in records:
            if record.get("_unresolved"):
                skipped.append(record["name_en"])
                continue

            my_names = myanmar_names(record["name_my"])
            en_names = english_names(record["name_en"])
            aliases = [
                *my_names,
                *en_names,
                record["scientific_name"],
            ]
            row = existing.get(normalize_scientific(record["scientific_name"]))

            owned = row is not None and (row["source_record_id"] or "").startswith(RECORD_PREFIX)
            if row is not None and not owned:
                # Already published from the Myanmar Biodiversity Portal.  Its
                # own text and photograph stay untouched; only the legal status
                # this list establishes is written, plus the list's names as
                # searchable aliases.
                conn.execute(
                    """UPDATE animals
                       SET protection_status_my = ?, protection_status_en = ?,
                           protection_law_my = ?, protection_basis_my = ?
                       WHERE id = ?""",
                    (PROTECTION_MY, PROTECTION_EN, law, BASIS_DIRECT, row["id"]),
                )
                merge_aliases(conn, row["id"], aliases, row["name_my"])
                marked.append(record["name_en"])
                continue

            name_my = my_names[0]
            name_en = en_names[0]
            record["linked_name"] = f"{slugify(record['scientific_name'])}_{slugify(name_en)}"
            portal = {
                "distribution": record.get("distribution"),
                "threats_to_survival": record.get("threats"),
                "conservation_research_undertaken": record.get("conservation"),
                "use_and_trade": record.get("use_and_trade"),
                "behaviour": record.get("behaviour"),
                "physical_description": record.get("physical_description"),
                "description_language": record.get("description_language"),
                "protected_list_no": record["no"],
                "protection_level_en": catalogue["protection_level_en"],
                "protection_level_my": catalogue["protection_level_my"],
                "legal_basis_en": catalogue["legal_basis_en"],
                "legal_basis_my": law,
                "wikidata_qid": record.get("wikidata_qid"),
                "gbif": record.get("gbif"),
                "en_wikipedia_title": record.get("en_title"),
                "my_wikipedia_title": record.get("my_title"),
            }
            sources = source_list(record)
            values = (
                name_my,
                name_en,
                record["scientific_name"],
                category_id,
                record.get("habitat"),
                record.get("description"),
                record.get("diet"),
                record.get("_image_url"),
                None,
                record_id(record),
                sources[0]["url"] if sources else None,
                sources[0]["label"] if sources else None,
                (record.get("image") or {}).get("download_url"),
                record["linked_name"],
                record["name_en"] if len(en_names) > 1 else None,
                record.get("species_order"),
                record.get("species_family"),
                record.get("global_iucn_status"),
                json.dumps(portal, ensure_ascii=False),
                crawled_at,
                json.dumps(sources, ensure_ascii=False),
                PROTECTION_MY,
                PROTECTION_EN,
                law,
                BASIS_DIRECT,
                credit_line(record.get("image")),
                "species",
                None,
                record.get("physical_description"),
                record.get("distribution"),
                record.get("behaviour"),
                record.get("threats"),
                record.get("conservation"),
                None,
                record.get("use_and_trade"),
                None,
                None,
                None,
                None,
            )
            if owned:
                conn.execute(
                    f"UPDATE animals SET {', '.join(f'{column} = ?' for column in RECORD_COLUMNS)}"
                    " WHERE id = ?",
                    (*values, row["id"]),
                )
                animal_id = row["id"]
                marked.append(record["name_en"])
            else:
                conn.execute(
                    f"INSERT INTO animals ({', '.join(RECORD_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in RECORD_COLUMNS)})",
                    values,
                )
                animal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                created.append(record["name_en"])
            imported = dict(conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone())
            verified = provenance.imported_field_sources(imported, record)
            conn.execute(
                "UPDATE animals SET field_sources = ? WHERE id = ?",
                (json.dumps(verified, ensure_ascii=False), animal_id),
            )
            merge_aliases(conn, animal_id, aliases, name_my)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"created": created, "marked": marked, "skipped": skipped, "backup": backup_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cache", action="store_true", help="Reuse the saved crawl")
    parser.add_argument("--no-images", action="store_true", help="Do not download photographs")
    parser.add_argument(
        "--refresh-images", action="store_true", help="Re-fetch photographs already on disk"
    )
    parser.add_argument("--limit", type=int, help="Import only the first N species")
    args = parser.parse_args()

    catalogue = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    species = catalogue["species"][: args.limit] if args.limit else catalogue["species"]

    if args.from_cache:
        records = json.loads(CACHE_PATH.read_text(encoding="utf-8"))["records"]
        if args.limit:
            records = records[: args.limit]
    else:
        records = crawl(species)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {"crawled_at": utc_now(), "count": len(records), "records": records},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    for record in records:
        if not record.get("_unresolved"):
            record.setdefault(
                "linked_name",
                f"{slugify(record['scientific_name'])}_{slugify(english_names(record['name_en'])[0])}",
            )

    missing_photos = (
        [] if args.no_images else download_images(records, force=args.refresh_images)
    )
    result = import_records(records, catalogue)
    print(
        json.dumps(
            {
                "listed": len(records),
                "created": len(result["created"]),
                "updated_or_marked_protected": len(result["marked"]),
                "unresolved": result["skipped"],
                "missing_photographs": missing_photos,
                "database": str(Config.DATABASE),
                "backup": str(result["backup"]) if result["backup"] else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
