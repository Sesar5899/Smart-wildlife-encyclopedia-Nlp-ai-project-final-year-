"""Find human-specific wording in published animal records."""

import sqlite3
from pathlib import Path


DB = Path(__file__).resolve().parent / "wildlife.db"
TERMS = (
    "လူဦးရေ", "လူဦးရေ", "လူဉီးရေ", "မိန်းမ", "အမျိုးသမီး",
    "ကလေး", "လူမှုရေး", "မွေးကင်းစ", "ကိုယ်ဝန်", "လင်မယား",
    "အရွယ်မရောက်သေးသူ", "အရွယ်ရောက်ပြီးသူ", "မိဘ", "မိခင်",
)
SKIP_COLUMNS = {"portal_data", "field_sources", "sources", "image_urls"}


def main():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    columns = [row[1] for row in db.execute("PRAGMA table_info(animals)")
               if row[2].upper().startswith("TEXT") and row[1] not in SKIP_COLUMNS]
    records = db.execute("SELECT * FROM animals ORDER BY id").fetchall()
    print(f"Reviewed {len(records)} animal records, {len(columns)} published text columns")
    for animal in records:
        for column in columns:
            value = animal[column] or ""
            for term in TERMS:
                start = 0
                while (start := value.find(term, start)) != -1:
                    context = value[max(0, start - 35):start + len(term) + 45].replace("\n", " ")
                    print(f"{animal['id']} | {animal['name_en']} | {column} | {term} | {context}")
                    start += len(term)


if __name__ == "__main__":
    main()
