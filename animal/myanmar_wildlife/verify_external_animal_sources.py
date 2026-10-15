"""Attach independently checked official species-list citations to animal fields.

Each entry below is a taxon printed in Forest Department Notification 690/2020.
The line number is an audit locator in the Trade Portal's 44-page PDF text.
Nothing is attributed from a generic source page or a name-only search hit.
"""

import json
import sqlite3
from pathlib import Path

from provenance import decode_field_sources, decode_sources


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "wildlife.db"
OFFICIAL_PDF = "https://www.myanmartradeportal.gov.mm/uploads/legals/2021/6/Notification%20690-2021.pdf"

# id: (scientific name in the PDF, PDF text line, official category)
VERIFIED_LISTINGS = {
    2: ("Elephas maximus", 37, "Totally protected"),
    4: ("Ursus thibetanus", 13, "Totally protected"),
    5: ("Catopuma temminckii", 36, "Totally protected"),
    7: ("Bos javanicus", 61, "Totally protected"),
    12: ("Ephippiorhynchus asiaticus", 579, "Totally protected"),
    21: ("Neofelis nebulosa", 28, "Totally protected"),
    24: ("Rucervus eldii", 58, "Totally protected"),
    25: ("Prionailurus viverrinus", 34, "Totally protected"),
    27: ("Leptoptilos dubius", 580, "Totally protected"),
    29: ("Pavo muticus", 128, "Totally protected"),
    37: ("Felis chaus", 35, "Totally protected"),
    40: ("Hylobates lar", 5, "Totally protected"),
    42: ("Panthera pardus", 29, "Totally protected"),
    43: ("Prionailurus bengalensis", 861, "Normally protected"),
    48: ("Helarctos malayanus", 12, "Totally protected"),
    49: ("Tapirus indicus", 42, "Totally protected"),
    67: ("Gyps tenuirostris", 531, "Totally protected"),
    70: ("Pelecanus philippensis", 582, "Totally protected"),
    71: ("Ciconia stormi", 578, "Totally protected"),
    74: ("Panthera tigris", 30, "Totally protected"),
    76: ("Ardea insignis", 573, "Totally protected"),
    93: ("Cuon alpinus", 9, "Totally protected"),
    94: ("Ailurus fulgens", 11, "Totally protected"),
    97: ("Lutrogale perspicillata", 19, "Totally protected"),
    98: ("Lutra lutra", 15, "Totally protected"),
    99: ("Lutra sumatrana", 18, "Totally protected"),
    103: ("Dicerorhinus sumatrensis", 38, "Totally protected"),
    108: ("Muntiacus gongshanensis", 53, "Totally protected"),
    109: ("Capricornis sumatraensis", 64, "Totally protected"),
    112: ("Budorcas taxicolor", 62, "Totally protected"),
    131: ("Orcaella brevirostris", 71, "Totally protected"),
    132: ("Neophocaena phocaenoides", 83, "Totally protected"),
    139: ("Rhodonessa caryophyllacea", 138, "Totally protected"),
    143: ("Caloenas nicobarica", 352, "Totally protected"),
    146: ("Milvus migrans", 522, "Totally protected"),
    150: ("Athene brama", 348, "Totally protected"),
    157: ("Coracias benghalensis", 945, "Normally protected"),
    165: ("Sphenocichla roberti", 680, "Totally protected"),
    172: ("Chrysococcyx maculatus", 1404, "Seasonally protected"),
    174: ("Cacomantis merulinus", 1402, "Seasonally protected"),
    175: ("Megalaima haemacephala", 940, "Normally protected"),
    180: ("Lanius schach", 1438, "Seasonally protected"),
    181: ("Eurystomus orientalis", 946, "Normally protected"),
    204: ("Hystrix brachyura", 899, "Normally protected"),
    210: ("Daboia siamensis", 765, "Totally protected"),
    211: ("Naja kaouthia", 762, "Totally protected"),
    212: ("Varanus salvator", 1363, "Normally protected"),
}

