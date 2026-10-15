"""Export populated animal population fields for review."""

import csv
import sqlite3
from collections import Counter
from pathlib import Path

from provenance import decode_field_sources


ROOT = Path(__file__).resolve().parent
FIELDS = (
    ("population_trend", "တွေ့ရှိမှု အခြေအနေ"),
    ("myanmar_population", "မြန်မာနိုင်ငံ အကောင်ရေ"),
    ("global_population", "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ"),
    ("wild_population_my", "တောရိုင်း အကောင်ရေ အသေးစိတ်"),
)
MD_PATH = ROOT / "docs" / "animal_population_fields_with_data.md"
CSV_PATH = ROOT / "docs" / "animal_population_fields_after_cleanup.csv"


def main():
    conn = sqlite3.connect(ROOT / "wildlife.db")
    conn.row_factory = sqlite3.Row
    try:
        animals = []
        csv_rows = []
        counts = Counter()
        for animal in conn.execute("SELECT * FROM animals ORDER BY id"):
            present = []
            sources = decode_field_sources(animal["field_sources"])
            for field, label in FIELDS:
                value = animal[field]
                if value is None or not str(value).strip():
                    continue
                present.append((field, label))
                counts[field] += 1
                csv_rows.append((animal["id"], animal["name_my"], animal["name_en"],
                                 animal["scientific_name"] or "", label, field,
                                 str(value), "ရှိ" if sources.get(field) else "မရှိ"))
            if present:
                animals.append((animal, present))
    finally:
        conn.close()

    lines = [
        "# အကောင်ရေဆိုင်ရာ field များတွင် data ရှိသော တိရစ္ဆာန်များ",
        "",
        "Data ရှိသည်ဆိုသည်မှာ field ထဲတွင် စာသားဖြည့်ထားသည်ဟုသာ ဆိုလိုသည်။ "
        "အကောင်ရေကိန်းဂဏန်း သို့မဟုတ် source အတည်ပြုချက် ရှိကြောင်း မဆိုလိုပါ။ "
        "သိရှိပြီးသော ‘မသိရသေးပါ’ သက်သက်စာသားနှင့် စိစစ်တွေ့ရှိသော မှားယွင်းအချက်များကို "
        "ဖယ်ရှားထားပြီး၊ အသေးစိတ်ကို removed_animal_population_fields.json တွင် ကြည့်နိုင်သည်။",
        "လက်ရှိစာရင်း၏ CSV ဖိုင်: animal_population_fields_after_cleanup.csv။",
        "",
        f"- တိရစ္ဆာန်: **{len(animals)} ကောင်**",
    ]
    for field, label in FIELDS:
        lines.append(f"- {label} (`{field}`): **{counts[field]} ကောင်**")
    lines.extend(["", "| ID | တိရစ္ဆာန် | အင်္ဂလိပ်အမည် | Data ရှိသော field |", "| ---: | --- | --- | --- |"])
    for animal, present in animals:
        field_names = ", ".join(f"{label} (`{field}`)" for field, label in present)
        lines.append(f"| {animal['id']} | {animal['name_my'].replace('|', '/')} | "
                     f"{animal['name_en'].replace('|', '/')} | {field_names} |")
    lines.append("")
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("animal_id", "name_my", "name_en", "scientific_name",
                         "field_label", "field_key", "field_value", "field_source_link"))
        writer.writerows(csv_rows)
    print(f"{len(animals)} animals, {len(csv_rows)} populated field values")
    print(MD_PATH)
    print(CSV_PATH)


if __name__ == "__main__":
    main()
