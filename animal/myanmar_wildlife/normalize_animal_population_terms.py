"""Correct human population wording in published animal text fields."""

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "animal_population_wording_changes.json"
REPLACEMENTS = {
    "လူဦးရေ": "အကောင်ရေ",
    "လူဦးရေ": "အကောင်ရေ",
    "လူဉီးရေ": "အကောင်ရေ",
    "အရွယ်မရောက်သေးသူများ": "အရွယ်မရောက်သေးသောအကောင်များ",
    "အရွယ်မရောက်သေးသူ": "အရွယ်မရောက်သေးသောအကောင်",
    "အရွယ်ရောက်ပြီးသူများ": "အရွယ်ရောက်ပြီးသောအကောင်များ",
    "အရွယ်ရောက်ပြီးသူ": "အရွယ်ရောက်ပြီးသောအကောင်",
    "ကိုယ်ဝန်ဆောင်ကာလ": "သန္ဓေတည်ကာလ",
    "မွေးကင်းစအကောင်ပေါက်လေးများ": "ဥမှပေါက်ခါစ လိပ်သားပေါက်များ",
    "မွေးကင်းစကောင်": "မွေးခါစ သားငယ်",
    "ဆင်ကလေး": "ဆင်သားပေါက်",
    "ကလေးဆင်": "ဆင်သားပေါက်",
    "ကလေးအကောင်များ": "သားပေါက်များ",
    "လူမှုရေးကောင်းမွန်သော သတ္တဝါများ": "အုပ်စုဖွဲ့နေထိုင်တတ်သော တိရစ္ဆာန်များ",
    "အလွန်လူမှုရေးကောင်းသော သတ္တဝါ": "အုပ်စုဖွဲ့နေထိုင်တတ်သော တိရစ္ဆာန်",
    "လူမှုရေးအလွန်ကောင်းသော သတ္တဝါ": "အုပ်စုဖွဲ့နေထိုင်တတ်သော တိရစ္ဆာန်",
}
EXCLUDED = {"portal_data", "field_sources"}


def main():
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        text_fields = [column[1] for column in conn.execute("PRAGMA table_info(animals)")
                       if column[2].upper().startswith("TEXT") and column[1] not in EXCLUDED]
        for animal in conn.execute("SELECT * FROM animals ORDER BY id").fetchall():
            for field in text_fields:
                old = animal[field]
                if not old:
                    continue
                new = old
                for wrong, right in REPLACEMENTS.items():
                    new = new.replace(wrong, right)
                if new != old:
                    changes.append({"animal_id": animal["id"], "name_en": animal["name_en"],
                                    "field": field, "old_value": old, "new_value": new})
        # Save the old values before modifying the database so the edit is reversible.
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if changes:
            LOG.write_text(json.dumps(prior + changes, ensure_ascii=False, indent=2), encoding="utf-8")
        with conn:
            for change in changes:
                result = conn.execute(
                    f"UPDATE animals SET {change['field']} = ? WHERE id = ? AND {change['field']} = ?",
                    (change["new_value"], change["animal_id"], change["old_value"]),
                )
                if result.rowcount != 1:
                    raise RuntimeError(f"Concurrent change for animal {change['animal_id']}")
    finally:
        conn.close()
    print(f"Corrected {len(changes)} fields across {len({x['animal_id'] for x in changes})} animals")
    print(LOG)


if __name__ == "__main__":
    main()
