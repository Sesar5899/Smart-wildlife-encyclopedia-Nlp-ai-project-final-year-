"""Import Notification 690/2020 — the protected birds of Myanmar.

This schedule is shaped differently from the mammal list.  Nineteen of its
forty-eight entries name a species; the other twenty-nine protect a whole
**family, order or genus** — every owl, every stork, every pitta.  Two things
follow from that.

First, a record here is not always a species, so ``animals.taxon_rank`` says
what it is and a group record carries no IUCN category, because a family does
not have one.  A group record shows a photograph only when the file itself says
which member species it depicts, and the caption says so: a picture captioned as
the family would be passing one bird off as a hundred others.

Second, protecting a family protects the birds already in this encyclopedia that
belong to it.  After publishing the schedule the importer walks every bird in the
catalog and assigns the level of the **most specific** entry that covers it —
species beats genus beats family beats order, and where two entries are equally
specific the stricter level wins.  So the Green Peafowl is totally protected by
its own entry rather than normally protected as a member of Phasianidae, and the
Slender-billed Vulture is totally protected as an Accipitridae without being
named anywhere in the notification.

Like ``protected_mammals.py`` this importer is additive and idempotent: it never
deletes a row, it refreshes only the rows it owns, and portal records keep their
own text and photographs.
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
    fetch_wikipedia,
    is_webp,
    licence_of,
    taxon_photograph,
    myanmar_names,
    myanmar_species_names,
    normalize_scientific,
    save_webp,
    slugify,
    split_sections,
    trim,
    utc_now,
)

APP_DIR = Path(__file__).resolve().parent
LIST_PATH = APP_DIR / "data" / "protected_birds_2020.json"
CACHE_PATH = APP_DIR / "data" / "protected_birds_2020_crawl.json"
IMAGE_DIR = APP_DIR / "static" / "images" / "species"

BIRD_CATEGORY = ("ငှက်", "Birds", "မြန်မာနိုင်ငံရှိ ငှက်များ", "bird")
RECORD_PREFIX = "protected_bird_2020_"

# How narrowly an entry names a bird.  The narrowest entry that covers a species
# decides its level, which is how a species entry overrides its own family's.
RANK_SPECIFICITY = {"species": 4, "genus": 3, "subfamily": 2, "family": 1, "order": 0}
LEVEL_STRICTNESS = {"totally": 3, "normally": 2, "seasonally": 1}

BASIS_DIRECT = "အမိန့်ကြော်ငြာစာ စာရင်းတွင် မျိုးစိတ်အလိုက် တိုက်ရိုက် ပါဝင်သည်။"
RANK_MY = {
    "species": "မျိုးစိတ်",
    "genus": "မျိုးရင်း (Genus)",
    "subfamily": "မျိုးရင်းခွဲ (Subfamily)",
    "family": "မိသားစု (Family)",
    "order": "မျိုးစဉ် (Order)",
}


def entry_key(entry: dict) -> str:
    taxon = entry["taxa"][0]["name"]
    return f"{RECORD_PREFIX}{entry['level']}_{entry['no']:02d}_{slugify(taxon).lower()}"


def group_basis(entry: dict) -> str:
    taxon = entry["taxa"][0]
    return (
        f"{entry['name_my']} ({taxon['name']} — {RANK_MY[taxon['rank']]}) "
        "အုပ်စုဝင်အဖြစ် စာရင်းတွင် ပါဝင်သည်။"
    )


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
    """Assemble one record per schedule entry, species or group alike."""
    titles = [entry["taxa"][0]["name"] for entry in entries]
    print(f"Resolving {len(titles)} taxa on English Wikipedia …")
    english = fetch_wikipedia(EN_WIKI, titles, langlink="my")

    burmese_titles = sorted(
        {page["langlink"] for page in english.values() if page.get("langlink")}
    )
    print(f"Reading {len(burmese_titles)} Burmese Wikipedia articles …")
    burmese = fetch_wikipedia(MY_WIKI, burmese_titles) if burmese_titles else {}

    species_qids = [
        english[entry["taxa"][0]["name"]]["qid"]
        for entry in entries
        if entry["taxa"][0]["rank"] == "species"
        and english.get(entry["taxa"][0]["name"], {}).get("qid")
    ]
    print(f"Reading IUCN categories for {len(species_qids)} species …")
    statuses = fetch_iucn_statuses(species_qids)

    files = [page["image_file"] for page in english.values() if page.get("image_file")]
    print(f"Reading licences for {len(files)} Wikipedia lead images …")
    lead_images = fetch_image_info(files)

    members = catalogue_species_names()
    records = []
    verified: dict[str, dict] = {}
    for entry in entries:
        taxon = entry["taxa"][0]
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
        description = trim(description, DESCRIPTION_LIMIT)

        gbif = fetch_taxon(name, taxon["rank"])
        taxon = {**taxon, "family": gbif.get("family"), "order": gbif.get("order")}
        chosen, example = taxon_photograph(taxon, page, lead_images, my_page, verified, members)

        records.append(
            {
                **entry,
                "taxon_name": name,
                "taxon_rank": taxon["rank"],
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
                "global_iucn_status": (
                    statuses.get(page.get("qid")) if taxon["rank"] == "species" else None
                ),
                "species_order": gbif.get("order") or (name if taxon["rank"] == "order" else None),
                "species_family": gbif.get("family")
                or (name if taxon["rank"] == "family" else None),
                "gbif": gbif,
                "image": licence_of(*chosen) if chosen else None,
                "image_example_species": example or None,
            }
        )
        print(
            f"  {entry['level'][:4]:>4} {entry['no']:>2}. {entry['name_en'][:34]:36}"
            f" {taxon['rank'][:8]:9} {'my' if description_language == 'my' else 'en'}"
            f"  {'photo' if chosen else 'no photo'}"
            f"{'  (example: ' + example + ')' if example else ''}"
        )
    return records


# --------------------------------------------------------------------------
# Photographs
# --------------------------------------------------------------------------


def download_images(records: list[dict], *, force: bool = False) -> list[str]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for record in records:
        if record.get("_unresolved"):
            continue
        image = record.get("image")
        if not image or not image.get("download_url"):
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


def image_credit(record: dict) -> str | None:
    """The caption, which never claims the picture is of the group itself."""
    line = credit_line(record.get("image"))
    if not line or (record.get("taxon_rank") or "species") == "species":
        return line
    example = record.get("image_example_species")
    if example:
        return f"ဤအုပ်စုမှ ဥပမာ — {example} · {line}"
    # A montage of several members: examples, but not one that can be named.
    return f"ဤအုပ်စုမှ ဥပမာများ · {line}"


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
        sources.append(
            {"label": "ဓာတ်ပုံ — Wikimedia Commons", "url": record["image"]["file_page"]}
        )
    return sources


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

RECORD_COLUMNS = (
    "name_my", "name_en", "scientific_name", "category_id", "habitat_my",
    "description_my", "diet_my", "image_url", "source_record_id", "source_url",
    "source_name", "source_image_url", "linked_name", "other_name",
    "species_order", "species_family", "global_iucn_status", "portal_data",
    "crawled_at", "source_urls", "protection_status_my", "protection_status_en",
    "protection_law_my", "protection_basis_my", "image_credit", "taxon_rank",
    "iucn_justification_my", "physical_description_my", "distribution_my",
    "behaviour_my", "threats_my", "conservation_actions_my",
    "conservation_needs_my", "use_trade_my", "wild_population_my",
    "protected_areas_my", "ecosystems_my", "kba_my",
)


def bird_category_id(conn: sqlite3.Connection) -> int:
    name_my, name_en = BIRD_CATEGORY[0], BIRD_CATEGORY[1]
    row = conn.execute(
        "SELECT id FROM categories WHERE name_en = ? OR name_my = ?", (name_en, name_my)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO categories (name_my, name_en, description_my, icon) VALUES (?, ?, ?, ?)",
        BIRD_CATEGORY,
    )
    return cursor.lastrowid


def merge_aliases(conn, animal_id: int, aliases: list[str], name_my: str) -> None:
    held = {
        row["alias_my"]
        for row in conn.execute(
            "SELECT alias_my FROM animal_aliases WHERE animal_id = ?", (animal_id,)
        )
    }
    for alias in aliases:
        if alias and alias != name_my and alias not in held:
            conn.execute(
                "INSERT INTO animal_aliases (animal_id, alias_my) VALUES (?, ?)",
                (animal_id, alias),
            )
            held.add(alias)


def covering_entry(animal: sqlite3.Row, entries: list[dict]) -> tuple[dict, dict] | None:
    """The narrowest, then strictest, schedule entry that covers this bird."""
    scientific = normalize_scientific(animal["scientific_name"])
    genus = scientific.split(" ")[0] if scientific else ""
    family = (animal["species_family"] or "").casefold()
    order = (animal["species_order"] or "").casefold()

    best = None
    for entry in entries:
        for taxon in entry["taxa"]:
            rank, name = taxon["rank"], taxon["name"].casefold()
            covers = (
                (rank == "species" and normalize_scientific(taxon["name"]) == scientific)
                or (rank == "genus" and name == genus)
                or (rank == "family" and name == family)
                or (rank == "order" and name == order)
            )
            if not covers:
                continue
            score = (RANK_SPECIFICITY[rank], LEVEL_STRICTNESS[entry["level"]])
            if best is None or score > best[0]:
                best = (score, entry, taxon)
    return (best[1], best[2]) if best else None


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
    levels = catalogue["levels"]
    created, updated, marked, skipped = [], [], [], []

    try:
        conn.execute("BEGIN IMMEDIATE")
        category_id = bird_category_id(conn)
        owned = {
            row["source_record_id"]: row
            for row in conn.execute(
                "SELECT * FROM animals WHERE source_record_id LIKE ?", (RECORD_PREFIX + "%",)
            )
        }
        by_scientific = {}
        for row in conn.execute("SELECT * FROM animals"):
            key = normalize_scientific(row["scientific_name"])
            if key and not (row["source_record_id"] or "").startswith(RECORD_PREFIX):
                by_scientific.setdefault(key, row)

        for record in records:
            if record.get("_unresolved"):
                skipped.append(record["name_en"])
                continue

            level = levels[record["level"]]
            taxon = record["taxa"][0]
            my_names = myanmar_names(record["name_my"])
            en_names = english_names(record["name_en"])
            aliases = [
                *my_names,
                *en_names,
                *(item["name"] for item in record["taxa"]),
                record["scientific_raw"],
            ]
            key = entry_key(record)
            existing = by_scientific.get(normalize_scientific(taxon["name"]))

            if taxon["rank"] == "species" and existing is not None:
                # Already published from the portal.  Its text and photograph
                # stay; only the legal status this notification establishes is
                # written, plus the schedule's names as searchable aliases.
                conn.execute(
                    """UPDATE animals
                       SET protection_status_my = ?, protection_status_en = ?,
                           protection_law_my = ?, protection_basis_my = ?
                       WHERE id = ?""",
                    (level["my"], level["en"], law, BASIS_DIRECT, existing["id"]),
                )
                merge_aliases(conn, existing["id"], aliases, existing["name_my"])
                marked.append(record["name_en"])
                continue

            name_my = my_names[0]
            name_en = en_names[0]
            portal = {
                "distribution": record.get("distribution"),
                "threats_to_survival": record.get("threats"),
                "conservation_research_undertaken": record.get("conservation"),
                "use_and_trade": record.get("use_and_trade"),
                "behaviour": record.get("behaviour"),
                "physical_description": record.get("physical_description"),
                "description_language": record.get("description_language"),
                "notification": catalogue["list_name_en"],
                "protected_list_no": record["no"],
                "protection_level_key": record["level"],
                "protection_level_en": level["en"],
                "protection_level_my": level["my"],
                "protection_schedule_my": level["heading_my"],
                "legal_basis_en": catalogue["legal_basis_en"],
                "legal_basis_my": law,
                "scientific_raw": record["scientific_raw"],
                "taxa": record["taxa"],
                "taxon_rank": taxon["rank"],
                "taxon_rank_my": RANK_MY[taxon["rank"]],
                "wikidata_qid": record.get("wikidata_qid"),
                "gbif": record.get("gbif"),
                "en_wikipedia_title": record.get("en_title"),
                "my_wikipedia_title": record.get("my_title"),
                "image_example_species": record.get("image_example_species"),
                "source_note": record.get("source_note"),
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
                key,
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
                level["my"],
                level["en"],
                law,
                BASIS_DIRECT if taxon["rank"] == "species" else group_basis(record),
                image_credit(record),
                taxon["rank"],
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
            row = owned.get(key)
            if row is not None:
                conn.execute(
                    f"UPDATE animals SET {', '.join(f'{c} = ?' for c in RECORD_COLUMNS)}"
                    " WHERE id = ?",
                    (*values, row["id"]),
                )
                animal_id = row["id"]
                updated.append(record["name_en"])
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

        inherited = apply_family_protection(conn, catalogue, category_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "created": created,
        "updated": updated,
        "marked": marked,
        "skipped": skipped,
        "inherited": inherited,
        "backup": backup_path,
    }


def apply_family_protection(conn, catalogue: dict, category_id: int) -> list[dict]:
    """Give every bird in the catalog the level of the entry that covers it.

    A species entry beats the family it belongs to, so the Green Peafowl stays
    totally protected rather than being demoted to Phasianidae's level.
    """
    entries = catalogue["entries"]
    levels = catalogue["levels"]
    law = catalogue["legal_basis_my"]
    applied = []

    birds = conn.execute(
        """SELECT * FROM animals
           WHERE category_id = ?
             AND (taxon_rank IS NULL OR taxon_rank = 'species')""",
        (category_id,),
    ).fetchall()

    for bird in birds:
        found = covering_entry(bird, entries)
        if not found:
            continue
        entry, taxon = found
        level = levels[entry["level"]]
        basis = BASIS_DIRECT if taxon["rank"] == "species" else group_basis(entry)
        if (
            bird["protection_status_en"] == level["en"]
            and bird["protection_basis_my"] == basis
        ):
            continue
        conn.execute(
            """UPDATE animals
               SET protection_status_my = ?, protection_status_en = ?,
                   protection_law_my = ?, protection_basis_my = ?
               WHERE id = ?""",
            (level["my"], level["en"], law, basis, bird["id"]),
        )
        applied.append(
            {
                "name_en": bird["name_en"],
                "level": level["en"],
                "via": f"{taxon['name']} ({taxon['rank']})",
            }
        )
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cache", action="store_true", help="Reuse the saved crawl")
    parser.add_argument("--no-images", action="store_true", help="Do not download photographs")
    parser.add_argument(
        "--refresh-images", action="store_true", help="Re-fetch photographs already on disk"
    )
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
            taxon = record["taxa"][0]["name"]
            record.setdefault(
                "linked_name",
                f"{slugify(taxon)}_{slugify(english_names(record['name_en'])[0])}",
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
                "refreshed": len(result["updated"]),
                "already_present_now_marked": result["marked"],
                "protected_by_their_family_or_order": result["inherited"],
                "unresolved": result["skipped"],
                "records_without_a_photograph": missing_photos,
                "database": str(Config.DATABASE),
                "backup": str(result["backup"]) if result["backup"] else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
