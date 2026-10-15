"""Apply the reviewed Burmese text corrections to existing ecosystem DB rows.

The canonical source file is data/ecosystems.json. This script updates only the
explicitly reviewed fields below and leaves all other catalog data unchanged.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data" / "ecosystems.json"
DB_PATH = ROOT / "wildlife.db"

FIELDS_BY_SLUG = {
    "Ayeyarwady_delta_mangrove_forest": ["abiotic_environment_mm"],
    "Ayeyarwady_floodplain_wetlands": ["assessment_summary_mm"],
    "Bago_semi-evergreen_forest": ["distribution_mm"],
    "Central_Ayeyarwady_floodplain_grasslands": ["threats_main_mm"],
    "Central_dry_evergreen_riparian_forest": ["threats_main_mm"],
    "Coastal_mudflat": ["distribution_mm"],
    "Dry_zone_foothills_spiny_scrub": [
        "description_mm",
        "threats_mm",
        "threats_main_mm",
    ],
    "Indaing_forest": ["collapse_definition_mm"],
    "Kachin-Sagaing_low_elevation_evergreen_subtropical_rainforest": [
        "species_flora_mm"
    ],
    "Northern_semi-evergreen_forest": ["species_flora_mm"],
    "Rakhine_hills_bamboo_brake": ["description_mm"],
    "Sagaing_hills_pine_savanna": ["description_mm"],
    "Sha_thorny_scrub": ["threats_main_mm"],
}

FORBIDDEN_TEXT = (
    "နေ့စဥ်နေ့စဉ်",
    "ဒီရေတောများသည် ဒီရေတောများသည်",
    "ကျုးကျော်",
    "ပျံနှံ့",
    "ကမ်းရိုးတန်း၏ ကမ်းရိုးတန်း၏",
    "ခြုုံ",
    "မကြာခန",
    "သော််ကဖို",
    "ဆိိတ်နံပင်",
    "မြက်ပင် မျိုးစိတ်,မြက်ပင် မျိုးစိတ်",
    "အနှောက်အယှက်",
)


def main() -> None:
    source_records = json.loads(SOURCE_PATH.read_text(encoding="utf-8-sig"))
    source_by_slug = {record["slug"]: record for record in source_records}

    for slug, fields in FIELDS_BY_SLUG.items():
        record = source_by_slug[slug]
        for field in fields:
            value = str(record.get(field) or "")
            matches = [text for text in FORBIDDEN_TEXT if text in value]
            if matches:
                raise ValueError(f"Uncorrected text remains in {slug}.{field}: {matches}")

    updated_records = 0
    updated_fields = 0
    missing_records: list[str] = []

    with sqlite3.connect(DB_PATH) as connection:
        for slug, fields in FIELDS_BY_SLUG.items():
            row = connection.execute(
                "SELECT data_json FROM catalog_records WHERE kind = ? AND slug = ?",
                ("ecosystems", slug),
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
                    "ecosystems",
                    slug,
                ),
            )
            updated_records += 1

    print(f"Updated database records: {updated_records}")
    print(f"Updated database fields: {updated_fields}")
    print("Missing database records: " + (", ".join(missing_records) or "none"))


if __name__ == "__main__":
    main()
