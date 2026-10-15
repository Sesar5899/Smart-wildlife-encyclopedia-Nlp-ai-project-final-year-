"""Myanmar Biodiversity Portal ecosystem and protected-area catalogs.

Committed JSON files are offline import snapshots. On first startup they seed
SQLite; after that, member pages and Content Studio share the same live database
records. Running this module refreshes both snapshots and their SQLite catalogs
from the portal's public catalog and Next.js detail endpoints.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from crawler import PORTAL_BASE, discover_build_id, get_json, is_webp, normalized_stem
from myanmar import Key, contains_myanmar, normalize_mm


DATA_DIR = Path(__file__).resolve().parent / "data"
ECOSYSTEM_CACHE = DATA_DIR / "ecosystems.json"
PROTECTED_AREA_CACHE = DATA_DIR / "protected_areas.json"
ECOSYSTEM_IMAGE_DIR = Path(__file__).resolve().parent / "static" / "images" / "ecosystems"
PROTECTED_AREA_IMAGE_DIR = (
    Path(__file__).resolve().parent / "static" / "images" / "protected_areas"
)


PROTECTED_AREA_PRIMARY_REGIONS = {
    "alaungdaw_kathapa_national_park_protected": (
        "Sagaing", "စစ်ကိုင်းတိုင်းဒေသကြီး"
    ),
    "ayeyarwady_dolphin_protected_area_protected": (
        "Mandalay", "မန္တလေးတိုင်းဒေသကြီး"
    ),
    "bumhpabum_wildlife_sanctuary_protected": ("Kachin", "ကချင်ပြည်နယ်"),
    "eimawbon_national_park_protected": ("Kachin", "ကချင်ပြည်နယ်"),
    "gulf_of_mottama_protected": ("Mon", "မွန်ပြည်နယ်"),
    "hukaung_valley_extension_wildlife_sanctuary_protected": (
        "Kachin", "ကချင်ပြည်နယ်"
    ),
    "hukaung_valley_wildlife_sanctuary_protected": (
        "Kachin", "ကချင်ပြည်နယ်"
    ),
    "kahilu_wildlife_sanctuary_protected": ("Kayin", "ကရင်ပြည်နယ်"),
    "kyaikhtiyoe_wildlife_sanctuary_protected": ("Mon", "မွန်ပြည်နယ်"),
    "minwuntaung_wildlife_sanctuary_protected": (
        "Sagaing", "စစ်ကိုင်းတိုင်းဒေသကြီး"
    ),
    "panlaung_pyadalin_cave_wildlife_sanctuary_protected": (
        "Shan", "ရှမ်းပြည်နယ်"
    ),
    "panthitaung_national_park_protected": ("Kayah", "ကယားပြည်နယ်"),
    "rakhine_yoma_elephant_range_protected": ("Rakhine", "ရခိုင်ပြည်နယ်"),
    "say_taung_wildlife_sanctuary_protected": ("Kayin", "ကရင်ပြည်နယ်"),
    "shwe_u_daung_wildlife_sanctuary_protected": (
        "Mandalay", "မန္တလေးတိုင်းဒေသကြီး"
    ),
    "taninthayi_nature_reserve_protected": (
        "Tanintharyi", "တနင်္သာရီတိုင်းဒေသကြီး"
    ),
}


def normalize_protected_area_record(record: dict) -> dict:
    """Apply the member-facing status and primary-region conventions."""
    normalized = dict(record)
    if (
        normalized.get("status") == "Declared by Minister"
        or normalized.get("status_mm") == "ဝန်ကြီးက သတ်မှတ်ထားသည်"
    ):
        normalized["status"] = "Declared"
        normalized["status_mm"] = "သတ်မှတ်ပြီး"

    primary_region = PROTECTED_AREA_PRIMARY_REGIONS.get(normalized.get("slug"))
    if primary_region:
        normalized["in_state_region"], normalized["in_state_region_mm"] = primary_region
    else:
        # Keep any newly imported record to one display region until it can be
        # added to the researched primary-region list above.
        english_regions = [
            value.strip()
            for value in str(normalized.get("in_state_region") or "").split(",")
            if value.strip()
        ]
        burmese_regions = [
            value.strip()
            for value in str(normalized.get("in_state_region_mm") or "").split(",")
            if value.strip()
        ]
        if english_regions:
            normalized["in_state_region"] = english_regions[0]
        if burmese_regions:
            normalized["in_state_region_mm"] = burmese_regions[0]
    return normalized


def ecosystem_slug(name: str) -> str:
    r"""Match the portal's client-side ``name.replace(/\s/g, '_')`` route."""
    return re.sub(r"\s", "_", (name or "").strip())


