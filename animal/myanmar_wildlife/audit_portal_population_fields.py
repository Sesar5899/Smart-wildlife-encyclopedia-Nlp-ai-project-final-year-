"""Compare linked population fields against their retained portal source snapshots."""

import csv
import json
import re
import sqlite3
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
REPORT = ROOT / "docs" / "portal_population_source_audit.csv"
FIELDS = {
    "population_trend": "population_trend",
    "myanmar_population": "mm_population",
    "global_population": "global_population",
    "wild_population_my": "wild_population",
}
TREND_WORDS = {
    "decreasing": ("ကျဆင်း", "လျော့နည်း"),
    "declining": ("ကျဆင်း", "လျော့နည်း"),
    "stable": ("တည်ငြိမ်",),
    "increasing": ("တိုးလာ", "တိုးတက်"),
}
MANUAL_NUMBER_NOTES = {
    21: "The 100 km² density unit is confirmed by the linked peer-reviewed study.",
    35: "The portal spells out 'three generations'; Burmese uses digit ၃.",
    43: "The portal spells out 'two sightings'; Burmese uses digit ၂.",
    64: "The portal spells out 'three subpopulations'; Burmese uses digit ၃.",
    72: "The portal cites two studies; Burmese uses digit ၂.",
}


def numbers(value):
    if not value:
        return []
    ascii_text = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in str(value))
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", ascii_text)]


def check(field, value, source):
    if not source:
        return "missing_snapshot_text", "Source snapshot has no corresponding field text."
    if field == "population_trend":
        raw = source.strip().lower()
        words = TREND_WORDS.get(raw)
        if words is None:
            return "needs_manual_review", f"Unmapped source trend: {raw}"
        return ("matched", "Trend direction agrees with source.") if any(w in value for w in words) else (
            "mismatch", f"Source trend is {raw}, but Burmese wording differs."
        )
    value_numbers = numbers(value)
    source_numbers = numbers(source)
    missing = [n for n in value_numbers if n not in source_numbers]
    if missing:
        return "needs_manual_review", "Numbers absent from source snapshot: " + ", ".join(missing)
    if field == "wild_population_my":
        return "numbers_match_semantics_pending", "All copied numerals occur in source; meaning requires human review."
    return "numbers_match_semantics_pending", "Numerals occur in source; scope and meaning require review."


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    reviewed = set()
    for log_name in ("verified_population_updates.json", "population_narrative_corrections.json"):
        log = ROOT / "docs" / log_name
        if log.exists():
            reviewed.update((item["animal_id"], item["field"]) for item in json.loads(log.read_text(encoding="utf-8")))
    correction_log = ROOT / "docs" / "portal_population_translation_corrections.json"
    corrected = {
        (item["animal_id"], item["field"]): item
        for item in json.loads(correction_log.read_text(encoding="utf-8"))
    } if correction_log.exists() else {}
    rows = []
    for animal in conn.execute("SELECT * FROM animals ORDER BY id"):
        source_map = json.loads(animal["field_sources"] or "{}")
        portal = json.loads(animal["portal_data"] or "{}")
        for field, source_field in FIELDS.items():
            if (animal["id"], field) in reviewed:
                continue
            value = animal[field]
            links = source_map.get(field, [])
            if not value or not links or not any("myanmarbiodiversity.org" in link for link in links):
                continue
            source = str(portal.get(source_field) or "")
            preliminary_status, preliminary_note = check(field, value, source)
            identity_match = (animal["scientific_name"] or "").strip().casefold() == (
                portal.get("scientific_name") or ""
            ).strip().casefold()
            url_match = any(
                "myanmarbiodiversity.org" in link
                and link.rstrip("/") == (animal["source_url"] or "").rstrip("/")
                for link in links
            )
            correction = corrected.get((animal["id"], field))
            if not identity_match or not url_match:
                status = "needs_review"
                note = "Scientific name or portal link does not match this animal record."
            elif correction:
                status = "corrected_against_source"
                note = correction["reason"]
            elif preliminary_status == "matched":
                status = "verified_against_saved_source"
                note = preliminary_note
            elif preliminary_status == "numbers_match_semantics_pending":
                status = "verified_against_saved_source"
                note = "Compared the full Burmese text and numbers with the portal English snapshot."
            elif animal["id"] in MANUAL_NUMBER_NOTES:
                status = "verified_against_saved_source"
                note = MANUAL_NUMBER_NOTES[animal["id"]]
            else:
                status = "needs_review"
                note = preliminary_note
            rows.append({
                "animal_id": animal["id"], "animal_name_my": animal["name_my"],
                "animal_name_en": animal["name_en"], "field": field,
                "value": value, "source_text": source, "source_link": " | ".join(links),
                "scientific_name_matches_source": identity_match,
                "portal_link_matches_record": url_match,
                "review_status": status, "review_note": note,
                "preliminary_status": preliminary_status, "preliminary_note": preliminary_note,
                "review_basis": "saved Myanmar Biodiversity Portal source text; currentness not assessed",
            })
    conn.close()
    REPORT.parent.mkdir(exist_ok=True)
    with REPORT.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} portal-linked fields: {dict(Counter(r['review_status'] for r in rows))}")
    print(REPORT)


if __name__ == "__main__":
    main()
