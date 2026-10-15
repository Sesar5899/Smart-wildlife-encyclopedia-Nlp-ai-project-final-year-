"""Myanmar place names in Myanmar script.

The Biodiversity Portal publishes a species' states and protected areas in
English only — ``in_state_region`` is "Rakhine,Ayeyarwady" and
``in_protected_area`` is "Htamanthi Wildlife Sanctuary".  Neither needs
translating: the states have fixed official names, and the portal's own
protected-area catalog, already cached in ``data/protected_areas.json``, carries
the Myanmar name of every area this site shows.  Looking both up is exact, so a
reader gets Myanmar script without a single machine-translated word.

A name with no known Myanmar form is left in English rather than guessed at.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from rapidfuzz import fuzz, process

STATE_REGION_MY = {
    "ayeyarwady": "ဧရာဝတီတိုင်းဒေသကြီး",
    "bago": "ပဲခူးတိုင်းဒေသကြီး",
    "chin": "ချင်းပြည်နယ်",
    "kachin": "ကချင်ပြည်နယ်",
    "kayah": "ကယားပြည်နယ်",
    "kayin": "ကရင်ပြည်နယ်",
    "magway": "မကွေးတိုင်းဒေသကြီး",
    "mandalay": "မန္တလေးတိုင်းဒေသကြီး",
    "mon": "မွန်ပြည်နယ်",
    "nay pyi taw": "နေပြည်တော်",
    "naypyitaw": "နေပြည်တော်",
    "rakhine": "ရခိုင်ပြည်နယ်",
    "sagaing": "စစ်ကိုင်းတိုင်းဒေသကြီး",
    "shan": "ရှမ်းပြည်နယ်",
    "tanintharyi": "တနင်္သာရီတိုင်းဒေသကြီး",
    "taninthayi": "တနင်္သာရီတိုင်းဒေသကြီး",
    "yangon": "ရန်ကုန်တိုင်းဒေသကြီး",
}

_SPLIT = re.compile(r"\s*[,၊;]\s*")


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _bare_key(value: str) -> str:
    """The key without any parenthetical, so an "(extension)" still matches."""
    return _key(re.sub(r"\([^)]*\)", " ", value))


def _parts(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in _SPLIT.split(str(value)) if part.strip()]


def region_names_my(value: str | None) -> str | None:
    """"Rakhine,Ayeyarwady" -> "ရခိုင်ပြည်နယ်၊ ဧရာဝတီတိုင်းဒေသကြီး"."""
    names = [STATE_REGION_MY.get(_key(part), part) for part in _parts(value)]
    return "၊ ".join(dict.fromkeys(names)) or None


@lru_cache(maxsize=1)
def _protected_area_index() -> dict[str, str]:
    from portal_collections import load_protected_areas

    index = {}
    for record in load_protected_areas():
        name_mm = (record.get("name_mm") or "").strip()
        if not name_mm:
            continue
        for name in (record.get("name"), record.get("slug")):
            if name:
                index[_key(name)] = name_mm
    return index


def protected_area_names_my(value: str | None) -> str | None:
    """Protected-area names in Myanmar, keeping any the catalog cannot name."""
    index = _protected_area_index()
    names = []
    for part in _parts(value):
        key = _key(part)
        name = index.get(key) or index.get(_bare_key(part))
        if name is None:
            # "Hukaung Valley (Extension) Wildlife Sanctuary" is catalogued
            # without its extension; fall back to the longest catalogued name
            # the value contains rather than leaving the whole entry English.
            bare = _bare_key(part)
            candidates = [
                (len(other), mm) for other, mm in index.items()
                if other and (bare.startswith(other) or other.startswith(bare))
            ]
            if candidates:
                name = max(candidates)[1]
        if name is None:
            # A last resort for spelling drift between the two portal catalogs
            # ("Taninthayi" against "Tanintharyi"), kept strict enough that it
            # cannot name one protected area as another.
            match = process.extractOne(
                _bare_key(part), index.keys(), scorer=fuzz.ratio, score_cutoff=92
            )
            name = index[match[0]] if match else part
        names.append(name)
    return "၊ ".join(dict.fromkeys(names)) or None


@lru_cache(maxsize=1)
def _ecosystem_index() -> dict[str, str]:
    from portal_collections import load_ecosystems

    index = {}
    for record in load_ecosystems():
        name = (record.get("name_mm") or record.get("name") or "").strip()
        if not name:
            continue
        for identifier in (record.get("id"), record.get("geoserver_id"), record.get("code")):
            if identifier:
                index[_key(str(identifier))] = name
    return index


def ecosystem_names_my(value: str | None) -> str | None:
    """Resolve portal ecosystem IDs to the catalog's published Myanmar names."""
    index = _ecosystem_index()
    names = [index.get(_key(part), part) for part in _parts(value)]
    return "၊ ".join(dict.fromkeys(names)) or None
