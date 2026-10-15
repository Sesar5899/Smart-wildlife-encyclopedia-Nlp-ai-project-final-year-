"""Add Myanmar name variants, and the taxa they name that the catalog lacks.

One animal carries several Myanmar names — the clouded leopard is အင်းကျား,
သစ်တောကျား and ကျားတိမ်; the sun bear is ခွေးဝံ and ဝက်ဝံငယ် — and a reader
searching one of them should find the record whatever name they know it by.
Every variant in ``data/myanmar_name_variants.json`` is stored as an alias.

Some rows name a taxon the encyclopedia does not hold yet. A few are species
(the sambar, the wild boar, the Popa langur); most are the everyday **group**
words — ဖျံ for otters, ရှဉ့် for squirrels, ကြံ့ for rhinoceroses — which name a
genus or a family rather than one animal. Those are published the same way
``protected_birds.py`` publishes its family entries: with ``taxon_rank`` set, no
IUCN category, and a photograph only when the file names the member it depicts.

The importer is additive and idempotent. It never renames a record: an existing
Myanmar name stays the record's name and the list's variants join it as aliases.
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
    EN_WIKI,
    MY_WIKI,
    assign_sections,
    credit_line,
    english_names,
    fetch_image_info,
    fetch_iucn_statuses,
    fetch_taxon,
    fetch_taxonomy,
    fetch_wikipedia,
    is_webp,
    licence_of,
    myanmar_species_names,
    normalize_scientific,
    save_webp,
    slugify,
    split_sections,
    taxon_photograph,
    trim,
    utc_now,
)

APP_DIR = Path(__file__).resolve().parent
LIST_PATH = APP_DIR / "data" / "myanmar_name_variants.json"
CACHE_PATH = APP_DIR / "data" / "myanmar_name_variants_crawl.json"
IMAGE_DIR = APP_DIR / "static" / "images" / "species"
RECORD_PREFIX = "name_variant_"

CATEGORIES = {
    "Mammalia": ("နို့တိုက်သတ္တဝါ", "Mammals", "မြန်မာနိုင်ငံရှိ နို့တိုက်သတ္တဝါများ", "mammal"),
    "Aves": ("ငှက်", "Birds", "မြန်မာနိုင်ငံရှိ ငှက်များ", "bird"),
    "Reptilia": ("တွားသွားသတ္တဝါ", "Reptiles", "မြန်မာနိုင်ငံရှိ တွားသွားသတ္တဝါများ", "reptile"),
}
RANK_MY = {
    "species": "မျိုးစိတ်",
    "genus": "မျိုးရင်း (Genus)",
    "subfamily": "မျိုးရင်းခွဲ (Subfamily)",
    "family": "မိသားစု (Family)",
    "order": "မျိုးစဉ် (Order)",
}

RECORD_COLUMNS = (
    "name_my", "name_en", "scientific_name", "category_id", "habitat_my",
    "description_my", "diet_my", "image_url", "source_record_id", "source_url",
    "source_name", "source_image_url", "linked_name", "other_name",
    "species_order", "species_family", "global_iucn_status", "portal_data",
    "crawled_at", "source_urls", "image_credit", "taxon_rank",
)


def record_key(taxon: dict) -> str:
    return f"{RECORD_PREFIX}{slugify(taxon['name']).lower()}"


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------


def catalogue_species_names() -> frozenset[str]:
    """Species this encyclopedia already publishes, plus the official schedules.

    Together these are the animals a Myanmar reader is likely to care about, and
    a group record's example photograph is chosen from them where one exists.
    """
    conn = sqlite3.connect(Config.DATABASE)
    try:
        names = {
            normalize_scientific(row[0])
            for row in conn.execute(
                "SELECT scientific_name FROM animals "
                "WHERE scientific_name IS NOT NULL "
                "AND (taxon_rank IS NULL OR taxon_rank = 'species')"
            )
        }
    finally:
        conn.close()
    return frozenset(names | myanmar_species_names()) - {""}


def crawl(entries: list[dict]) -> list[dict]:
    titles = [entry["taxon"]["name"] for entry in entries]
    print(f"Resolving {len(titles)} taxa on English Wikipedia …")
    english = fetch_wikipedia(EN_WIKI, titles, langlink="my")

    burmese_titles = sorted(
        {page["langlink"] for page in english.values() if page.get("langlink")}
    )
    print(f"Reading {len(burmese_titles)} Burmese Wikipedia articles …")
    burmese = fetch_wikipedia(MY_WIKI, burmese_titles) if burmese_titles else {}

    qids = [
        english[entry["taxon"]["name"]]["qid"]
        for entry in entries
        if entry["taxon"]["rank"] == "species"
        and english.get(entry["taxon"]["name"], {}).get("qid")
    ]
    print(f"Reading IUCN categories for {len(qids)} species …")
    statuses = fetch_iucn_statuses(qids)

    files = [page["image_file"] for page in english.values() if page.get("image_file")]
    print(f"Reading licences for {len(files)} Wikipedia lead images …")
    lead_images = fetch_image_info(files)

    members = catalogue_species_names()
    records = []
    verified: dict[str, dict] = {}
    for entry in entries:
        taxon = entry["taxon"]
        name = taxon["name"]
        page = english.get(name)
        if not page:
            print(f"  ! no English Wikipedia article for {name}")
            records.append({**entry, "_unresolved": True})
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

        gbif = fetch_taxon(name, taxon["rank"])
        taxon = {**taxon, "family": gbif.get("family"), "order": gbif.get("order")}
        chosen, example = taxon_photograph(taxon, page, lead_images, my_page, verified, members)

        records.append(
            {
                **entry,
                "taxon": taxon,
                "wikidata_qid": page.get("qid"),
                "en_title": page["title"],
                "en_url": f"https://en.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}",
                "my_title": my_page["title"] if my_page else None,
                "my_url": (
                    f"https://my.wikipedia.org/wiki/{quote(my_page['title'].replace(' ', '_'))}"
                    if my_page
                    else None
                ),
                "description": trim(description, DESCRIPTION_LIMIT),
                "description_language": description_language,
                "habitat": my_sections.get("habitat") or sections.get("habitat"),
                "diet": my_sections.get("diet") or sections.get("diet"),
                "distribution": my_sections.get("distribution") or sections.get("distribution"),
                "threats": sections.get("threats"),
                "conservation": sections.get("conservation"),
                "use_and_trade": sections.get("use_trade"),
                "behaviour": my_sections.get("behaviour") or sections.get("behaviour"),
                "physical_description": physical,
                "global_iucn_status": (
                    statuses.get(page.get("qid")) if taxon["rank"] == "species" else None
                ),
                "gbif": gbif,
                "image": licence_of(*chosen) if chosen else None,
                "image_example_species": example or None,
            }
        )
        print(
            f"  {entry['names_en'][0][:30]:32} {taxon['rank'][:9]:10}"
            f" {'my' if description_language == 'my' else 'en'}"
            f"  {'photo' if chosen else 'no photo'}"
            f"{'  (example: ' + example + ')' if example else ''}"
        )
    return records


def download_images(records: list[dict], *, force: bool = False) -> list[str]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for record in records:
        if record.get("_unresolved"):
            continue
        image = record.get("image")
        if not image or not image.get("download_url"):
            record["_image_url"] = None
            missing.append(record["names_en"][0])
            continue
        filename = f"{record['linked_name']}.webp"
        destination = IMAGE_DIR / filename
        record["_image_url"] = f"/static/images/species/{filename}"
        if not force and destination.exists() and is_webp(destination.read_bytes()):
            continue
        size = save_webp(image["download_url"], destination)
        print(f"  photo {filename} ({size // 1024} KB)")
    return missing


def image_credit(record: dict) -> str | None:
    line = credit_line(record.get("image"))
    if not line or record["taxon"]["rank"] == "species":
        return line
    example = record.get("image_example_species")
    if example:
        return f"ဤအုပ်စုမှ ဥပမာ — {example} · {line}"
    return f"ဤအုပ်စုမှ ဥပမာများ · {line}"


def source_list(record: dict) -> list[dict]:
    sources = []
    if record.get("my_url"):
        sources.append({"label": "မြန်မာ ဝီကီပီးဒီးယား", "url": record["my_url"]})
    if record.get("en_url"):
        sources.append({"label": "English Wikipedia", "url": record["en_url"]})
    if record.get("wikidata_qid"):
        sources.append(
            {"label": "Wikidata", "url": f"https://www.wikidata.org/wiki/{record['wikidata_qid']}"}
        )
    if (record.get("gbif") or {}).get("gbif_key"):
        sources.append(
            {
                "label": "GBIF Backbone Taxonomy",
                "url": f"https://www.gbif.org/species/{record['gbif']['gbif_key']}",
            }
        )
    if (record.get("image") or {}).get("file_page"):
        sources.append(
            {"label": "ဓာတ်ပုံ — Wikimedia Commons", "url": record["image"]["file_page"]}
        )
    return sources


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------


def resolve_classes(records: list[dict]) -> None:
    """Fill in the taxonomic class each record's category comes from.

    GBIF answers a subfamily out of a contributed checklist that often omits the
    class — Lutrinae comes back knowing only that it is a Mustelidae — so the
    parent family or order is asked instead.  Resolved before the database
    transaction opens, so no network call happens inside it.
    """
    for record in records:
        if record.get("_unresolved"):
            continue
        gbif = record.get("gbif") or {}
        class_name = gbif.get("class_name")
        if not class_name:
            parent = gbif.get("family") or gbif.get("order")
            if parent:
                class_name = (fetch_taxonomy(parent) or {}).get("class_name")
        record["_class"] = class_name


def category_id_for(conn: sqlite3.Connection, class_name: str | None) -> int | None:
    category = CATEGORIES.get(class_name or "")
    if not category:
        return None
    row = conn.execute(
        "SELECT id FROM categories WHERE name_en = ? OR name_my = ?", (category[1], category[0])
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO categories (name_my, name_en, description_my, icon) VALUES (?, ?, ?, ?)",
        category,
    )
    return cursor.lastrowid


def merge_aliases(conn, animal_id: int, aliases: list[str], name_my: str) -> int:
    held = {
        row["alias_my"]
        for row in conn.execute(
            "SELECT alias_my FROM animal_aliases WHERE animal_id = ?", (animal_id,)
        )
    }
    added = 0
    for alias in aliases:
        alias = alias.strip().rstrip("*").strip()
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
    created, aliased, skipped, uncategorised = [], [], [], []

    try:
        conn.execute("BEGIN IMMEDIATE")
        owned = {
            row["source_record_id"]: row
            for row in conn.execute(
                "SELECT * FROM animals WHERE source_record_id LIKE ?", (RECORD_PREFIX + "%",)
            )
        }
        # Rows this importer owns are refreshed below, not treated as records
        # published elsewhere that may only receive aliases.
        by_scientific, by_taxon = {}, {}
        for row in conn.execute("SELECT * FROM animals"):
            if (row["source_record_id"] or "").startswith(RECORD_PREFIX):
                continue
            key = normalize_scientific(row["scientific_name"])
            if key and (row["taxon_rank"] or "species") == "species":
                by_scientific.setdefault(key, row)
            if (row["taxon_rank"] or "species") != "species":
                by_taxon.setdefault(row["scientific_name"], row)

        for record in records:
            if record.get("_unresolved"):
                skipped.append(record["names_en"][0])
                continue
            taxon = record["taxon"]
            aliases = [*record["names_my"], *record["names_en"], taxon["name"]]

            existing = (
                by_scientific.get(normalize_scientific(taxon["name"]))
                if taxon["rank"] == "species"
                else by_taxon.get(taxon["name"])
            )
            if existing is not None:
                # The record keeps the Myanmar name it already publishes; the
                # list's variants join it as aliases rather than replacing it.
                added = merge_aliases(conn, existing["id"], aliases, existing["name_my"])
                if added:
                    aliased.append({"name": existing["name_my"], "aliases_added": added})
                continue

            category_id = category_id_for(conn, record.get("_class"))
            if category_id is None:
                uncategorised.append(taxon["name"])

            name_my = record["names_my"][0]
            name_en = record["names_en"][0]
            portal = {
                "distribution": record.get("distribution"),
                "threats_to_survival": record.get("threats"),
                "conservation_research_undertaken": record.get("conservation"),
                "use_and_trade": record.get("use_and_trade"),
                "behaviour": record.get("behaviour"),
                "physical_description": record.get("physical_description"),
                "description_language": record.get("description_language"),
                "name_variants_my": record["names_my"],
                "taxon_rank": taxon["rank"],
                "taxon_rank_my": RANK_MY[taxon["rank"]],
                "scientific_raw": taxon["name"],
                "wikidata_qid": record.get("wikidata_qid"),
                "gbif": record.get("gbif"),
                "en_wikipedia_title": record.get("en_title"),
                "my_wikipedia_title": record.get("my_title"),
                "image_example_species": record.get("image_example_species"),
                "list_name_my": catalogue["list_name_my"],
            }
            sources = source_list(record)
            values = (
                name_my,
                name_en,
                taxon["name"],
                category_id,
                record.get("habitat"),
                record.get("description"),
                record.get("diet"),
                record.get("_image_url"),
                record_key(taxon),
                sources[0]["url"] if sources else None,
                sources[0]["label"] if sources else None,
                (record.get("image") or {}).get("download_url"),
                record["linked_name"],
                " / ".join(record["names_en"][1:]) or None,
                (record.get("gbif") or {}).get("order"),
                (record.get("gbif") or {}).get("family"),
                record.get("global_iucn_status"),
                json.dumps(portal, ensure_ascii=False),
                crawled_at,
                json.dumps(sources, ensure_ascii=False),
                image_credit(record),
                taxon["rank"],
            )
            row = owned.get(record_key(taxon))
            if row is not None:
                conn.execute(
                    f"UPDATE animals SET {', '.join(f'{c} = ?' for c in RECORD_COLUMNS)}"
                    " WHERE id = ?",
                    (*values, row["id"]),
                )
                animal_id = row["id"]
            else:
                conn.execute(
                    f"INSERT INTO animals ({', '.join(RECORD_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in RECORD_COLUMNS)})",
                    values,
                )
                animal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                created.append(f"{name_my} ({taxon['name']})")
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

    return {
        "created": created,
        "aliased": aliased,
        "skipped": skipped,
        "uncategorised": uncategorised,
        "backup": backup_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cache", action="store_true", help="Reuse the saved crawl")
    parser.add_argument("--no-images", action="store_true", help="Do not download photographs")
    parser.add_argument("--refresh-images", action="store_true", help="Re-fetch photographs")
    parser.add_argument("--limit", type=int, help="Import only the first N entries")
    args = parser.parse_args()

    catalogue = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    entries = catalogue["entries"][: args.limit] if args.limit else catalogue["entries"]

    if args.from_cache:
        records = json.loads(CACHE_PATH.read_text(encoding="utf-8"))["records"]
        if args.limit:
            records = records[: args.limit]
    else:
        records = crawl(entries)
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
                f"{slugify(record['taxon']['name'])}_{slugify(english_names(record['names_en'][0])[0])}",
            )

    resolve_classes(records)
    missing = [] if args.no_images else download_images(records, force=args.refresh_images)
    result = import_records(records, catalogue)
    print(
        json.dumps(
            {
                "listed": len(records),
                "new_records_created": result["created"],
                "existing_records_given_new_aliases": len(result["aliased"]),
                "aliases_added": sum(item["aliases_added"] for item in result["aliased"]),
                "records_without_a_photograph": missing,
                "unresolved": result["skipped"],
                "no_category_from_gbif": result["uncategorised"],
                "database": str(Config.DATABASE),
                "backup": str(result["backup"]) if result["backup"] else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
