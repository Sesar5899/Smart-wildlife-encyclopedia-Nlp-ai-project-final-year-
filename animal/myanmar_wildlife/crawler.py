"""Import real species records from the Myanmar Biodiversity Portal.

The portal is a Next.js site. Its catalog API provides the 82 species slugs and
the public ``_next/data`` endpoint provides the complete bilingual record for
each species. Images are stored in the public repository referenced by the
portal. Empty legacy JPG files and ``defaultImage.webp`` are never imported.
"""

from __future__ import annotations

import argparse
import json
import provenance
import re
import shutil
import sqlite3
import threading
import unicodedata
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from db import init_db
from myanmar_places import ecosystem_names_my, protected_area_names_my, region_names_my


PORTAL_BASE = "https://www.myanmarbiodiversity.org"
PORTAL_CATALOG = f"{PORTAL_BASE}/api/species/all"
IMAGE_REPOSITORY_API = (
    "https://api.github.com/repos/Thibico/wcsimages/contents/"
    "public/assets/species/images?per_page=1000"
)
SOURCE_NAME = "Myanmar Biodiversity Portal"
APP_DIR = Path(__file__).resolve().parent
IMAGE_DIR = APP_DIR / "static" / "images" / "species"
CACHE_PATH = APP_DIR / "data" / "myanmar_biodiversity_species.json"
USER_AGENT = (
    "MyanmarWildlifeEducationalImporter/1.0 "
    "(+https://www.myanmarbiodiversity.org/species)"
)
_thread_local = threading.local()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/html"})
        _thread_local.session = session
    return session


def get_json(url: str, *, timeout: int = 45) -> dict | list:
    response = http_session().get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def discover_build_id() -> str:
    response = http_session().get(f"{PORTAL_BASE}/species", timeout=45)
    response.raise_for_status()
    match = re.search(r'"buildId":"([^"]+)"', response.text)
    if not match:
        raise RuntimeError("Could not discover the portal's Next.js build ID")
    return match.group(1)


def fetch_catalog() -> list[dict]:
    payload = get_json(PORTAL_CATALOG)
    records = payload.get("feed", []) if isinstance(payload, dict) else []
    expected = payload.get("count", len(records)) if isinstance(payload, dict) else 0
    if not records or not expected:
        raise RuntimeError("Portal catalog returned no species")

    page_size = len(records)
    for page in range(2, math.ceil(expected / page_size) + 1):
        page_payload = get_json(f"{PORTAL_BASE}/api/species?page={page}&language=en")
        records.extend(page_payload.get("feed", []))

    deduplicated = {
        record["linked_name"]: record for record in records if record.get("linked_name")
    }
    records = list(deduplicated.values())
    if len(records) != expected:
        raise RuntimeError(
            f"Portal catalog was incomplete: received {len(records)} of {expected} records"
        )
    return records


def fetch_species_record(build_id: str, linked_name: str) -> dict:
    encoded = quote(linked_name, safe="")
    url = (
        f"{PORTAL_BASE}/_next/data/{build_id}/en/species/{encoded}.json"
        f"?linked_name={encoded}"
    )
    payload = get_json(url)
    record = payload.get("pageProps", {}).get("result", {})
    if not record or record.get("linked_name") != linked_name:
        raise RuntimeError(f"Invalid portal record returned for {linked_name}")
    return record


def crawl_records(*, workers: int = 4, limit: int | None = None) -> list[dict]:
    build_id = discover_build_id()
    catalog = fetch_catalog()
    if limit:
        catalog = catalog[:limit]

    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        futures = {
            pool.submit(fetch_species_record, build_id, item["linked_name"]): item
            for item in catalog
        }
        for number, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to crawl {item.get('linked_name', 'unknown species')}"
                ) from exc
            records.append(record)
            print(f"[{number:02d}/{len(catalog):02d}] {record.get('common_name')}")

    records.sort(key=lambda record: (record.get("common_name") or "").casefold())
    return records


def normalized_stem(value: str | None) -> str:
    if not value:
        return ""
    stem = Path(value).stem
    ascii_text = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.casefold())


def image_candidates(record: dict) -> list[str]:
    candidates = []
    for filename in (record.get("species_image") or "").split(","):
        if filename.strip():
            candidates.append(filename.strip())
    candidates.extend(
        value
        for value in (
            record.get("common_name"),
            record.get("scientific_name"),
            record.get("linked_name"),
        )
        if value
    )
    return candidates


def fetch_image_index() -> list[dict]:
    payload = get_json(IMAGE_REPOSITORY_API)
    return [
        item
        for item in payload
        if item.get("type") == "file"
        and item.get("name", "").casefold().endswith(".webp")
        and item.get("name") != "defaultImage.webp"
        and int(item.get("size") or 0) > 2048
        and item.get("download_url")
    ]


