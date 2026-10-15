"""List populated animal editor fields in sections 02–04 without linked sources."""

import csv
import sqlite3
from collections import Counter
from pathlib import Path

from provenance import decode_field_sources


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "wildlife.db"
MD_PATH = ROOT / "docs" / "animal_section_source_gaps.md"
CSV_PATH = ROOT / "docs" / "animal_section_source_gaps.csv"

# Field order and labels follow templates/admin/animal_form.html.
SECTIONS = (
    ("02. ဖော်ပြချက်နှင့် နေထိုင်မှု", (
        ("description_my", "အကျဉ်းချုပ် ဖော်ပြချက်"),
        ("physical_description_my", "ရုပ်သွင်ပြင် ဖော်ပြချက်"),
        ("habitat_my", "နေထိုင်ရာ"),
        ("diet_my", "အစာစားနည်း"),
        ("distribution_my", "ဖြန့်ကျက်တည်ရှိမှု"),
        ("behaviour_my", "အနေအထိုင်နှင့် အပြုအမူ"),
        ("size_my", "အရွယ်အစား"),
        ("lifespan_my", "သက်တမ်း"),
        ("region_my", "တွေ့ရှိရသော ဒေသ"),
        ("fun_facts_my", "ထူးခြားအချက်များ"),
    )),
    ("03. ထိန်းသိမ်းရေးနှင့် မျိုးခွဲ", (
        ("conservation_status", "မြန်မာ IUCN အဆင့်"),
        ("global_iucn_status", "ကမ္ဘာလုံးဆိုင်ရာ IUCN အဆင့်"),
        ("population_trend", "တွေ့ရှိမှု အခြေအနေ"),
        ("myanmar_population", "မြန်မာနိုင်ငံ အကောင်ရေ"),
        ("global_population", "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ"),
        ("species_order", "Order"),
        ("species_family", "Family"),
        ("iucn_justification_my", "IUCN အကဲဖြတ် အကြောင်းပြချက်"),
        ("wild_population_my", "တောရိုင်း အကောင်ရေ အသေးစိတ်"),
        ("threats_my", "ရှင်သန်ရေး ခြိမ်းခြောက်မှုများ"),
        ("conservation_actions_my", "ထိန်းသိမ်းရေး လုပ်ဆောင်ချက်များ"),
        ("conservation_needs_my", "ထိန်းသိမ်းရေး လိုအပ်ချက်များ"),
        ("use_trade_my", "အသုံးပြုမှုနှင့် ကုန်သွယ်မှု"),
        ("protected_areas_my", "တွေ့ရှိရသော ကာကွယ်ထိန်းသိမ်းနယ်မြေများ"),
        ("ecosystems_my", "ဆက်စပ် ဂေဟစနစ်များ"),
        ("kba_my", "အဓိက ဇီဝမျိုးစုံမျိုးကွဲ နယ်မြေများ (KBA)"),
    )),
    ("04. ဥပဒေအရ ကာကွယ်ထားမှု", (
        ("protection_status_my", "ကာကွယ်မှုအဆင့် (မြန်မာ)"),
        ("protection_status_en", "ကာကွယ်မှုအဆင့် (English)"),
        ("protection_law_my", "ဥပဒေ / စာရင်း ကိုးကား"),
        ("protection_basis_my", "ကာကွယ်ရသည့် အကြောင်းရင်း"),
    )),
)


def collect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        results = []
        for animal in conn.execute("SELECT * FROM animals ORDER BY id"):
            sources = decode_field_sources(animal["field_sources"])
            gaps = []
            for section, fields in SECTIONS:
                for field, label in fields:
                    value = animal[field]
                    if value is not None and str(value).strip() and not sources.get(field):
                        gaps.append((section, field, label))
            if gaps:
                results.append((animal, gaps))
        return results
    finally:
        conn.close()


def write_reports(results):
    section_counts = Counter(section for _, gaps in results for section, _, _ in gaps)
    total = sum(section_counts.values())
    lines = [
        "# တိရစ္ဆာန်အလိုက် source ချိတ်ရန်ကျန်သော field များ — 02/03/04",
        "",
        "လက်ရှိ `wildlife.db` ကို အခြေခံထားသည်။ Data ဖြည့်ထားပြီး `field_sources` တွင် "
        "ထို field အတွက် URL မရှိသေးသည့်အချက်များကိုသာ ဖော်ပြသည်။ "
        "Source မချိတ်ရသေးခြင်းသည် data မှားကြောင်း အတည်ပြုခြင်း မဟုတ်ပါ။",
        "",
        f"- စာရင်းဝင်တိရစ္ဆာန်: **{len(results)} ကောင်**",
        f"- Source ချိတ်ရန်ကျန်သော field: **{total} ခု**",
    ]
    for section, _ in SECTIONS:
        lines.append(f"- {section}: **{section_counts[section]} ခု**")
    lines.extend([
        "",
        "အချက်အလက်မဖြည့်ရသေးသော field များကို မရေတွက်ပါ။ "
        "04 အောက်ရှိ `taxon_rank` သည် မှတ်တမ်းအဆင့် metadata၊ `image_credit` သည် ဓာတ်ပုံခရက်ဒစ်ဖြစ်သောကြောင့် "
        "field source ချိတ်ရန်စာရင်းတွင် မပါဝင်ပါ။",
        "",
    ])
    for animal, gaps in results:
        name = f"{animal['name_my']} / {animal['name_en']} / {animal['scientific_name'] or '—'}"
        lines.extend([f"## {name} (ID {animal['id']})", ""])
        for section, _ in SECTIONS:
            section_gaps = [(field, label) for heading, field, label in gaps if heading == section]
            if not section_gaps:
                continue
            lines.extend([f"### {section}", ""])
            for field, label in section_gaps:
                lines.append(f"- {label} (`{field}`)")
            lines.append("")
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("animal_id", "animal_name_my", "animal_name_en", "scientific_name", "section", "field_label", "field_key"))
        for animal, gaps in results:
            for section, field, label in gaps:
                writer.writerow((animal["id"], animal["name_my"], animal["name_en"],
                                 animal["scientific_name"] or "", section, label, field))
    return total, section_counts


if __name__ == "__main__":
    animals = collect()
    count, by_section = write_reports(animals)
    print(f"{len(animals)} animals; {count} fields; "
          f"section counts: {[by_section[heading] for heading, _ in SECTIONS]}")
    print(MD_PATH)
    print(CSV_PATH)
