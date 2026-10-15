"""Verified field-level provenance for published animal records.

The portal snapshot proves only values that still match its imported fields.
Other source links require an editor to assign them explicitly.
"""

import json
from functools import lru_cache
from pathlib import Path


FIELD_LABELS = {
    "name_my": "မြန်မာအမည်", "name_en": "အင်္ဂလိပ်အမည်",
    "scientific_name": "သိပ္ပံအမည်", "habitat_my": "နေထိုင်ရာ",
    "description_my": "အကျဉ်းချုပ်", "physical_description_my": "ရုပ်သွင်ပြင်",
    "diet_my": "အစာစားနည်း", "conservation_status": "မြန်မာ IUCN အဆင့်",
    "fun_facts_my": "ထူးခြားအချက်များ", "size_my": "အရွယ်အစား",
    "lifespan_my": "သက်တမ်း", "region_my": "တွေ့ရှိရသော ဒေသ",
    "species_order": "Order", "species_family": "Family",
    "global_iucn_status": "ကမ္ဘာလုံးဆိုင်ရာ IUCN အဆင့်",
    "population_trend": "တွေ့ရှိမှု အခြေအနေ",
    "myanmar_population": "မြန်မာနိုင်ငံ အကောင်ရေ",
    "global_population": "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ",
    "protection_status_my": "ကာကွယ်မှုအဆင့် (မြန်မာ)",
    "protection_status_en": "ကာကွယ်မှုအဆင့် (English)",
    "protection_law_my": "ဥပဒေ / စာရင်း ကိုးကား",
    "protection_basis_my": "ကာကွယ်ရသည့် အကြောင်းရင်း",
    "iucn_justification_my": "IUCN အကဲဖြတ် အကြောင်းပြချက်",
    "distribution_my": "ဖြန့်ကျက်တည်ရှိမှု",
    "behaviour_my": "အနေအထိုင်နှင့် အပြုအမူ",
    "threats_my": "ရှင်သန်ရေး ခြိမ်းခြောက်မှုများ",
    "conservation_actions_my": "ထိန်းသိမ်းရေး လုပ်ဆောင်ချက်များ",
    "conservation_needs_my": "ထိန်းသိမ်းရေး လိုအပ်ချက်များ",
    "use_trade_my": "အသုံးပြုမှုနှင့် ကုန်သွယ်မှု",
    "wild_population_my": "တောရိုင်း အကောင်ရေ",
    "protected_areas_my": "ကာကွယ်ထိန်းသိမ်းနယ်မြေများ",
    "ecosystems_my": "ဆက်စပ် ဂေဟစနစ်များ",
    "kba_my": "အဓိက ဇီဝမျိုးစုံမျိုးကွဲ နယ်မြေများ",
}

# Only direct copies from the saved portal response are eligible for automatic
# attribution. Derived text, manual additions and translations are left open.
PORTAL_FIELDS = {
    "name_en": ("common_name",),
    "scientific_name": ("scientific_name",),
    "habitat_my": ("habitat_ecology_mm", "habitat_ecology"),
    "description_my": ("physical_description",),
    "physical_description_my": ("physical_description",),
    "conservation_status": ("national_iucn_status", "global_iucn_status"),
    "species_order": ("species_order",),
    "species_family": ("species_family",),
    "global_iucn_status": ("global_iucn_status",),
    "population_trend": ("population_trend_mm", "population_trend"),
    "myanmar_population": ("mm_population_mm", "mm_population"),
    "global_population": ("global_population_mm", "global_population"),
    "iucn_justification_my": ("justification_mm", "justification"),
    "distribution_my": ("distribution_mm", "distribution"),
    "behaviour_my": ("behaviour",),
    "threats_my": ("threats_to_survival_mm", "threats_to_survival"),
    "conservation_actions_my": (
        "conservation_research_undertaken_mm", "conservation_research_undertaken"
    ),
    "conservation_needs_my": (
        "conservation_research_needed_mm", "conservation_research_needed"
    ),
    "use_trade_my": ("use_and_trade_mm", "use_and_trade"),
    "wild_population_my": ("wild_population_mm", "wild_population"),
}

try:
    from myanmar_places import (
        ecosystem_names_my, protected_area_names_my, region_names_my,
    )
except ImportError:  # The standalone audit can still verify direct copies.
    ecosystem_names_my = protected_area_names_my = region_names_my = None


