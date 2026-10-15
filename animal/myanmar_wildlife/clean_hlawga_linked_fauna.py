"""Sync Hlawga's visible fauna fields to its explicit animal relationships."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data" / "protected_areas.json"
DB_PATH = ROOT / "wildlife.db"
SLUG = "hlawga_wildlife_park_protected"
FIELDS = ("species_fauna", "species_fauna_mm", "other_fauna", "other_fauna_mm")

EXPECTED = {
    "species_fauna": "Macaca_mulatta_Rhesus_Macaque,Felis_chaus_Jungle_Cat",
    "species_fauna_mm": "မျောက်စပ်,တောကြောင်",
    "other_fauna": None,
    "other_fauna_mm": None,
}


def main() -> None:
    records = json.loads(SOURCE_PATH.read_text(encoding="utf-8-sig"))
    source_record = next(record for record in records if record["slug"] == SLUG)
    actual = {field: source_record.get(field) for field in FIELDS}
    if actual != EXPECTED:
        raise ValueError(f"Unexpected Hlawga source values: {actual}")

    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT data_json FROM catalog_records WHERE kind = ? AND slug = ?",
            ("protected_areas", SLUG),
        ).fetchone()
        if row is None:
            raise ValueError("Hlawga protected-area database record is missing")

        db_record = json.loads(row[0])
        for field in FIELDS:
            db_record[field] = source_record[field]
        connection.execute(
            "UPDATE catalog_records SET data_json = ? WHERE kind = ? AND slug = ?",
            (json.dumps(db_record, ensure_ascii=False), "protected_areas", SLUG),
        )

    print("Updated database records: 1")
    print("Updated database fields: 4")


if __name__ == "__main__":
    main()
