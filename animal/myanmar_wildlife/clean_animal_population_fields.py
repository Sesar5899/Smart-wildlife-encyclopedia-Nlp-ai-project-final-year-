"""Remove reviewed empty/incorrect population claims, retaining a restore log."""

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from provenance import decode_field_sources


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "removed_animal_population_fields.json"
FIELDS = ("population_trend", "myanmar_population", "global_population", "wild_population_my")

# Complete values whose only message is that a count or trend is unavailable.
UNKNOWN_VALUES = {
    "မသိရသေးပါ။",
    "မသိရသေးပါ",
    "မြန်မာနိုင်ငံအတွက် တိကျသော နိုင်ငံအဆင့် ခန့်မှန်းချက် (national population estimate) မရရှိသေးပါ",
    "အကောင်ရေကို တိကျစွာ ခန့်မှန်းရန် ခက်ခဲပြီး ကမ္ဘာလုံးဆိုင်ရာ အရေအတွက်အတွက် ပြည့်စုံသော စာရင်းမရှိသေးပါ။",
    "တိကျသော အကောင်ရေစာရင်း မရရှိသေးပါ။",
    "အတိအကျ မသိရှိရသေးပါ။",
    "တိကျသောစာရင်းမရှိ (ထောင်ဂဏန်းအထိ ရှိနိုင်)",
    "တိကျသော စုစုပေါင်းမသိရှိရသေး",
    "နိုင်ငံလုံးဆိုင်ရာ အရေအတွက်ခန့်မှန်းချက်မရှိပါ။",
    "စုစုပေါင်းကိန်းဂဏန်းမရှိသော်လည်း နိုင်ငံအများအပြားမှာ ပျံ့နှံ့ပြီး ကျန်းမာသောအုပ်စုများရှိပါတယ်။",
    "မြန်မာနိုင်ငံအတွင်း အကောင်ရေ အတိအကျကို မသိရသေးပါ။",
    "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ အတိအကျကို မသိရသေးပါ။",
    "မြန်မာနိုင်ငံရှိ တောရိုင်းအကောင်ရေကို တိကျစွာ မတွက်ချက်ရသေးပါ။",
    "အကောင်ရေ အပြောင်းအလဲကို အတည်ပြုရန် အချက်အလက် မလုံလောက်သေးပါ။",
    "ကျားသစ်သည် ကမ္ဘာအနှံ့ဖြန့်ကျက်နေသော်လည်း အချို့ဒေသများတွင် အလွန်ရှားပါးလာပြီး တိကျသော ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေကို မသတ်မှတ်နိုင်သေးသော မျိုးစိတ်ဖြစ်သည်။တိကျသောစာရင်း မရှိ (ထောင်ဂဏန်းမှ သောင်းဂဏန်းအထိ ခန့်မှန်း)",
}

# Paragraphs which supply no usable population number, or use unsupported
# regional estimates as if they were a species-wide count.
NO_COUNT_PARAGRAPHS = {
    (132, "wild_population_my"),
    (207, "wild_population_my"),
}

