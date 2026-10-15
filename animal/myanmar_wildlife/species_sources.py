"""Public sources every protected-list importer draws on.

``crawler.py`` reads the Myanmar Biodiversity Portal, which publishes 82
species.  The Protected Wildlife List (2020) and Notification 690/2020 name far
more than that, so their importers assemble records from four public sources
instead, and this module is the part they share:

* **Wikidata** — the global IUCN category for a taxon.
* **Wikipedia** — the prose, Burmese where an article exists and English
  otherwise, split into the fields this encyclopedia publishes.
* **GBIF** — order, family and the accepted name behind a taxon.
* **Wikimedia Commons** — the photograph, with the photographer and licence
  that the licence requires be printed wherever the picture is shown.

Nothing here writes to the database; the importers decide what to do with what
this returns.
"""

from __future__ import annotations

import html
import io
import csv
import re
import unicodedata
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import iucn

USER_AGENT = (
    "MyanmarWildlifeEducationalImporter/1.0 "
    "(educational encyclopedia; contact myominko1011@gmail.com)"
)
EN_WIKI = "https://en.wikipedia.org/w/api.php"
MY_WIKI = "https://my.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
GBIF_MATCH = "https://api.gbif.org/v1/species/match"

# The abbreviation for every written-out assessment, taken from the same
# category table the site renders, so a crawled label and a rendered badge
# can never disagree about what a code means.
IUCN_CODES = iucn.CODES_BY_NAME

# Wikipedia headings vary between articles, so each field claims the sections
# whose heading names its subject.  The order matters: a section is assigned to
# the first field that recognises it and to no other, which is what keeps the
# dhole's "Feeding ecology" out of its "Ecology and behaviour" text.  A section
# whose own heading matches nothing inherits its parent's field, so the
# Irrawaddy dolphin's per-country subsections stay with "Conservation".
SECTION_MAP = (
    ("diet", ("diet", "feeding", "food", "foraging", "prey", "hunting behavi")),
    ("habitat", ("habitat",)),
    ("distribution", ("distribution", "geographic range", "range and", "occurrence")),
    ("threats", ("threat", "poaching", "whaling", "bycatch", "exploitation", "entanglement")),
    ("conservation", ("conservation", "protection", "recovery", "management")),
    (
        "use_trade",
        ("trade", "interaction with human", "in culture", "cultural", "in captivity", "tourism"),
    ),
    (
        "physical",
        (
            "description",
            "characteristic",
            "anatomy",
            "appearance",
            "morphology",
            "physiology",
            "physical",
            "size",
        ),
    ),
    (
        "behaviour",
        (
            "behaviour",
            "behavior",
            "ecology",
            "reproduction",
            "breeding",
            "communication",
            "vocalization",
            "vocalisation",
            "social",
            "life cycle",
            "mating",
            "migration",
        ),
    ),
)
# Sections that are never useful prose for an encyclopedia entry.  Everything
# nested under one of these is dropped with it.
SECTION_SKIP = (
    "see also",
    "references",
    "external links",
    "further reading",
    "notes",
    "bibliography",
    "footnotes",
    "sources",
    "gallery",
    "taxonomy",
    "etymology",
    "phylogeny",
    "phylogeography",
    "fossil",
    "genetics",
    "genomics",
    "subspecies",
    "naming",
    "evolution",
)

