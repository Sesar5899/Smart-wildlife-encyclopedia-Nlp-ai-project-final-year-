"""List every remaining population field and distinguish provenance from recency."""

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

from provenance import decode_field_sources


ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
FIELDS = ("population_trend", "myanmar_population", "global_population", "wild_population_my")
FIELD_LABELS = {
    "population_trend": "အကောင်ရေတွေ့ရှိမှုနှုန်း",
    "myanmar_population": "မြန်မာနိုင်ငံ အကောင်ရေ",
    "global_population": "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ",
    "wild_population_my": "တောရိုင်း အကောင်ရေ အသေးစိတ်",
}


def main():
    updates = json.loads((DOCS / "verified_population_updates.json").read_text(encoding="utf-8"))
    revised = {(item["animal_id"], item["field"]): item for item in updates if item["new_value"] is not None}
    narrative_log = DOCS / "population_narrative_corrections.json"
    if narrative_log.exists():
        revised.update({
            (item["animal_id"], item["field"]): item
            for item in json.loads(narrative_log.read_text(encoding="utf-8"))
        })
    translation_log = DOCS / "portal_population_translation_corrections.json"
    if translation_log.exists():
        revised.update({
            (item["animal_id"], item["field"]): item
            for item in json.loads(translation_log.read_text(encoding="utf-8"))
        })
    audit_path = DOCS / "portal_population_source_audit.csv"
    audited = {}
    if audit_path.exists():
        with audit_path.open(encoding="utf-8-sig", newline="") as input_file:
            audited = {
                (int(item["animal_id"]), item["field"]): item
                for item in csv.DictReader(input_file)
            }
    conn = sqlite3.connect(ROOT / "wildlife.db")
    conn.row_factory = sqlite3.Row
    rows = []
    try:
        for animal in conn.execute("SELECT * FROM animals ORDER BY id"):
            mapping = decode_field_sources(animal["field_sources"])
            for field in FIELDS:
                value = animal[field]
                if not value or not str(value).strip():
                    continue
                source_links = mapping.get(field, [])
                item = revised.get((animal["id"], field))
                if item:
                    status = "source_checked_correction_recency_not_guaranteed"
                    note = item["reason"]
                elif audited.get((animal["id"], field), {}).get("review_status") == "verified_against_saved_source":
                    status = "source_content_verified_recency_unconfirmed"
                    note = "Value matches the saved source text; whether a newer assessment exists was not established."
                elif source_links:
                    status = "source_linked_recency_unverified"
                    note = "A source link exists, but its underlying survey or assessment year has not been confirmed as the latest."
                else:
                    status = "source_and_recency_unverified"
                    note = "No field-level source link or currentness verification."
                rows.append({
                    "animal_id": animal["id"], "animal_name_my": animal["name_my"],
                    "animal_name_en": animal["name_en"], "scientific_name": animal["scientific_name"],
                    "field": field, "field_label": FIELD_LABELS[field], "value": value,
                    "review_status": status, "source_links": " | ".join(source_links),
                    "review_note": note,
                })
    finally:
        conn.close()
    counts = Counter(item["review_status"] for item in rows)
    DOCS.mkdir(exist_ok=True)
    csv_path = DOCS / "population_currentness_review.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    md_path = DOCS / "population_currentness_review.md"
    lines = [
        "# အကောင်ရေ field များ၏ source နှင့် ရက်စွဲ စိစစ်ချက်",
        "",
        "မူရင်းစာမျက်နှာမှ ၂၀၂၆ ခုနှစ်တွင် ကူးယူထားခြင်းသည် ကိန်းဂဏန်းကို "
        "၂၀၂၆ ခုနှစ်တွင် စစ်တမ်းကောက်ယူခဲ့ကြောင်း မဆိုလိုပါ။",
        "",
        f"- ဖြည့်ထားသော field: **{len(rows)} ခု**",
        f"- Source နှင့် အဓိပ္ပာယ် ပြန်တိုက်ပြီး ပြင်ထားသော field: **{counts['source_checked_correction_recency_not_guaranteed']} ခု** (အားလုံး နောက်ဆုံးရစာရင်းဟု မဆိုလိုပါ)",
        f"- သိမ်းထားသည့် source စာသားနှင့် တိုက်စစ်၍ ကိုက်ညီသော field: **{counts['source_content_verified_recency_unconfirmed']} ခု** (နောက်ဆုံးရဖြစ်ကြောင်း မအတည်ပြုရသေးပါ)",
        f"- Source ရှိသော်လည်း နောက်ဆုံးရဖြစ်ကြောင်း အတည်မပြုနိုင်သေးသော field: **{counts['source_linked_recency_unverified']} ခု**",
        f"- Field အလိုက် source နှင့် နောက်ဆုံးရအခြေအနေ မအတည်ပြုရသေးသော field: **{counts['source_and_recency_unverified']} ခု**",
        "",
        "အသေးစိတ်စာရင်းကို population_currentness_review.csv တွင် ကြည့်ပါ။ "
        "`source_linked_recency_unverified` ဆိုသည်မှာ မှားသည်ဟု ဆုံးဖြတ်ထားခြင်း မဟုတ်ပါ။",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} remaining fields: {dict(counts)}")
    print(md_path)
    print(csv_path)


if __name__ == "__main__":
    main()
