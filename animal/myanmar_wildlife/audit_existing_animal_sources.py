"""Link only provable existing animal sources; list every remaining gap.

This audit never discovers or adds a source URL. It uses the saved portal
snapshot and protected-list import cache as evidence of an unchanged field.
"""

import json
import re
import sqlite3
from pathlib import Path

from provenance import (
    FIELD_LABELS, decode_field_sources, decode_sources, imported_field_sources,
    portal_field_sources,
)


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "wildlife.db"
REPORT_PATH = ROOT / "docs" / "unverified_animal_field_sources.md"


def filled(value):
    return value is not None and str(value).strip() != ""


def cached_identity_sources(animal):
    """Use exact species identity plus a matching, already-listed page title."""
    record_id = animal.get("source_record_id") or ""
    if record_id.startswith("protected_mammal_2020_"):
        filename, taxon_key = "protected_mammals_2020_crawl.json", "scientific_name"
    elif record_id.startswith("protected_bird_2020_"):
        filename, taxon_key = "protected_birds_2020_crawl.json", "taxon_name"
    else:
        return {}
    try:
        snapshot = json.loads(animal.get("portal_data") or "{}")
        records = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))["records"]
    except (OSError, TypeError, ValueError, KeyError):
        return {}
    candidates = [
        record for record in records
        if record.get("no") == snapshot.get("protected_list_no")
        and record.get(taxon_key) == animal.get("scientific_name")
    ]
    if len(candidates) != 1:
        return {}
    record = candidates[0]
    gbif = record.get("gbif") or {}
    scientific = animal.get("scientific_name") or ""
    accepted = gbif.get("accepted_name") or ""
    if (gbif.get("match_type") != "EXACT" or not scientific
            or not (accepted == scientific or accepted.startswith(scientific + " "))):
        return {}
    listed = decode_sources(animal)
    result = {}
    gbif_url = f"https://www.gbif.org/species/{gbif['gbif_key']}" if gbif.get("gbif_key") else ""
    if gbif_url in listed:
        result["scientific_name"] = [gbif_url]
    for field, title_key, url_key in (
        ("name_en", "en_title", "en_url"),
        ("name_my", "my_title", "my_url"),
    ):
        title, url = record.get(title_key), record.get(url_key)
        if (title and url in listed and animal.get(field)
                and str(title).strip().casefold() == str(animal[field]).strip().casefold()):
            result[field] = [url]
    return result


def portal_excerpt_sources(animal):
    """Attribute a whole saved excerpt or exact name alias to its portal page."""
    try:
        portal = json.loads(animal.get("portal_data") or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(portal, dict) or portal.get("scientific_name") != animal.get("scientific_name"):
        return {}
    slug = portal.get("linked_name")
    url = f"https://www.myanmarbiodiversity.org/species/{slug}" if slug else ""
    if url not in decode_sources(animal):
        return {}
    result = {}
    description = (animal.get("description_my") or "").strip()
    justification = portal.get("justification_mm") or ""
    if len(description) >= 80 and description in justification:
        result["description_my"] = [url]
    name = (animal.get("name_my") or "").strip()
    aliases = re.split(r"[,၊/]", portal.get("common_name_mm") or "")
    if name and name in {alias.strip() for alias in aliases}:
        result["name_my"] = [url]
    return result


def audit():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    newly_linked = []
    pending = []
    try:
        with conn:
            for row in conn.execute("SELECT * FROM animals ORDER BY id").fetchall():
                animal = dict(row)
                current = decode_field_sources(animal.get("field_sources"))
                # These functions accept only unchanged source text and check
                # that the actual provider URL is present on the live record.
                verified = portal_field_sources(animal)
                verified.update(imported_field_sources(animal))
                verified.update(cached_identity_sources(animal))
                verified.update(portal_excerpt_sources(animal))
                added = {
                    field: urls for field, urls in verified.items()
                    if filled(animal.get(field)) and not current.get(field)
                }
                if added:
                    current.update(added)
                    conn.execute(
                        "UPDATE animals SET field_sources = ? WHERE id = ?",
                        (json.dumps(current, ensure_ascii=False), animal["id"]),
                    )
                    newly_linked.extend((animal["id"], field, urls) for field, urls in added.items())
                remaining = [
                    field for field in FIELD_LABELS
                    if filled(animal.get(field)) and not current.get(field)
                ]
                if remaining:
                    pending.append((animal, remaining))
    finally:
        conn.close()

    lines = [
        "# Source ဖြင့် အတည်မပြုနိုင်သေးသော တိရစ္ဆာန်အချက်များ",
        "",
        "ဤစာရင်းသည် source နှင့် မကိုက်ညီကြောင်း အတည်ပြုထားသော စာရင်းမဟုတ်ပါ။ "
        "လက်ရှိသိမ်းထားသော source link၊ မူရင်း snapshot နှင့် "
        "ယခုထိ စစ်ပြီးသော ပြင်ပ source များဖြင့် "
        "အချက်တစ်ခုချင်းစီကို သေချာမချိတ်နိုင်သေးသော စာရင်းဖြစ်သည်။ "
        "စာသားအချက်အလက်များကို database မှ မဖျက်ထားပါ။",
        "",
        f"- တိရစ္ဆာန်မှတ်တမ်း: {len(pending)} ခု",
        f"- Source မချိတ်ရသေးသော data field: {sum(len(fields) for _, fields in pending)} ခု",
        "",
        "## တိရစ္ဆာန်အလိုက် ကျန်ရှိသော field များ",
        "",
    ]
    for animal, fields in pending:
        title = f"{animal['name_my']} / {animal['name_en']} (ID {animal['id']})"
        lines += [
            f"### {title}",
            "",
            ", ".join(f"{FIELD_LABELS[field]} (`{field}`)" for field in fields),
            "",
        ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return newly_linked, pending


if __name__ == "__main__":
    linked, pending = audit()
    print(f"Linked {len(linked)} verified fields; {sum(len(f) for _, f in pending)} remain across {len(pending)} animals.")
    print(REPORT_PATH)
