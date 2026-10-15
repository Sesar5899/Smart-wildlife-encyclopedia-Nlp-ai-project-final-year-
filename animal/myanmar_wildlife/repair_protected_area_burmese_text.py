"""Sync reviewed protected-area Burmese corrections to existing DB rows.

The canonical source is data/protected_areas.json. Only the explicitly reviewed
fields are copied. Non-standard ဥ်/ဉ် forms and the known တိရိစ္ဆာန် issue are
intentionally outside this remediation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data" / "protected_areas.json"
DB_PATH = ROOT / "wildlife.db"

FIELDS_BY_SLUG = {
    "alaungdaw_kathapa_national_park_protected": [
        "designation_mm",
        "description_mm",
        "natural_resources_mm",
    ],
    "bat_cave_geo_physically_significant_reserve_protected": [
        "description_mm",
        "natural_resources_mm",
    ],
    "chatthin_wildlife_sanctuary_protected": ["natural_resources_mm"],
    "eimawbon_national_park_protected": ["natural_resources_mm"],
    "hkakaborazi_national_park_protected": [
        "designation_mm",
        "natural_resources_mm",
    ],
    "hlawga_wildlife_park_protected": ["tourism_mm"],
    "hponkanrazi_wildlife_sanctuary_protected": [
        "description_mm",
        "natural_resources_mm",
    ],
    "htamanthi_wildlife_sanctuary_protected": [
        "designation_mm",
        "natural_resources_mm",
    ],
    "indawgyi_wildlife_sanctuary_protected": [
        "designation_mm",
        "natural_resources_mm",
    ],
    "inlay_lake_wildlife_sanctuary_protected": [
        "designation_mm",
        "description_mm",
        "tourism_mm",
    ],
    "kyeeyeyan_taung_national_park_protected": ["tourism_mm"],
    "mainmahla_kyun_wildlife_sanctuary_protected": ["designation_mm"],
    "natmataung_national_park_protected": ["designation_mm"],
    "rakhine_yoma_elephant_range_protected": ["description_mm"],
    "sar_munm_national_park_protected": ["description_mm"],
    "shwe_u_daung_wildlife_sanctuary_protected": ["natural_resources_mm"],
    "shwesettaw_wildlife_sanctuary_protected": ["natural_resources_mm"],
}

FORBIDDEN_TEXT = (
    "အာစီယံ",
    "ဝါးမျိးစိတ်",
    "အခွင့်အလန်း",
    "အမျိူးမျိုး",
    "ကုန်းနေရေနေနေ",
    "ဥယျာက်",
    "တည်မှီး",
    "တောတိုနှင့်",
    "တဆက်တည်း",
    "ထင်းရူးတော",
    "အပြင်မျိုးစိတ်",
    "ဆေးဘက်ဝင်",
    "အသင့်အတင်",
    "ဖွံဖြိုးရေး",
    "ပါ၀င်",
    "ထိန်းသိမ်းရေးနယ်မြတစ်ခု",
    "အင်တိုင်းသစ်တော သစ်တောများ",
)

REPEATED_HLAWGA_SENTENCE = (
    "လှော်ကားဥယျာဉ်သည် ရန်ကုန်မြို့နှင့် နီးကပ်သောကြောင့် "
    "ပြည်တွင်းခရီးသွားများနှင့် သဘာဝလေ့လာလိုသူများအတွက် "
    "လူကြိုက်များသော နေရာတစ်ခု ဖြစ်သည်။"
)


def main() -> None:
    records = json.loads(SOURCE_PATH.read_text(encoding="utf-8-sig"))
    source_by_slug = {record["slug"]: record for record in records}

    for slug, fields in FIELDS_BY_SLUG.items():
        for field in fields:
            value = str(source_by_slug[slug].get(field) or "")
            matches = [text for text in FORBIDDEN_TEXT if text in value]
            if matches:
                raise ValueError(f"Uncorrected text remains in {slug}.{field}: {matches}")
    if source_by_slug["hlawga_wildlife_park_protected"]["tourism_mm"].count(
        REPEATED_HLAWGA_SENTENCE
    ) != 1:
        raise ValueError("Hlawga tourism sentence was not reduced to one copy")

    updated_records = 0
    updated_fields = 0
    missing_records: list[str] = []

    with sqlite3.connect(DB_PATH) as connection:
        for slug, fields in FIELDS_BY_SLUG.items():
            row = connection.execute(
                "SELECT data_json FROM catalog_records WHERE kind = ? AND slug = ?",
                ("protected_areas", slug),
            ).fetchone()
            if row is None:
                missing_records.append(slug)
                continue

            db_record = json.loads(row[0])
            for field in fields:
                db_record[field] = source_by_slug[slug][field]
                updated_fields += 1

            connection.execute(
                "UPDATE catalog_records SET data_json = ? WHERE kind = ? AND slug = ?",
                (
                    json.dumps(db_record, ensure_ascii=False),
                    "protected_areas",
                    slug,
                ),
            )
            updated_records += 1

    print(f"Updated database records: {updated_records}")
    print(f"Updated database fields: {updated_fields}")
    print("Missing database records: " + (", ".join(missing_records) or "none"))


if __name__ == "__main__":
    main()
