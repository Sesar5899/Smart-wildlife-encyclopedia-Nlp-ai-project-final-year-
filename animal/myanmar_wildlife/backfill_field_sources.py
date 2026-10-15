"""One-time, conservative field provenance backfill for the local catalog."""

import json
import sqlite3
from pathlib import Path

from provenance import (
    decode_field_sources, imported_field_sources, portal_field_sources,
)


def backfill(database=None):
    database = Path(database or Path(__file__).with_name("wildlife.db"))
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(animals)")}
        if "field_sources" not in columns:
            conn.execute("ALTER TABLE animals ADD COLUMN field_sources TEXT")
        records = fields = 0
        for row in conn.execute("SELECT * FROM animals").fetchall():
            verified = portal_field_sources(dict(row))
            verified.update(imported_field_sources(dict(row)))
            if not verified:
                continue
            existing = decode_field_sources(row["field_sources"])
            verified.update(existing)
            if verified == existing:
                continue
            conn.execute(
                "UPDATE animals SET field_sources = ? WHERE id = ?",
                (json.dumps(verified, ensure_ascii=False), row["id"]),
            )
            records += 1
            fields += len(verified) - len(existing)
        conn.commit()
        return records, fields
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    records, fields = backfill()
    print(f"Verified source provenance: {fields} fields across {records} animals")