def decode_field_sources(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
    if not isinstance(raw, dict):
        return {}
    return {
        field: list(dict.fromkeys(url for url in urls if isinstance(url, str) and url))
        for field, urls in raw.items()
        if field in FIELD_LABELS and isinstance(urls, list)
    }


def portal_field_sources(animal):
    """Attribute unchanged direct imports to their saved portal page only."""
    try:
        portal = json.loads(animal.get("portal_data") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    slug = portal.get("linked_name") or animal.get("linked_name")
    url = (f"https://www.myanmarbiodiversity.org/species/{slug}" if slug else "")
    listed = decode_sources(animal)
    if not isinstance(portal, dict) or not portal or not url or url not in listed:
        return {}
    result = {}
    for field, keys in PORTAL_FIELDS.items():
        current = animal.get(field)
        if current in (None, ""):
            continue
        original = next((portal.get(key) for key in keys if portal.get(key)), None)
        if original is not None and str(current).strip() == str(original).strip():
            result[field] = [url]
    # The imported Myanmar name is the first portal name when several are given.
    original_name = portal.get("common_name_mm")
    if original_name and animal.get("name_my") == str(original_name).split("၊")[0].strip():
        result["name_my"] = [url]
    measurements = "\n".join(str(value) for value in (
        portal.get("measurement_length_mm") or portal.get("measurement_length"),
        portal.get("measurement_weight_mm") or portal.get("measurement_weight"),
    ) if value)
    if measurements and animal.get("size_my") == measurements:
        result["size_my"] = [url]
    derived = (
        ("region_my", "in_state_region", region_names_my),
        ("protected_areas_my", "in_protected_area", protected_area_names_my),
        ("ecosystems_my", "in_ecosytems", ecosystem_names_my),
        ("kba_my", "in_kba", protected_area_names_my),
    )
    for field, key, convert in derived:
        if convert and portal.get(key) and animal.get(field) == convert(portal[key]):
            result[field] = [url]
    return result


def decode_sources(animal):
    raw = animal.get("source_urls")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raw = []
    urls = {
        item.get("url") for item in raw or []
        if isinstance(item, dict) and item.get("url")
    }
    if animal.get("source_url"):
        urls.add(animal["source_url"])
    return urls


@lru_cache(maxsize=3)
def _import_cache(kind):
    filename = {
        "mammal": "protected_mammals_2020_crawl.json",
        "bird": "protected_birds_2020_crawl.json",
        "variant": "myanmar_name_variants_crawl.json",
    }[kind]
    path = Path(__file__).with_name("data") / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))["records"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return []


def imported_field_sources(animal, cache_record=None):
    """Trace unchanged protected-list imports to their actual fetch provider."""
    record_id = animal.get("source_record_id") or ""
    if record_id.startswith("protected_mammal_2020_"):
        kind = "mammal"
    elif record_id.startswith("protected_bird_2020_"):
        kind = "bird"
    elif record_id.startswith("name_variant_"):
        kind = "variant"
    else:
        return {}
    try:
        snapshot = json.loads(animal.get("portal_data") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(snapshot, dict):
        return {}
    if cache_record is None:
        matches = [
            item for item in _import_cache(kind)
            if (kind == "variant" or item.get("no") == snapshot.get("protected_list_no"))
            and (item.get("scientific_name") if kind == "mammal"
                 else item.get("taxon_name") if kind == "bird"
                 else (item.get("taxon") or {}).get("name")) == animal.get("scientific_name")
        ]
        if len(matches) != 1:
            return {}
        cache_record = matches[0]
    urls = decode_sources(animal)
    en = cache_record.get("en_url")
    my = cache_record.get("my_url")

    def unchanged(field, cache_key):
        value = animal.get(field)
        original = cache_record.get(cache_key)
        return value not in (None, "") and original not in (None, "") and str(value).strip() == str(original).strip()

    result = {}
    prose = {
        "description_my": "description", "habitat_my": "habitat",
        "diet_my": "diet", "distribution_my": "distribution",
        "behaviour_my": "behaviour", "physical_description_my": "physical_description",
        "threats_my": "threats", "conservation_actions_my": "conservation",
        "use_trade_my": "use_and_trade",
    }
    english_only = {
        "physical_description_my", "threats_my", "conservation_actions_my",
        "use_trade_my",
    }
    for field, cache_key in prose.items():
        if not unchanged(field, cache_key):
            continue
        if field in english_only:
            url = en
        elif field == "description_my":
            url = my if cache_record.get("description_language") == "my" else en
        else:
            has_myanmar = any("\u1000" <= ch <= "\u109f" for ch in str(animal[field]))
            # The importer prefers the Burmese section when present. A Latin
            # section could occur in either article, so do not guess its URL.
            url = my if has_myanmar else (en if not my else None)
        if url in urls:
            result[field] = [url]

    gbif_key = (cache_record.get("gbif") or {}).get("gbif_key")
    gbif_url = f"https://www.gbif.org/species/{gbif_key}" if gbif_key else None
    for field in ("species_order", "species_family"):
        key = "order" if field == "species_order" else "family"
        if (gbif_url in urls and animal.get(field)
                and (cache_record.get("gbif") or {}).get(key) == animal.get(field)):
            result[field] = [gbif_url]
    qid = cache_record.get("wikidata_qid")
    wiki_url = f"https://www.wikidata.org/wiki/{qid}" if qid else None
    if wiki_url in urls and unchanged("global_iucn_status", "global_iucn_status"):
        result["global_iucn_status"] = [wiki_url]
    return result


def sources_for_passages(animal, passages, *, identity_question=False):
    """Return verified links for retrieved fields, preserving record order."""
    mapping = decode_field_sources(animal.get("field_sources"))
    fields = {
        passage.field for passage in passages
        if passage.field and (identity_question or not passage.identity)
    }
    urls = {url for field in fields for url in mapping.get(field, [])}
    return [source for source in animal.get("sources") or [] if source.get("url") in urls]