# A Wikipedia lead image is often not a photograph of the animal at all: the
# pygmy sperm whale leads with a size-comparison silhouette and the leaf muntjac
# with a distribution map.  Publishing those as the species photograph would
# break the same promise the portal importer makes, so a candidate file is
# rejected outright when its name or its Commons categories say it depicts
# something other than the animal.
NOT_A_PHOTOGRAPH = (
    "size comparison",
    "distribution map",
    "range map",
    " maps",
    "maps of",
    "diagram",
    "cladogram",
    "phylogen",
    "silhouette",
    "skeleton",
    "skeletal",
    "skull",
    "bones",
    "teeth",
    "chart",
    "logo",
    "icon",
    "stamp",
    "coin",
    "signature",
    "map of",
    "_map",
    " map",
    "distribution",
    "sonogram",
    "spectrogram",
    "footprint",
    "track",
    "fetus",
    "foetus",
    "embryo",
    "specimen",
    # Commons titles are not always in English, and a skull or a foetus is
    # still not the picture a reader is asking for.
    "頭骨",
    "骨骼",
    "標本",
    "胎兒",
    "胎児",
    "schädel",
    "skelett",
)
# Still a depiction of the animal, but a photograph is preferred where one exists.
NOT_A_PHOTOGRAPH_BUT_A_DEPICTION = (
    "drawing",
    "illustration",
    "painting",
    "engraving",
    "lithograph",
    "plate",
    "artwork",
    "sculpture",
    "model",
    "taxidermy",
)
MINIMUM_PHOTO_WIDTH = 240

DESCRIPTION_LIMIT = 2400
SECTION_LIMIT = 2000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session() -> requests.Session:
    if not hasattr(session, "_value"):
        value = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        value.mount("https://", HTTPAdapter(max_retries=retry))
        value.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        session._value = value
    return session._value