def resolve_image(record: dict, image_index: list[dict]) -> dict | None:
    by_stem: dict[str, list[dict]] = {}
    for image in image_index:
        by_stem.setdefault(normalized_stem(image["name"]), []).append(image)

    candidates = image_candidates(record)
    for candidate in candidates:
        exact = by_stem.get(normalized_stem(candidate))
        if exact:
            return max(exact, key=lambda item: int(item.get("size") or 0))

    # Some source filenames were renamed when the portal converted them to
    # WebP. Accept only a strong filename match to avoid showing the wrong animal.
    best_score = 0.0
    best_image = None
    for candidate in candidates:
        candidate_stem = normalized_stem(candidate)
        if not candidate_stem:
            continue
        for image in image_index:
            image_stem = normalized_stem(image["name"])
            score = SequenceMatcher(None, candidate_stem, image_stem).ratio()
            if min(len(candidate_stem), len(image_stem)) >= 8 and (
                candidate_stem in image_stem or image_stem in candidate_stem
            ):
                score = max(score, 0.9)
            if score > best_score:
                best_score = score
                best_image = image

    return best_image if best_score >= 0.86 else None


def is_webp(content: bytes) -> bool:
    return len(content) > 2048 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"


def download_species_images(records: list[dict], *, workers: int = 4) -> list[str]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_index = fetch_image_index()
    jobs = []
    missing = []

    for record in records:
        image = resolve_image(record, image_index)
        if image is None:
            record["_image_url"] = None
            record["_source_image_url"] = None
            missing.append(record.get("common_name") or record.get("linked_name"))
            continue
        filename = f"{record['linked_name']}.webp"
        destination = IMAGE_DIR / filename
        record["_image_url"] = f"/static/images/species/{filename}"
        record["_source_image_url"] = image["download_url"]
        jobs.append((record, image["download_url"], destination))

    def download(job: tuple[dict, str, Path]) -> None:
        _, url, destination = job
        if destination.exists() and is_webp(destination.read_bytes()):
            return
        response = http_session().get(url, timeout=60)
        response.raise_for_status()
        if not is_webp(response.content):
            raise RuntimeError(f"Rejected invalid or empty image: {url}")
        destination.write_bytes(response.content)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        futures = {pool.submit(download, job): job for job in jobs}
        for future in as_completed(futures):
            future.result()

    return missing


