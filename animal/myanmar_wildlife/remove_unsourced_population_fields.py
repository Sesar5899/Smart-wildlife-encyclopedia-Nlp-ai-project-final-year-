"""Remove the five explicitly requested unsourced population fields, with a log."""

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "removed_unsourced_population_fields.json"
EXPECTED = {
    (12, "global_population"): "360324081934628de5257b12486ad7b1c4e3931d204007773f81a726f6cdfe1d",
    (36, "wild_population_my"): "af258cac3f902f8965afd7f687b6d8a3fe768b71253c61f7fc49986cc4bb9d8a",
    (95, "population_trend"): "9a3b8879bcd4427aeff071b1c82b7ecb1c6e555fbf0e9c8ce090e1da1201d337",
    (184, "population_trend"): "22efa1ca3c13efd4cdf3f1d654d81d572636ce8faa6b5bc172c2b170533923cb",
    (207, "population_trend"): "306639345e8112d363907b0f34e713c3601721275dd2b0b7db909271795bfbd7",
}


def main():
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    completed = {(x["animal_id"], x["field"]) for x in prior}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        with conn:
            for (animal_id, field), digest in EXPECTED.items():
                if (animal_id, field) in completed:
                    continue
                animal = conn.execute("SELECT * FROM animals WHERE id=?", (animal_id,)).fetchone()
                if animal is None:
                    raise LookupError(animal_id)
                value = animal[field]
                if value is None or hashlib.sha256(value.encode("utf-8")).hexdigest() != digest:
                    raise ValueError(f"Unexpected value in animal {animal_id}, {field}")
                sources = json.loads(animal["field_sources"] or "{}")
                if sources.get(field):
                    raise ValueError(f"Field now has a source: animal {animal_id}, {field}")
                conn.execute(f"UPDATE animals SET {field}=NULL WHERE id=?", (animal_id,))
                changes.append({
                    "animal_id": animal_id, "name_my": animal["name_my"],
                    "name_en": animal["name_en"], "field": field, "removed_value": value,
                    "reason": "No field-level source link; removal requested by user.",
                })
            if changes:
                LOG.parent.mkdir(exist_ok=True)
                LOG.write_text(json.dumps(prior + changes, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        conn.close()
    print(f"Removed {len(changes)} unsourced fields")
    print(LOG)


if __name__ == "__main__":
    main()