def api(endpoint: str, params: dict) -> dict:
    payload = {"format": "json", "formatversion": "2", **params}
    response = session().get(endpoint, params=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


# --------------------------------------------------------------------------
# Source lookups
# --------------------------------------------------------------------------


def fetch_wikipedia(endpoint: str, titles: list[str], *, langlink: str | None = None) -> dict:
    """Resolve titles on one Wikipedia and return them keyed by the title asked for.

    Metadata is batched, but the article text is not: MediaWiki only returns a
    complete plaintext extract when a single title is asked for, and silently
    answers a batch with the lead of one page.  Asking one at a time is the
    difference between a real record and an empty one.
    """
    resolved: dict[str, dict] = {}
    for batch in chunked(titles, 20):
        params = {
            "action": "query",
            "redirects": "1",
            "prop": "pageimages|pageprops",
            "piprop": "original|name",
            "ppprop": "wikibase_item",
            "titles": "|".join(batch),
        }
        if langlink:
            params["prop"] += "|langlinks"
            params["lllang"] = langlink
        data = api(endpoint, params)["query"]
        aliases = {item["from"]: item["to"] for item in data.get("normalized", [])}
        aliases.update({item["from"]: item["to"] for item in data.get("redirects", [])})
        pages = {page["title"]: page for page in data.get("pages", [])}
        for title in batch:
            target = aliases.get(title, title)
            target = aliases.get(target, target)
            page = pages.get(target)
            if not page or page.get("missing"):
                continue
            links = page.get("langlinks") or []
            resolved[title] = {
                "title": page["title"],
                "extract": "",
                "qid": (page.get("pageprops") or {}).get("wikibase_item"),
                "image_file": page.get("pageimage"),
                "image_url": (page.get("original") or {}).get("source"),
                "langlink": links[0]["title"] if links else None,
            }

    for entry in resolved.values():
        entry["extract"] = fetch_extract(endpoint, entry["title"])
    return resolved


def fetch_extract(endpoint: str, title: str) -> str:
    data = api(
        endpoint,
        {
            "action": "query",
            "redirects": "1",
            "prop": "extracts",
            "explaintext": "1",
            "exlimit": "1",
            "titles": title,
        },
    )
    for page in data.get("query", {}).get("pages", []):
        if not page.get("missing"):
            return page.get("extract") or ""
    return ""


def fetch_iucn_statuses(qids: list[str]) -> dict[str, str]:
    """Map each Wikidata item to its IUCN category code via property P141."""
    statuses: dict[str, str] = {}
    referenced: set[str] = set()
    raw: dict[str, str] = {}
    for batch in chunked(sorted(set(qids)), 40):
        data = api(
            WIKIDATA,
            {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"},
        )
        for qid, entity in (data.get("entities") or {}).items():
            claims = (entity.get("claims") or {}).get("P141") or []
            for claim in claims:
                value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
                if isinstance(value, dict) and value.get("id"):
                    raw[qid] = value["id"]
                    referenced.add(value["id"])
                    break
    labels: dict[str, str] = {}
    for batch in chunked(sorted(referenced), 40):
        data = api(
            WIKIDATA,
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels",
                "languages": "en",
            },
        )
        for qid, entity in (data.get("entities") or {}).items():
            label = ((entity.get("labels") or {}).get("en") or {}).get("value")
            if label:
                labels[qid] = label
    for qid, status_qid in raw.items():
        label = labels.get(status_qid, "")
        code = IUCN_CODES.get(label.casefold())
        if code:
            statuses[qid] = code
    return statuses


def fetch_taxonomy(scientific_name: str) -> dict:
    """Order and family from the GBIF backbone; only an accepted match is used."""
    response = session().get(
        GBIF_MATCH, params={"name": scientific_name, "strict": "false"}, timeout=45
    )
    response.raise_for_status()
    data = response.json()
    if data.get("matchType") in (None, "NONE"):
        return {}
    return {
        "class_name": data.get("class"),
        "order": data.get("order"),
        "family": data.get("family"),
        "accepted_name": data.get("scientificName"),
        "gbif_key": data.get("usageKey"),
        "match_type": data.get("matchType"),
    }


def fetch_taxon(name: str, rank: str) -> dict:
    """Resolve a taxon above species level.

    The GBIF match endpoint answers a bare genus name with the kingdom unless
    it is told what rank to look for, and it does not carry subfamilies at all —
    those are looked up through the search endpoint instead.
    """
    if rank == "species":
        return fetch_taxonomy(name)

    response = session().get(
        GBIF_MATCH,
        params={"name": name, "rank": rank.upper(), "strict": "false"},
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    if (data.get("rank") or "").casefold() == rank and data.get("usageKey"):
        return {
            "accepted_name": data.get("scientificName") or name,
            "rank": rank,
            "class_name": data.get("class"),
            "order": data.get("order"),
            "family": data.get("family"),
            "gbif_key": data.get("usageKey"),
            "match_type": data.get("matchType"),
        }

    # The GBIF backbone omits bird subfamilies entirely; they exist only in the
    # contributed checklists, so the search is not restricted to the backbone.
    search = session().get(
        "https://api.gbif.org/v1/species/search",
        params={"q": name, "rank": rank.upper(), "limit": "10"},
        timeout=45,
    )
    search.raise_for_status()
    matches = [
        result
        for result in search.json().get("results", [])
        if (result.get("canonicalName") or "").casefold() == name.casefold()
    ]
    # Prefer an entry that knows where it sits, and that has children to list.
    matches.sort(key=lambda result: (bool(result.get("family")), result.get("numDescendants") or 0), reverse=True)
    for result in matches:
        return {
            "accepted_name": result.get("scientificName") or name,
            "rank": rank,
            "class_name": result.get("class"),
            "order": result.get("order"),
            "family": result.get("family"),
            "gbif_key": result.get("key"),
            "match_type": "SEARCH",
        }
    return {}


def taxon_genera(gbif_key: int) -> list[str]:
    """Every genus GBIF places under this taxon, for ranks a record cannot store.

    A species row carries only its order and family, so membership of a
    subfamily such as Aegypiinae has to be decided by genus instead.
    """
    genera: list[str] = []
    offset = 0
    while True:
        response = session().get(
            f"https://api.gbif.org/v1/species/{gbif_key}/children",
            params={"limit": "100", "offset": str(offset)},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        for result in payload.get("results", []):
            if (result.get("rank") or "").casefold() == "genus" and result.get("canonicalName"):
                genera.append(result["canonicalName"])
        if payload.get("endOfRecords", True):
            break
        offset += 100
    return genera


def strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip() or None


def photograph_score(
    title: str,
    info: dict,
    scientific_name: str,
    english_title: str,
    *,
    require_identity: bool = False,
):
    """Rank one Commons file as a photograph of this species; ``None`` rejects it.

    ``require_identity`` is set for files found by searching Commons rather than
    by Wikipedia's own editors.  A species category is not proof of identity:
    Commons files "Muntiacus gongshanensis" under a photograph whose own title,
    description and categories all say *Muntiacus feae*.  A searched file must
    therefore name this species itself, and is rejected outright when it names a
    different one from the same genus.
    """
    if (info.get("mime") or "").startswith("image/svg"):
        return None
    width = int(info.get("width") or 0)
    if width and width < MINIMUM_PHOTO_WIDTH:
        return None

    meta = info.get("extmetadata") or {}
    categories = " ".join(
        [
            strip_markup((meta.get("Categories") or {}).get("value")) or "",
            *info.get("_categories", []),
        ]
    ).casefold()
    description = (
        strip_markup((meta.get("ImageDescription") or {}).get("value")) or ""
    ).casefold()
    haystack = f"{title.casefold()} {categories} {description}"
    if any(marker in haystack for marker in NOT_A_PHOTOGRAPH):
        return None

    binomial = scientific_name.casefold()
    genus, _, epithet = binomial.partition(" ")
    folded_title = title.casefold()
    english = english_title.casefold()
    # A file whose own name says which species it shows needs no further proof.
    # Otherwise the categories and description have to name this species and no
    # other one from the same genus.
    named_by_title = binomial in folded_title or english in folded_title
    names_this_species = binomial in haystack or english in haystack
    names_another = bool(
        re.search(rf"\b{re.escape(genus)}\s+(?!{re.escape(epithet)})[a-z]{{3,}}\b", haystack)
    )
    if require_identity and not named_by_title and (not names_this_species or names_another):
        return None

    score = 0.0
    if binomial in haystack:
        score += 6
    elif english_title.casefold() in haystack:
        score += 4
    elif genus in haystack:
        score += 1
    if any(marker in haystack for marker in NOT_A_PHOTOGRAPH_BUT_A_DEPICTION):
        score -= 3
    if (info.get("mime") or "") == "image/jpeg":
        score += 1
    score += min(width, 4000) / 4000
    return score


def article_images(endpoint: str, title: str) -> list[str]:
    """Every file used on one Wikipedia article.

    Editors put these on this species' page, which is a far stronger identity
    signal than a Commons category — species categories are routinely misfiled.
    Navbox and taxobox furniture comes back too, so the caller still checks that
    a file names the species before publishing it.
    """
    data = api(
        endpoint,
        {
            "action": "query",
            "prop": "images",
            "imlimit": "100",
            "redirects": "1",
            "titles": title,
        },
    )
    files = []
    for page in data.get("query", {}).get("pages", []):
        for image in page.get("images") or []:
            files.append(image["title"])
    return files


def choose_photograph(
    scientific_name: str,
    english_title: str,
    preferred: tuple[str, dict] | None,
    candidates: list[str],
) -> tuple[str, dict] | None:
    """The best genuine photograph of this species, with its licence."""
    if preferred:
        title, info = preferred
        # Wikipedia's editors chose this file to head this species' own article,
        # so it does not have to prove its identity — only that it is a picture
        # of the animal rather than a map or a size chart.
        if photograph_score(title, info, scientific_name, english_title) is not None:
            return title, info

    if not candidates:
        return None
    best = None
    for batch in chunked(candidates, 25):
        for page_title, info in fetch_image_info(batch).items():
            score = photograph_score(
                page_title, info, scientific_name, english_title, require_identity=True
            )
            if score is not None and (best is None or score > best[0]):
                best = (score, page_title, info)
    return (best[1], best[2]) if best else None


def licence_of(title: str, info: dict) -> dict:
    meta = info.get("extmetadata") or {}

    def field(name):
        return strip_markup((meta.get(name) or {}).get("value"))

    return {
        "file": title,
        "download_url": info.get("thumburl") or info.get("url"),
        "file_page": info.get("descriptionurl"),
        "artist": field("Artist"),
        "credit": field("Credit"),
        "licence": field("LicenseShortName"),
        "licence_url": field("LicenseUrl"),
    }


def commons_title(filename: str) -> str:
    """The Commons page title for a ``pageimage`` filename (which uses underscores)."""
    name = filename.replace("_", " ").strip()
    return name if name.startswith("File:") else f"File:{name}"


def fetch_image_info(filenames: list[str]) -> dict[str, dict]:
    """Raw Commons ``imageinfo`` for each file, keyed by its Commons page title."""
    infos: dict[str, dict] = {}
    titles = [commons_title(name) for name in filenames]
    for batch in chunked(sorted(set(titles)), 25):
        data = api(
            COMMONS,
            {
                "action": "query",
                "prop": "imageinfo|categories",
                "iiprop": "url|extmetadata|mime|size",
                "iiurlwidth": "1400",
                "cllimit": "500",
                "titles": "|".join(batch),
            },
        )
        for page in data.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [None])[0]
            if info:
                info["_categories"] = [
                    item["title"].removeprefix("Category:")
                    for item in (page.get("categories") or [])
                ]
                infos[page["title"]] = info
    return infos


# --------------------------------------------------------------------------
# Turning an article into record fields
# --------------------------------------------------------------------------


def split_sections(extract: str) -> tuple[str, list[dict]]:
    """Split a plaintext Wikipedia extract into its lead and its headed sections.

    ``==`` marks a top-level section and each extra ``=`` one level deeper, so
    the level is kept: it is what lets a subsection inherit the field its parent
    was assigned to.
    """
    parts = re.split(r"\n(=+)\s*(.+?)\s*\1\n", "\n" + extract.strip() + "\n")
    lead = parts[0].strip()
    sections = []
    for index in range(1, len(parts) - 2, 3):
        sections.append(
            {
                "level": len(parts[index]),
                "heading": parts[index + 1].strip(),
                "body": parts[index + 2].strip(),
            }
        )
    return lead, sections


def field_for(heading: str) -> str | None:
    folded = heading.casefold()
    for field, keywords in SECTION_MAP:
        if any(keyword in folded for keyword in keywords):
            return field
    return None


# A country section is often the last thing an article says on a subject, so a
# length cap drops it — and for this encyclopedia the paragraph about Myanmar is
# the one that must survive.  The Irrawaddy dolphin's conservation text ran past
# the cap exactly where it began describing the protected stretch of the
# Ayeyarwady between Mingun and Kyaukmyaung.
MYANMAR_TERMS = re.compile(
    r"\b(myanmar|burma|burmese|ayeyarwady|irrawaddy|chindwin|thanlwin|salween|"
    r"rakhine|tanintharyi|tenasserim|kachin|kayah|kayin|sagaing|mandalay|yangon|"
    r"bago|magway|shan state|mon state|chin state|naypyidaw|nay pyi taw)\b",
    re.IGNORECASE,
)


def myanmar_first(items: list[tuple[str, str]]) -> list[str]:
    """Order whole sections so anything about Myanmar survives trimming.

    The heading is the signal that matters.  Testing the prose instead fails on
    exactly the species that need this most: every paragraph of the Irrawaddy
    dolphin's conservation text contains the word "Irrawaddy", so nothing sorts
    above anything else, while its subsection headed "Myanmar" is the one part a
    reader here cannot do without.
    """
    def rank(item):
        heading, body = item
        return (
            bool(MYANMAR_TERMS.search(heading)),
            bool(MYANMAR_TERMS.search(body)),
        )

    ordered = sorted(items, key=rank, reverse=True)
    return [body for _, body in ordered]


def assign_sections(sections: list[dict]) -> dict[str, str]:
    """Give every section to exactly one field, letting subsections inherit."""
    collected: dict[str, list[tuple[str, str]]] = {}
    stack: list[tuple[int, str | None]] = []
    skip_level = None

    for section in sections:
        level, heading, body = section["level"], section["heading"], section["body"]
        if skip_level is not None:
            if level > skip_level:
                continue
            skip_level = None
        folded = heading.casefold()
        if any(word in folded for word in SECTION_SKIP):
            skip_level = level
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()
        field = field_for(heading) or (stack[-1][1] if stack else None)
        stack.append((level, field))
        if field and body:
            collected.setdefault(field, []).append((heading, body))

    assembled = {}
    for field, items in collected.items():
        text = "\n\n".join(body for _, body in items)
        if len(text) > SECTION_LIMIT:
            text = "\n\n".join(myanmar_first(items))
        assembled[field] = trim(text, SECTION_LIMIT)
    return assembled


def trim(text: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind("။"), cut.rfind(". "), cut.rfind("\n"))
    if stop > limit * 0.5:
        cut = cut[: stop + 1]
    return cut.rstrip() + " …"


def slugify(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", ascii_text)).strip("_")


def normalize_scientific(value: str | None) -> str:
    """Genus + species only, so 'Bos gaurus' matches 'Bos gaurus Smith, 1827'."""
    if not value:
        return ""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z]+", ascii_text)
    return " ".join(words[:2]).casefold()



def english_names(raw: str) -> list[str]:
    """A list column's English names, e.g. "Malayan Pangolin / Sunda Pangolin"."""
    return [part.strip() for part in raw.split("/") if part.strip()]


def myanmar_names(raw: str) -> list[str]:
    """The same for a Myanmar column, which separates with / or the Myanmar comma."""
    return [part.strip() for part in re.split(r"[/၊]", raw) if part.strip()]


def is_montage(title: str, info: dict) -> bool:
    """Whether a Commons file shows several species rather than one.

    A family article often leads with a grid of members.  That is a fine picture
    for a family record, but it cannot be captioned with a single species name.
    Commons marks these with a "Montages of …" category, and their descriptions
    list every bird in the grid.
    """
    meta = info.get("extmetadata") or {}
    categories = " ".join(info.get("_categories", [])).casefold()
    if "montage" in categories or "collage" in categories:
        return True
    description = strip_markup((meta.get("ImageDescription") or {}).get("value")) or ""
    return len(set(re.findall(r"\b[A-Z][a-z]{2,}[ _][a-z]{3,}\b", description))) > 2


def depicted_species_candidates(title: str, info: dict) -> list[str]:
    """Binomials a Commons file might be saying it depicts, best guess first.

    Pattern alone cannot settle this — "Bulgaria photographs" is shaped exactly
    like a species name — so the caller checks each candidate against GBIF
    before publishing it as a caption.
    """
    meta = info.get("extmetadata") or {}
    sources = [
        title.removeprefix("File:"),
        strip_markup((meta.get("ImageDescription") or {}).get("value")) or "",
        *info.get("_categories", []),
    ]
    found: list[str] = []
    for text in sources:
        for match in re.finditer(r"\b([A-Z][a-z]{2,})[ _]([a-z]{3,})\b", text):
            candidate = f"{match.group(1)} {match.group(2)}"
            if candidate not in found:
                found.append(candidate)
    return found


# --------------------------------------------------------------------------
# Photographs for a taxon that is not a species
# --------------------------------------------------------------------------


def member_species(candidates: list[str], taxon: dict, verified: dict | None = None) -> str | None:
    """The first candidate GBIF confirms is a species inside this group.

    GBIF does not carry bird subfamilies, so a subfamily is checked against its
    parent family instead — every Aegypiinae is an Accipitridae, so the caption
    still cannot name an animal from outside the group.
    """
    verified = {} if verified is None else verified
    wanted = taxon["name"].casefold()
    rank = taxon["rank"]
    for candidate in candidates:
        if candidate not in verified:
            try:
                verified[candidate] = fetch_taxonomy(candidate)
            except Exception:
                verified[candidate] = {}
        match = verified[candidate]
        if not match or match.get("match_type") not in ("EXACT", "FUZZY"):
            continue
        genus = candidate.split(" ")[0].casefold()
        family = (match.get("family") or "").casefold()
        order = (match.get("order") or "").casefold()
        belongs = (
            (rank == "genus" and genus == wanted)
            or (rank == "family" and family == wanted)
            or (rank == "order" and order == wanted)
            or (rank == "subfamily" and family == (taxon.get("family") or "").casefold())
        )
        if belongs:
            return candidate
    return None


@lru_cache(maxsize=1)
def myanmar_species_names() -> frozenset[str]:
    """Species recorded in Myanmar, from the official 2020 wildlife schedules.

    A group record's example should be an animal a reader in Myanmar could
    actually meet.  Without this, the fox genus leads with an Arctic fox and the
    rhinoceros family with African white rhinos — both truthfully captioned, and
    both the wrong picture for this encyclopedia.
    """
    path = (
        Path(__file__).resolve().parent.parent
        / "animal infos" / "outputs" / "animal-lists-2020"
        / "myanmar_wildlife_lists_2020.csv"
    )
    names = set()
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("scientific_name") or "").strip()
                if name:
                    names.add(normalize_scientific(name))
    return frozenset(names)


def taxon_photograph(taxon, page, lead_images, my_page, verified=None, preferred_members=()):
    """The picture for one record, and the species it shows if it is a group.

    A species record may use its article's lead image as itself.  A group record
    may not: the picture is of one member, so it is published only when the file
    names that member and GBIF confirms the member is inside the group.  The
    returned example is ``""`` for a montage of several members, which can be
    captioned as examples but not as any one of them.
    """
    name = taxon["name"]
    preferred = None
    if page.get("image_file"):
        title = commons_title(page["image_file"])
        info = lead_images.get(title)
        if info:
            preferred = (title, info)

    if taxon["rank"] == "species":
        candidates = []
        if not preferred or photograph_score(*preferred, name, page["title"]) is None:
            candidates = article_images(EN_WIKI, page["title"])
            if my_page:
                candidates += article_images(MY_WIKI, my_page["title"])
            candidates = list(dict.fromkeys(candidates))
        return choose_photograph(name, page["title"], preferred, candidates), None

    # The lead image is the one editors chose to represent the whole group, so
    # it wins whenever it names a member — unless that member does not occur in
    # Myanmar and another picture on the page shows one that does.  Ranking the
    # lead above the rest is also what keeps a fossil genus, mentioned only in
    # some category list, from winning on raw score.
    wanted = frozenset(preferred_members)
    titles = article_images(EN_WIKI, page["title"])
    if my_page:
        titles += article_images(MY_WIKI, my_page["title"])
    seen = {preferred[0]} if preferred else set()
    candidates = ([preferred] if preferred else []) + [
        (title, info)
        for title, info in fetch_image_info(list(dict.fromkeys(titles))).items()
        if title not in seen
    ]

    best = None
    for index, candidate in enumerate(candidates):
        score = photograph_score(*candidate, name, page["title"])
        if score is None:
            continue
        example = member_species(depicted_species_candidates(*candidate), taxon, verified)
        if not example:
            continue
        rank = (
            normalize_scientific(example) in wanted,
            preferred is not None and index == 0,
            score,
        )
        if best is None or rank > best[0]:
            best = (rank, candidate, "" if is_montage(*candidate) else example)
    return (best[1], best[2]) if best else (None, None)


# --------------------------------------------------------------------------
# Photographs
# --------------------------------------------------------------------------


def is_webp(content: bytes) -> bool:
    return len(content) > 2048 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"


def save_webp(url: str, destination: Path) -> int:
    """Download one Commons photograph and store it as WebP beside the portal's."""
    from PIL import Image

    response = session().get(url, timeout=120)
    response.raise_for_status()
    picture = Image.open(io.BytesIO(response.content))
    if picture.mode not in ("RGB", "RGBA"):
        picture = picture.convert("RGB")
    picture.save(destination, "WEBP", quality=82, method=5)
    if not is_webp(destination.read_bytes()):
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Rejected invalid photograph: {url}")
    return destination.stat().st_size


def credit_line(image: dict | None) -> str | None:
    """The attribution the Commons licence requires, as one printable line."""
    if not image:
        return None
    parts = [image.get("artist") or image.get("credit") or "Unknown photographer"]
    if image.get("licence"):
        parts.append(image["licence"])
    parts.append("Wikimedia Commons")
    return " · ".join(part for part in parts if part)