def _fetch_catalog(endpoint: str, key_field: str) -> list[dict]:
    first = get_json(f"{PORTAL_BASE}/api/{endpoint}/all")
    records = list(first.get("feed") or [])
    expected = int(first.get("count") or len(records))
    if not records or not expected:
        raise RuntimeError(f"Portal {endpoint} catalog returned no records")

    page_size = len(records)
    for page in range(2, math.ceil(expected / page_size) + 1):
        payload = get_json(
            f"{PORTAL_BASE}/api/{endpoint}?page={page}&language=en"
        )
        records.extend(payload.get("feed") or [])

    unique = {}
    for record in records:
        key = record.get(key_field)
        if key:
            unique[key] = record
    if len(unique) != expected:
        raise RuntimeError(
            f"Portal {endpoint} catalog was incomplete: "
            f"received {len(unique)} of {expected} records"
        )
    return list(unique.values())


def _fetch_detail(build_id: str, section: str, slug: str, query_key: str) -> dict:
    encoded = quote(slug, safe="")
    payload = get_json(
        f"{PORTAL_BASE}/_next/data/{build_id}/en/{section}/{encoded}.json"
        f"?{query_key}={encoded}"
    )
    result = payload.get("pageProps", {}).get("result", {})
    if not result:
        raise RuntimeError(f"Portal returned no detail record for {section}/{slug}")
    return result


def _crawl_details(
    build_id: str,
    catalog: list[dict],
    *,
    section: str,
    slug_for,
    query_key: str,
    workers: int,
) -> list[dict]:
    records = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        futures = {}
        for item in catalog:
            slug = slug_for(item)
            futures[
                pool.submit(_fetch_detail, build_id, section, slug, query_key)
            ] = (item, slug)

        for number, future in enumerate(as_completed(futures), start=1):
            item, slug = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                raise RuntimeError(f"Failed to crawl {section}/{slug}") from exc
            record["slug"] = slug
            record["source_name"] = "Myanmar Biodiversity Portal"
            record["source_url"] = f"{PORTAL_BASE}/{section}/{quote(slug)}"
            records.append(record)
            print(f"[{number:02d}/{len(catalog):02d}] {record.get('name') or slug}")

    records.sort(key=lambda item: (item.get("name") or "").casefold())
    return records


def crawl_collections(*, workers: int = 4) -> tuple[list[dict], list[dict]]:
    build_id = discover_build_id()
    ecosystems_catalog = _fetch_catalog("ecosystems", "code")
    protected_catalog = _fetch_catalog("protectedareas", "id")

    ecosystems = _crawl_details(
        build_id,
        ecosystems_catalog,
        section="ecosystems",
        slug_for=lambda item: ecosystem_slug(item.get("name") or ""),
        query_key="name",
        workers=workers,
    )
    protected_areas = _crawl_details(
        build_id,
        protected_catalog,
        section="protected_areas",
        slug_for=lambda item: item.get("id") or "",
        query_key="id",
        workers=workers,
    )
    return ecosystems, protected_areas


def save_collections(ecosystems: list[dict], protected_areas: list[dict]) -> None:
    """Persist fresh importer snapshots and replace their SQLite catalogs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ECOSYSTEM_CACHE.write_text(
        json.dumps(ecosystems, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PROTECTED_AREA_CACHE.write_text(
        json.dumps(
            [normalize_protected_area_record(record) for record in protected_areas],
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    from db import init_db, replace_catalog_records
    init_db()
    replace_catalog_records("ecosystems", ecosystems)
    replace_catalog_records(
        "protected_areas",
        [normalize_protected_area_record(record) for record in protected_areas],
    )


def save_collection(kind: str, records: list[dict]) -> None:
    """Replace an environmental catalog in the application's SQLite database."""
    if kind not in {"ecosystems", "protected_areas"}:
        raise ValueError("Unknown collection kind")
    if kind == "protected_areas":
        records = [normalize_protected_area_record(record) for record in records]
    from db import replace_catalog_records
    replace_catalog_records(kind, records)