def first_name(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return re.split(r"\s*[,၊/]\s*", value, maxsplit=1)[0].strip() or fallback


def aliases_for(record: dict) -> list[str]:
    values = []
    for field in ("common_name_mm", "other_name_mm", "other_name"):
        raw = record.get(field) or ""
        values.extend(part.strip() for part in re.split(r"[,၊/]", raw) if part.strip())
    values.extend(
        value
        for value in (record.get("common_name"), record.get("scientific_name"))
        if value
    )
    return list(dict.fromkeys(values))


CATEGORY_DATA = {
    "Mammal": ("နို့တိုက်သတ္တဝါ", "Mammals", "မြန်မာနိုင်ငံရှိ နို့တိုက်သတ္တဝါများ", "mammal"),
    "Bird": ("ငှက်", "Birds", "မြန်မာနိုင်ငံရှိ ငှက်များ", "bird"),
    "Reptile": ("တွားသွားသတ္တဝါ", "Reptiles", "မြန်မာနိုင်ငံရှိ တွားသွားသတ္တဝါများ", "reptile"),
    "Unclassified": ("အမျိုးအစား မဖော်ပြထား", "Unclassified", "မူရင်း Portal တွင် class မဖော်ပြထားသော မျိုးစိတ်", "unknown"),
}


def import_records(records: list[dict], *, backup: bool = True) -> Path | None:
    """Atomically replace generated seed rows with crawled portal records."""
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

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM animal_aliases")
        conn.execute("DELETE FROM animals")
        conn.execute("DELETE FROM categories")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('animal_aliases', 'animals', 'categories')"
        )

        classes = [
            name
            for name in CATEGORY_DATA
            if any((r.get("species_class") or "Unclassified") == name for r in records)
        ]
        category_ids = {}
        for class_name in classes:
            category = CATEGORY_DATA[class_name]
            cursor = conn.execute(
                "INSERT INTO categories (name_my, name_en, description_my, icon) VALUES (?, ?, ?, ?)",
                category,
            )
            category_ids[class_name] = cursor.lastrowid

        for record in records:
            name_en = record.get("common_name") or record.get("scientific_name") or "Unknown"
            name_my = first_name(record.get("common_name_mm"), name_en)
            measurement = "\n".join(
                value
                for value in (
                    record.get("measurement_length_mm") or record.get("measurement_length"),
                    record.get("measurement_weight_mm") or record.get("measurement_weight"),
                )
                if value
            )
            source_url = f"{PORTAL_BASE}/species/{record['linked_name']}"
            cursor = conn.execute(
                """
                INSERT INTO animals (
                    name_my, name_en, scientific_name, category_id, habitat_my,
                    description_my, diet_my, conservation_status, image_url,
                    fun_facts_my, size_my, lifespan_my, region_my,
                    source_record_id, source_url, source_name, source_image_url,
                    linked_name, other_name, species_order, species_family,
                    global_iucn_status, population_trend, myanmar_population,
                    global_population, portal_data, crawled_at
                    , iucn_justification_my, physical_description_my,
                    distribution_my, behaviour_my, threats_my,
                    conservation_actions_my, conservation_needs_my, use_trade_my,
                    wild_population_my, protected_areas_my, ecosystems_my, kba_my
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    name_my,
                    name_en,
                    record.get("scientific_name"),
                    category_ids.get(record.get("species_class") or "Unclassified"),
                    record.get("habitat_ecology_mm") or record.get("habitat_ecology"),
                    record.get("physical_description"),
                    None,
                    record.get("national_iucn_status") or record.get("global_iucn_status"),
                    record.get("_image_url"),
                    None,
                    measurement or None,
                    None,
                    region_names_my(record.get("in_state_region")),
                    record.get("id"),
                    source_url,
                    SOURCE_NAME,
                    record.get("_source_image_url"),
                    record.get("linked_name"),
                    record.get("other_name") or record.get("other_name_mm"),
                    record.get("species_order"),
                    record.get("species_family"),
                    record.get("global_iucn_status"),
                    record.get("population_trend_mm") or record.get("population_trend"),
                    record.get("mm_population_mm") or record.get("mm_population"),
                    record.get("global_population_mm") or record.get("global_population"),
                    json.dumps(
                        {key: value for key, value in record.items() if not key.startswith("_")},
                        ensure_ascii=False,
                    ),
                    crawled_at,
                    record.get("justification_mm") or record.get("justification"),
                    record.get("physical_description"),
                    record.get("distribution_mm") or record.get("distribution"),
                    record.get("behaviour"),
                    record.get("threats_to_survival_mm")
                    or record.get("threats_to_survival"),
                    record.get("conservation_research_undertaken_mm")
                    or record.get("conservation_research_undertaken"),
                    record.get("conservation_research_needed_mm")
                    or record.get("conservation_research_needed"),
                    record.get("use_and_trade_mm") or record.get("use_and_trade"),
                    record.get("wild_population_mm") or record.get("wild_population"),
                    protected_area_names_my(record.get("in_protected_area")),
                    ecosystem_names_my(record.get("in_ecosytems")),
                    protected_area_names_my(record.get("in_kba")),
                ),
            )
            animal_id = cursor.lastrowid
            imported = dict(conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone())
            verified = provenance.portal_field_sources(imported)
            if verified:
                conn.execute(
                    "UPDATE animals SET field_sources = ? WHERE id = ?",
                    (json.dumps(verified, ensure_ascii=False), animal_id),
                )
            for alias in aliases_for(record):
                if alias != name_my:
                    conn.execute(
                        "INSERT INTO animal_aliases (animal_id, alias_my) VALUES (?, ?)",
                        (animal_id, alias),
                    )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return backup_path


def save_cache(records: list[dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": f"{PORTAL_BASE}/species",
        "source_name": SOURCE_NAME,
        "crawled_at": utc_now(),
        "count": len(records),
        "records": records,
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cache() -> list[dict]:
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not records:
        raise RuntimeError(f"No records found in {CACHE_PATH}")
    declared = payload.get("count")
    if declared is not None and declared != len(records):
        raise RuntimeError(
            f"{CACHE_PATH} declares {declared} records but holds {len(records)}. "
            "Re-run: python crawler.py"
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4, help="Concurrent requests (maximum 6)")
    parser.add_argument("--limit", type=int, help="Import only the first N records (development only)")
    parser.add_argument("--from-cache", action="store_true", help="Rebuild SQLite from the saved crawl")
    parser.add_argument("--no-images", action="store_true", help="Do not download portal photographs")
    args = parser.parse_args()

    if args.from_cache:
        records = load_cache()
        missing = [r.get("common_name") for r in records if not r.get("_image_url")]
    else:
        records = crawl_records(workers=args.workers, limit=args.limit)
        missing = [] if args.no_images else download_species_images(records, workers=args.workers)
        if args.no_images:
            for record in records:
                record["_image_url"] = None
                record["_source_image_url"] = None
        save_cache(records)

    backup_path = import_records(records)
    print(
        json.dumps(
            {
                "imported": len(records),
                "images": len(records) - len(missing),
                "missing_images": missing,
                "database": str(Config.DATABASE),
                "backup": str(backup_path) if backup_path else None,
                "cache": str(CACHE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