# Species names directly printed in the notification, where this audit does
# not infer or populate any legal-status field on the project record.
VERIFIED_NAMES_ONLY = {
    8: ("Esacus neglectus", "Beach Thick-knee", 405),
    183: ("Muntiacus putaoensis", "Leaf Muntjac", 52),
    184: ("Rusa unicolor", "Sambar", 903),
    192: ("Vulpes vulpes", "Red Fox", 10),
    194: ("Rhinoceros sondaicus", "Lesser One-horned Rhinoceros", 40),
    207: ("Viverricula indica", "Small Indian Civet", 857),
}
VERIFIED_GBIF_IUCN = {
    97: ("Lutrogale perspicillata", "VU", "2433686"),
    98: ("Lutra lutra", "NT", "2433753"),
    99: ("Lutra sumatrana", "EN", "2433752"),
}

STATUS_MY = {
    "Totally protected": "အပြည့်အဝ ကာကွယ်ထားသော မျိုးစိတ်",
    "Normally protected": "သာမန် ကာကွယ်ထားသော မျိုးစိတ်",
    "Seasonally protected": "ရာသီအလိုက် ကာကွယ်ထားသော မျိုးစိတ်",
}
DIRECT_BASIS = "အမိန့်ကြော်ငြာစာ စာရင်းတွင် မျိုးစိတ်အလိုက် တိုက်ရိုက် ပါဝင်သည်။"


def apply():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    changed_fields = 0
    corrected_records = []
    try:
        with conn:
            for animal_id, (taxon, line, category) in VERIFIED_LISTINGS.items():
                row = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                if row is None or row["scientific_name"] != taxon:
                    raise ValueError(f"Species identity changed for ID {animal_id}: {taxon}")
                if not ((line < 839 and category == "Totally protected") or
                        (839 <= line < 1369 and category == "Normally protected") or
                        (line >= 1369 and category == "Seasonally protected")):
                    raise ValueError(f"PDF section mismatch for ID {animal_id}")

                original_status = row["protection_status_en"]
                if animal_id in (43, 76, 165, 175, 181):
                    # The project classified these three as totally/seasonally
                    # protected; the official list explicitly places them in
                    # its normally protected section.
                    if original_status not in ("Totally protected", "Normally protected",
                                               "Seasonally protected", category):
                        raise ValueError(f"Unexpected prior status for ID {animal_id}")
                    if original_status != category:
                        corrected_records.append(animal_id)
                elif original_status not in (
                    category, category + " species",
                    "Completely protected species" if category == "Totally protected" else None,
                ):
                    raise ValueError(f"Status differs from PDF for ID {animal_id}")

                if "၆၉၀/၂၀၂၀" not in (row["protection_law_my"] or ""):
                    raise ValueError(f"Unexpected law for ID {animal_id}")
                basis = (DIRECT_BASIS if animal_id in (12, 27, 67, 71, 76, 146, 150, 165, 180)
                         else row["protection_basis_my"])
                if "တိုက်ရိုက်" not in (basis or ""):
                    raise ValueError(f"Unexpected protection basis for ID {animal_id}")

                sources = json.loads(row["source_urls"] or "[]")
                if OFFICIAL_PDF not in decode_sources(dict(row)):
                    sources.append({"label": "မြန်မာနိုင်ငံ သစ်တောဦးစီးဌာန — အမိန့်ကြော်ငြာစာ ၆၉၀/၂၀၂၀", "url": OFFICIAL_PDF})

                mapping = decode_field_sources(row["field_sources"])
                for field in ("scientific_name", "protection_status_my", "protection_status_en",
                              "protection_law_my", "protection_basis_my"):
                    if not row[field] and field != "protection_status_en":
                        continue
                    if OFFICIAL_PDF not in mapping.get(field, []):
                        mapping.setdefault(field, []).append(OFFICIAL_PDF)
                        changed_fields += 1

                conn.execute(
                    "UPDATE animals SET protection_status_my = ?, protection_status_en = ?, "
                    "protection_basis_my = ?, "
                    "source_urls = ?, field_sources = ? WHERE id = ?",
                    (STATUS_MY[category], category, basis,
                     json.dumps(sources, ensure_ascii=False),
                     json.dumps(mapping, ensure_ascii=False), animal_id),
                )
    finally:
        conn.close()
    return changed_fields, corrected_records