def save_collection_record(kind: str, record: dict, original_slug: str | None = None):
    """Create or update one SQLite record and return its stable slug."""
    slug = (record.get("slug") or "").strip()
    if not slug:
        raise ValueError("A slug is required")
    existing = (
        get_ecosystem(original_slug) if kind == "ecosystems"
        else get_protected_area(original_slug)
    ) if original_slug else None
    merged = dict(existing or {})
    merged.update(record)
    from db import upsert_catalog_record
    upsert_catalog_record(kind, merged, original_slug)
    return slug


def delete_collection_record(kind: str, slug: str) -> bool:
    from db import delete_catalog_record
    return delete_catalog_record(kind, slug)


def _source_image_names(record: dict, field: str) -> list[str]:
    return [
        value.strip()
        for value in str(record.get(field) or "").split(",")
        if value.strip()
    ]


def _image_index(source_dir: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in source_dir.glob("*.webp"):
        if path.name == "defaultImage.webp" or not is_webp(path.read_bytes()):
            continue
        index.setdefault(normalized_stem(path.name), []).append(path)
    return index


def _safe_image_stem(slug: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.()-]", "_", slug)


def _copy_record_images(
    records: list[dict],
    *,
    source_dir: Path,
    destination_dir: Path,
    source_field: str,
    public_segment: str,
    repository_segment: str,
) -> int:
    """Attach only photos explicitly listed on each portal record."""
    index = _image_index(source_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    attached = 0

    for record in records:
        matches = []
        seen = set()
        for source_name in _source_image_names(record, source_field):
            for candidate in index.get(normalized_stem(source_name), []):
                if candidate not in seen:
                    seen.add(candidate)
                    matches.append(candidate)
                    break

        local_urls = []
        source_urls = []
        stem = _safe_image_stem(record.get("slug") or "record")
        for position, source in enumerate(matches, start=1):
            suffix = "" if position == 1 else f"-{position}"
            filename = f"{stem}{suffix}.webp"
            destination = destination_dir / filename
            shutil.copy2(source, destination)
            local_urls.append(f"/static/images/{public_segment}/{filename}")
            source_urls.append(
                "https://raw.githubusercontent.com/Thibico/wcsimages/main/"
                f"public/assets/{repository_segment}/images/{source.name}"
            )

        record["image_url"] = local_urls[0] if local_urls else None
        record["image_urls"] = local_urls
        record["source_image_urls"] = source_urls
        if local_urls:
            attached += 1

    return attached


def attach_images_from_repository(
    ecosystems: list[dict], protected_areas: list[dict], repository: Path
) -> tuple[int, int]:
    """Copy verified WebP photos from a checkout of the portal image repository."""
    ecosystem_count = _copy_record_images(
        ecosystems,
        source_dir=repository / "public/assets/ecosystems/images",
        destination_dir=ECOSYSTEM_IMAGE_DIR,
        source_field="ecosystems_image",
        public_segment="ecosystems",
        repository_segment="ecosystems",
    )
    protected_count = _copy_record_images(
        protected_areas,
        source_dir=repository / "public/assets/protected_area/images",
        destination_dir=PROTECTED_AREA_IMAGE_DIR,
        source_field="protected_area_image",
        public_segment="protected_areas",
        repository_segment="protected_area",
    )
    return ecosystem_count, protected_count


# The upstream export serialises JavaScript's `undefined` and `null` into some
# fields as literal strings.  Seventeen protected areas carry
# ``"established_year": "undefined"``, which is truthy: left alone it renders
# as an "undefined" badge on the card, as a fact on the detail page, and as a
# founding year the chat would repeat.  These are missing values, so read them
# as missing.
_PLACEHOLDER_VALUES = {"undefined", "null", "nan", "-"}


def _clean_value(value):
    if isinstance(value, str) and value.strip().casefold() in _PLACEHOLDER_VALUES:
        return None
    return value


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [
        {field: _clean_value(value) for field, value in record.items()}
        if isinstance(record, dict) else record
        for record in payload
    ]


def load_ecosystems() -> list[dict]:
    from db import get_catalog_records, seed_catalog_records
    records, initialized = get_catalog_records("ecosystems")
    if not initialized:
        seed_catalog_records("ecosystems", _load(ECOSYSTEM_CACHE))
        records, _ = get_catalog_records("ecosystems")
    return records


def load_protected_areas() -> list[dict]:
    from db import get_catalog_records, seed_catalog_records
    records, initialized = get_catalog_records("protected_areas")
    if not initialized:
        seed_catalog_records(
            "protected_areas",
            [normalize_protected_area_record(record) for record in _load(PROTECTED_AREA_CACHE)],
        )
        records, _ = get_catalog_records("protected_areas")
    return [normalize_protected_area_record(record) for record in records]


# Compatibility for importer/tests that used to clear the JSON loader cache.
load_ecosystems.cache_clear = lambda: None
load_protected_areas.cache_clear = lambda: None


def get_ecosystem(slug: str) -> dict | None:
    return next((item for item in load_ecosystems() if item.get("slug") == slug), None)


def get_protected_area(slug: str) -> dict | None:
    return next(
        (item for item in load_protected_areas() if item.get("slug") == slug),
        None,
    )


# The fields a collection search reads.  Defined here so the member pages and
# the Content Studio cannot drift into searching different things.
SEARCH_FIELDS = {
    "ecosystems": (
        "name", "name_mm", "code", "description", "description_mm",
        "distribution", "distribution_mm", "in_biome", "in_biome_mm",
        "national_iucn_status",
    ),
    "protected_areas": (
        "name", "name_mm", "description", "description_mm", "designation",
        "designation_mm", "in_state_region", "in_state_region_mm",
        "status", "status_mm",
        "habitat_types", "natural_resources_biodiversity", "natural_resources_mm",
    ),
}


def searchable_text(record: dict, fields: tuple[str, ...]) -> str:
    values = [str(record.get(field) or "") for field in fields]
    return normalize_mm(" ".join(values)).casefold()


def filter_records(records: list[dict], query: str, fields: tuple[str, ...]) -> list[dict]:
    needle = normalize_mm(query or "").casefold().strip()
    if not needle:
        return list(records)
    return [record for record in records if needle in searchable_text(record, fields)]


_ENGLISH_WORDS = re.compile(r"[a-z0-9]+")


def _one_edit_away(left: str, right: str) -> bool:
    """Allow one insertion, deletion, substitution, or adjacent swap."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        changed = [index for index, (a, b) in enumerate(zip(left, right)) if a != b]
        if (
            len(changed) == 2
            and changed[1] == changed[0] + 1
            and left[changed[0]] == right[changed[1]]
            and left[changed[1]] == right[changed[0]]
        ):
            return True
    i = j = errors = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        errors += 1
        if errors > 1:
            return False
        if len(left) > len(right):
            i += 1
        elif len(right) > len(left):
            j += 1
        else:
            i += 1
            j += 1
    return errors + (i < len(left)) + (j < len(right)) == 1


def _myanmar_name_typo(query: str, name: str) -> bool:
    # Both catalogs use the same bounded Myanmar sound/mark rules.
    from db import _myanmar_typo_fragment
    return _myanmar_typo_fragment(query, name)


def _english_name_typo(query: str, name: str) -> bool:
    if contains_myanmar(query) or not re.fullmatch(r"[a-z0-9\s-]+", query):
        return False
    query_words = _ENGLISH_WORDS.findall(query)
    candidate_words = _ENGLISH_WORDS.findall(name.casefold())
    if not query_words or not candidate_words:
        return False
    query_text = " ".join(query_words)
    if len(query_text) < 5:
        return False
    width = len(query_words)
    return any(
        query_words[0][0] == candidate_words[start][0]
        and _one_edit_away(
            query_text, " ".join(candidate_words[start:start + width])
        )
        for start in range(len(candidate_words) - width + 1)
    )


def _catalog_names(record: dict) -> list[str]:
    """Search both stored names and the alternatives separated within them."""
    names = [str(record.get(field) or "") for field in ("name_mm", "name")]
    for name in names[:]:
        names.extend(part.strip() for part in re.split(r"[/၊]", name) if part.strip())
    return list(dict.fromkeys(name for name in names if name))


def _filter_named_catalog(records: list[dict], query: str, kind: str) -> list[dict]:
    """Rank either environmental catalog with the animal name matcher."""
    if not query or not query.strip():
        return list(records)
    needle = normalize_mm(query).casefold()
    from db import SEARCH_SCORE_THRESHOLD, _literal_contains, _name_score

    literal = [
        record for record in records
        if _literal_contains(
            needle, searchable_text(record, SEARCH_FIELDS[kind])
        )
    ]
    query_key = Key(needle)
    scored = []
    for index, record in enumerate(records):
        names = _catalog_names(record)
        score = max(
            (_name_score(query_key, needle, name) for name in names),
            default=0.0,
        )
        literal_name = any(
            _literal_contains(needle, normalize_mm(name).casefold())
            for name in names
        )
        scored.append((record, index, score, literal_name))

    def ranked(hits):
        return [record for record, _, _, _ in sorted(
            hits, key=lambda hit: (-hit[2], hit[1])
        )]

    # A Myanmar name hit is clear intent; English text hits remain available
    # behind English name hits for broader catalog browsing.
    if any(literal_name for _, _, _, literal_name in scored):
        if contains_myanmar(needle):
            return ranked([hit for hit in scored if hit[3]])
        literal_ids = {id(record) for record in literal}
        return ranked([
            (record, index, score if literal_name else 0.78, literal_name)
            for record, index, score, literal_name in scored
            if id(record) in literal_ids
        ])

    # As with animals, a complete phonetic/syllable name match outranks an
    # unrelated description that happens to contain the typed characters.
    phonetic = [
        hit for hit in scored if hit[2] >= 0.95
    ]
    if phonetic:
        return ranked(phonetic)

    typo = []
    for record, index, _, _ in scored:
        names = _catalog_names(record)
        if any(
            _myanmar_name_typo(needle, name) if contains_myanmar(needle)
            else _english_name_typo(needle, name)
            for name in names
        ):
            typo.append((record, index, 0.84, False))
    if typo:
        return ranked(typo)

    # Latin fuzzy scores use the same Key/similarity implementation as animals.
    # A literal article hit keeps its higher relevance than a weak name guess.
    literal_ids = {id(record) for record in literal}
    return ranked([
        (record, index, max(score, 0.78 if id(record) in literal_ids else 0.0), False)
        for record, index, score, _ in scored
        if score >= SEARCH_SCORE_THRESHOLD or id(record) in literal_ids
    ])


def filter_ecosystems(records: list[dict], query: str) -> list[dict]:
    return _filter_named_catalog(records, query, "ecosystems")


def filter_protected_areas(records: list[dict], query: str) -> list[dict]:
    return _filter_named_catalog(records, query, "protected_areas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images-from",
        type=Path,
        help="Attach photos from a local checkout of Thibico/wcsimages",
    )
    args = parser.parse_args()

    if args.images_from:
        ecosystem_records = load_ecosystems()
        protected_area_records = load_protected_areas()
        if not ecosystem_records or not protected_area_records:
            raise RuntimeError("Crawl the collection records before attaching images")
        ecosystem_photos, protected_photos = attach_images_from_repository(
            ecosystem_records, protected_area_records, args.images_from
        )
        print(
            f"Attached photos to {ecosystem_photos} ecosystems and "
            f"{protected_photos} protected areas."
        )
    else:
        ecosystem_records, protected_area_records = crawl_collections()
    save_collections(ecosystem_records, protected_area_records)
    print(
        f"Saved {len(ecosystem_records)} ecosystems and "
        f"{len(protected_area_records)} protected areas."
    )