# These verdicts are pinned to the exact current paragraph. The cited page
# explains the contradiction or lack of any defensible species-wide estimate.
REVIEWED = {
    (1, "wild_population_my"): (
        "f3d784205696fcfff936a56b7bcd0001c64c0797a0c156d0ab6066fa28a9e0a3",
        "Portal reports the population as unknown; no support for about 1,000.",
        "https://www.myanmarbiodiversity.org/species/Heosemys_depressa_Arakan_Forest_Turtle",
    ),
    (18, "myanmar_population"): (
        "5618cc76afd0fa0fd52dea2815ce62db642da87b79d28ee07fb9e37f8b7fc364",
        "Fewer than ten refers to wild adult females, not all Myanmar individuals.",
        "https://www.wcs.org/our-work/species/giant-river-turtles",
    ),
    (18, "global_population"): (
        "af1d282987989abdbb4cc5a4001fbdd51f05c202ec869ab0848dc8571d7498b0",
        "Ten cannot be the global total when over 1,000 are under protection.",
        "https://www.moi.gov.mm/moi%3Aeng/news/14553",
    ),
    (18, "wild_population_my"): (
        "319ebcd1a09b56ddaa39e9130bef1998cdcf1de1db8ee111ceed398a269a06a7",
        "Undated current-sounding wild and captive totals conflate historical counts.",
        "https://www.wcs.org/our-work/species/giant-river-turtles",
    ),
    (20, "myanmar_population"): (
        "e13c723d213bed50d8db1b310fd152226e317f4d0098ebd6153c10592718a7c1",
        "2,100 is a historic release figure, not an undated current Myanmar total.",
        "https://programs.wcs.org/onehealth/Wild-Places/Southeast-Asia.aspx",
    ),
    (27, "population_trend"): (
        "f7b0d94df561c787427a3061420f7612d6a774690b9085eee9f733ecb41e968b",
        "BirdLife's 2023 reassessment reports an increasing global trend.",
        "https://forums.birdlife.org/2023-2-graeter-adjutant-leptoptilus-dubius/",
    ),
    (27, "global_population"): (
        "beddb0bd7435132bf068d50f7af543bf203a22689fd4f15bd957d98b06582215",
        "800–1,200 is an old mature-individual estimate, not current global total.",
        "https://www.akp.gov.kh/index.php/post/detail/338695",
    ),
    (27, "wild_population_my"): (
        "0cded97b7b8efe7440305cba8bfe77a7cbc8f29e8c6283dbbf1b8f35fcd27441",
        "Paragraph embeds the contradicted declining global trend.",
        "https://forums.birdlife.org/2023-2-graeter-adjutant-leptoptilus-dubius/",
    ),
    (68, "wild_population_my"): (
        "c71af4cc884233ad500d9f0ed5e18bf99e64ea00b3b05466430408ff9cb292cc",
        "No species-specific support found for fewer than 250 in Myanmar.",
        "https://iucn-tftsg.org/wp-content/uploads/crm.10.checklist.atlas_.v10.2025.pdf",
    ),
    (131, "wild_population_my"): (
        "50d8817c1ace87ebdbb1723f451008784bfe24660379f7483042ad9dd1dfcf24",
        "Global 'a few thousand' conflicts with over 6,000 in Bangladesh alone; regional counts lack dates.",
        "https://www.wcs.org/our-work/species/coastal-dolphins",
    ),
    (134, "wild_population_my"): (
        "66e18e2695bfd197893c816040700837c0f67a519a4aa4c31a8fcb8b7a8cb7ea",
        "Ocean-wide figures mix common-dolphin forms; taxon boundaries are disputed.",
        "https://marinemammalscience.org/science-and-publications/list-marine-mammal-species-subspecies/",
    ),
}


def main():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    removed = []
    try:
        with conn:
            for row in conn.execute("SELECT * FROM animals ORDER BY id").fetchall():
                mapping = decode_field_sources(row["field_sources"])
                changes = {}
                for field in FIELDS:
                    value = row[field]
                    if value is None or not str(value).strip():
                        continue
                    key = (row["id"], field)
                    if key in REVIEWED:
                        expected, reason, evidence = REVIEWED[key]
                        if hashlib.sha256(value.encode("utf-8")).hexdigest() != expected:
                            raise ValueError(f"Reviewed text changed: {key}")
                        category = "reviewed_incorrect_or_misleading"
                    elif value.strip() in UNKNOWN_VALUES or key in NO_COUNT_PARAGRAPHS:
                        reason, evidence = "No usable population count or trend is stated.", ""
                        category = "unknown_only"
                    else:
                        continue
                    removed.append({
                        "id": row["id"], "name_my": row["name_my"], "name_en": row["name_en"],
                        "scientific_name": row["scientific_name"], "field": field,
                        "old_value": value, "old_field_sources": mapping.pop(field, []),
                        "category": category, "reason": reason, "evidence_url": evidence,
                    })
                    changes[field] = None
                if changes:
                    changes["field_sources"] = json.dumps(mapping, ensure_ascii=False)
                    columns = ", ".join(f"{field} = ?" for field in changes)
                    conn.execute(f"UPDATE animals SET {columns} WHERE id = ?",
                                 (*changes.values(), row["id"]))
            if removed:
                if LOG.exists():
                    raise FileExistsError(f"Restore log already exists: {LOG}")
                LOG.parent.mkdir(parents=True, exist_ok=True)
                LOG.write_text(json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        conn.close()
    counts = Counter(item["category"] for item in removed)
    print(f"Removed {len(removed)} fields across {len({item['id'] for item in removed})} animals: {dict(counts)}")
    print(LOG)


if __name__ == "__main__":
    main()