def link_gbif_taxonomy():
    """Add exact GBIF taxon pages for unchanged order/family values in the cache."""
    cached = {}
    for filename, taxon_field, prefix in (
        ("protected_mammals_2020_crawl.json", "scientific_name", "protected_mammal_2020_"),
        ("protected_birds_2020_crawl.json", "taxon_name", "protected_bird_2020_"),
    ):
        records = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))["records"]
        for item in records:
            cached[(prefix, item["no"], item.get(taxon_field))] = item

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    added = 0
    try:
        with conn:
            for row in conn.execute("SELECT * FROM animals").fetchall():
                record_id = row["source_record_id"] or ""
                prefix = next((p for p in ("protected_mammal_2020_", "protected_bird_2020_")
                               if record_id.startswith(p)), None)
                if not prefix:
                    continue
                snapshot = json.loads(row["portal_data"] or "{}")
                item = cached.get((prefix, snapshot.get("protected_list_no"), row["scientific_name"]))
                if not item:
                    continue
                gbif = item.get("gbif") or {}
                scientific = row["scientific_name"] or ""
                accepted = gbif.get("accepted_name") or ""
                if (gbif.get("match_type") != "EXACT" or not gbif.get("gbif_key")
                        or not accepted.startswith(scientific + " ")):
                    continue
                mapping = decode_field_sources(row["field_sources"])
                pending_taxonomy = any(
                    row[field] and row[field] == gbif.get(key) and not mapping.get(field)
                    for field, key in (("species_order", "order"), ("species_family", "family"))
                )
                if not pending_taxonomy:
                    continue
                url = f"https://www.gbif.org/species/{gbif['gbif_key']}"
                if url in decode_sources(dict(row)):
                    continue
                sources = json.loads(row["source_urls"] or "[]")
                sources.append({"label": "GBIF Backbone Taxonomy", "url": url})
                conn.execute("UPDATE animals SET source_urls = ? WHERE id = ?",
                             (json.dumps(sources, ensure_ascii=False), row["id"]))
                added += 1
    finally:
        conn.close()
    return added


def link_exact_official_names():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    added = 0
    try:
        with conn:
            for animal_id, (scientific, english, _line) in VERIFIED_NAMES_ONLY.items():
                row = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                if not row or row["scientific_name"] != scientific:
                    raise ValueError(f"Species identity changed for ID {animal_id}")
                sources = json.loads(row["source_urls"] or "[]")
                if OFFICIAL_PDF not in decode_sources(dict(row)):
                    sources.append({"label": "မြန်မာနိုင်ငံ သစ်တောဦးစီးဌာန — အမိန့်ကြော်ငြာစာ ၆၉၀/၂၀၂၀", "url": OFFICIAL_PDF})
                mapping = decode_field_sources(row["field_sources"])
                for field in ("scientific_name", "name_en"):
                    if field == "name_en" and row[field].strip().casefold() != english.casefold():
                        continue
                    if OFFICIAL_PDF not in mapping.get(field, []):
                        mapping.setdefault(field, []).append(OFFICIAL_PDF)
                        added += 1
                conn.execute("UPDATE animals SET source_urls = ?, field_sources = ? WHERE id = ?",
                             (json.dumps(sources, ensure_ascii=False),
                              json.dumps(mapping, ensure_ascii=False), animal_id))
    finally:
        conn.close()
    return added


def link_verified_iucn_display():
    """Attribute the IUCN badges independently checked on exact GBIF pages."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    added = 0
    try:
        with conn:
            for animal_id, (scientific, status, key) in VERIFIED_GBIF_IUCN.items():
                row = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                url = f"https://www.gbif.org/species/{key}"
                if (not row or row["scientific_name"] != scientific
                        or row["global_iucn_status"] != status
                        or url not in decode_sources(dict(row))):
                    raise ValueError(f"IUCN evidence changed for ID {animal_id}")
                mapping = decode_field_sources(row["field_sources"])
                if url not in mapping.get("global_iucn_status", []):
                    mapping.setdefault("global_iucn_status", []).append(url)
                    conn.execute("UPDATE animals SET field_sources = ? WHERE id = ?",
                                 (json.dumps(mapping, ensure_ascii=False), animal_id))
                    added += 1
    finally:
        conn.close()
    return added


if __name__ == "__main__":
    linked, corrected = apply()
    gbif = link_gbif_taxonomy()
    names = link_exact_official_names()
    iucn = link_verified_iucn_display()
    print(f"Added {linked} official field citations to {len(VERIFIED_LISTINGS)} species; "
          f"added {names} exact name citations, {gbif} GBIF taxon pages and "
          f"{iucn} IUCN status citations; "
          f"corrected legal category for {corrected}.")
