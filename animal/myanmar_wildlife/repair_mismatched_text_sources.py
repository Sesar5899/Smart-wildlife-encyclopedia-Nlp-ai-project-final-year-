"""Repair two live animal records that inherited another species' sources.

The old crawl files are import snapshots. This only updates the published
SQLite records, while preserving the editor's own species descriptions.
"""

import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).with_name("wildlife.db")
LAW = "https://www.myanmartradeportal.gov.mm/uploads/legals/2021/6/Notification%20690-2021.pdf"
MDD_BLACK = "https://www.mammaldiversity.org/taxon/1006348/"
MDD_HIMALAYAN = "https://www.mammaldiversity.org/taxon/1006349/"
GBIF_BLACK = "https://www.gbif.org/species/2440990"
GBIF_HIMALAYAN = "https://www.gbif.org/species/4262218"
GBIF_MONARCH = "https://www.gbif.org/species/2486625"


REPAIRS = {
    106: {
        "expected_scientific": "Moschus leucogaster (Himalayan Musk Deer), Moschus fuscus (Black Musk Deer)",
        "old_key": "protected_mammal_2020_muntiacus_feae",
        "source_record_id": "curated_moschus_fuscus_leucogaster",
        "source_url": MDD_BLACK,
        "source_name": "Mammal Diversity Database",
        "source_urls": [
            {"label": "Mammal Diversity Database — Black Musk-deer", "url": MDD_BLACK},
            {"label": "Mammal Diversity Database — Himalayan Musk-deer", "url": MDD_HIMALAYAN},
            {"label": "GBIF — Moschus fuscus", "url": GBIF_BLACK},
            {"label": "GBIF — Moschus leucogaster", "url": GBIF_HIMALAYAN},
            {"label": "မြန်မာနိုင်ငံ ကာကွယ်ထားသော တောရိုင်းတိရစ္ဆာန်များစာရင်း ၆၉၀/၂၀၂၀", "url": LAW},
        ],
        "field_sources": {
            "name_en": [MDD_BLACK, MDD_HIMALAYAN],
            "scientific_name": [MDD_BLACK, MDD_HIMALAYAN],
            "species_order": [GBIF_BLACK, GBIF_HIMALAYAN],
            "species_family": [GBIF_BLACK, GBIF_HIMALAYAN],
            "global_iucn_status": [MDD_BLACK, MDD_HIMALAYAN],
            "distribution_my": [MDD_BLACK, MDD_HIMALAYAN],
            "protection_status_my": [LAW],
            "protection_status_en": [LAW],
            "protection_law_my": [LAW],
            "protection_basis_my": [LAW],
        },
        "fields": {
            "species_family": "Moschidae",
            # This field is the Myanmar IUCN category; EN was copied from the
            # global status and is not supported as a national assessment.
            "conservation_status": None,
            "distribution_my": (
                "Himalayan Musk Deer (Moschus leucogaster) ကို ဘူတန်၊ အိန္ဒိယ၊ "
                "နီပေါနိုင်ငံတို့တွင် တွေ့ရှိရသည်။ Black Musk Deer "
                "(Moschus fuscus) ကို ဘူတန်၊ တရုတ်၊ အိန္ဒိယ၊ မြန်မာနှင့် "
                "နီပေါနိုင်ငံတို့တွင် တွေ့ရှိရသည်။"
            ),
            # This paragraph described Tanintharyi muntjacs, not musk deer.
            "conservation_actions_my": None,
            "protection_status_my": "Moschus fuscus — အပြည့်အဝ ကာကွယ်ထားသော မျိုးစိတ်",
            "protection_status_en": "Totally protected",
            "protection_basis_my": (
                "အမိန့်ကြော်ငြာစာအမှတ် ၆၉၀/၂၀၂၀ ၏ အပြည့်အဝ "
                "ကာကွယ်ထားသော နို့တိုက်သတ္တဝါစာရင်း အမှတ် ၅၆ တွင် "
                "Moschus fuscus (Black Musk-deer) ကို ဖော်ပြထားသည်။ "
                "Moschus leucogaster အတွက် ဤစာရင်းဝင်မှုကို မဆိုလိုပါ။"
            ),
        },
    },
    145: {
        "expected_scientific": "Hypothymis azurea",
        "old_key": "protected_bird_2020_totally_11_irena_puella",
        "source_record_id": "curated_hypothymis_azurea",
        "source_url": GBIF_MONARCH,
        "source_name": "GBIF Backbone Taxonomy",
        "source_urls": [
            {"label": "GBIF — Hypothymis azurea", "url": GBIF_MONARCH},
            {"label": "မြန်မာနိုင်ငံ ကာကွယ်ထားသော တောရိုင်းတိရစ္ဆာန်များစာရင်း ၆၉၀/၂၀၂၀", "url": LAW},
        ],
        "field_sources": {
            "name_en": [GBIF_MONARCH, LAW],
            "scientific_name": [GBIF_MONARCH, LAW],
            "species_order": [GBIF_MONARCH],
            "species_family": [GBIF_MONARCH],
            "protection_status_my": [LAW],
            "protection_status_en": [LAW],
            "protection_law_my": [LAW],
            "protection_basis_my": [LAW],
        },
        "fields": {
            "species_family": "Monarchidae",
            "protection_status_my": "ရာသီအလိုက် ကာကွယ်ထားသော မျိုးစိတ်",
            "protection_status_en": "Seasonally protected",
            "protection_basis_my": (
                "အမိန့်ကြော်ငြာစာအမှတ် ၆၉၀/၂၀၂၀ ၏ ရာသီအလိုက် "
                "ကာကွယ်ထားသော ငှက်စာရင်း အမှတ် ၅၁ တွင် Hypothymis azurea "
                "(Black-naped Monarch) ကို ဖော်ပြထားသည်။ "
                "ကာကွယ်ကာလမှာ မတ်လ ၁၅ ရက်မှ စက်တင်ဘာလ ၃၀ ရက်အထိ ဖြစ်သည်။"
            ),
            # The inherited cover depicts Irena puella, a different bird.
            "image_url": None,
        },
    },
}


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    changed = []
    try:
        with conn:
            for animal_id, repair in REPAIRS.items():
                row = conn.execute(
                    "SELECT scientific_name, source_record_id FROM animals WHERE id = ?",
                    (animal_id,),
                ).fetchone()
                if row is None or row["scientific_name"] != repair["expected_scientific"]:
                    raise ValueError(f"Animal {animal_id} identity changed; inspect manually")
                if row["source_record_id"] == repair["source_record_id"]:
                    continue
                if row["source_record_id"] != repair["old_key"]:
                    raise ValueError(f"Animal {animal_id} provenance changed; inspect manually")

                fields = {
                    **repair["fields"],
                    "source_record_id": repair["source_record_id"],
                    "source_url": repair["source_url"],
                    "source_name": repair["source_name"],
                    "source_urls": json.dumps(repair["source_urls"], ensure_ascii=False),
                    "field_sources": json.dumps(repair["field_sources"], ensure_ascii=False),
                    "linked_name": None,
                    "portal_data": None,
                    "crawled_at": None,
                    "source_image_url": None,
                    "image_credit": None,
                }
                columns = ", ".join(f"{name} = ?" for name in fields)
                conn.execute(
                    f"UPDATE animals SET {columns} WHERE id = ?",
                    [*fields.values(), animal_id],
                )
                conn.execute(
                    "UPDATE chat_messages SET animal_key = ? WHERE animal_key = ?",
                    (repair["source_record_id"], repair["old_key"]),
                )
                conn.execute(
                    "DELETE FROM embedding_passages WHERE content_kind = 'animal' AND record_key = ?",
                    (repair["old_key"],),
                )
                changed.append(animal_id)
    finally:
        conn.close()
    print(f"Corrected text sources for animal IDs: {changed}")


if __name__ == "__main__":
    main()
