"""Fix population wording that misstates the linked portal's original English."""

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "portal_population_translation_corrections.json"
FIELD = "wild_population_my"
PORTAL_KEY = "wild_population"
PRIMARY_CLOUDED_LEOPARD = (
    "https://www.cambridge.org/core/journals/oryx/article/"
    "population-density-estimates-and-conservation-concern-for-clouded-leopards-"
    "neofelis-nebulosa-marbled-cats-pardofelis-marmorata-and-tigers-panthera-tigris-"
    "in-htamanthi-wildlife-sanctuary-sagaing-myanmar/2A86FF95C0D603769C2392BC65C6AF2D"
)

# ID: (reviewed SHA256, exact old fragment, exact replacement, reason).
CORRECTIONS = {
    9: (
        "2c379cdabace48170a34d84a6e21048fc0c72482bf8a30ace057b5e4ad5cc200",
        "အကောင်ရေ လျော့ကျ့ကျနှုန်း", "အကောင်ရေ လျော့ကျနှုန်း",
        "Repair a garbled word without changing the assessment.",
    ),
    13: (
        "6858d622052ec6e816240f31cb8898fb3ebdc347e7593a6df3a3186b6f966c45",
        "မြန်မာနိုင်ငံတွင် အဆိုပါ အကြောင်းတရားများကို သာမာန်အဖြစ် ယူဆဆဲဖြစ်ပြီး ကုန်သွယ်မှုများ ရှိနေဆဲဖြစ်သည်။",
        "မြန်မာနိုင်ငံတွင် ဤမျိုးစိတ်ကို တွေ့ရများနေသေးပြီး ရောင်းဝယ်ဖောက်ကားမှုတွင်လည်း တွေ့ရဆဲဖြစ်သည်။",
        "Portal says the species is still common in Myanmar and present in trade.",
    ),
    16: (
        "7f6e6f821cc7e10a4f9c6194ba45e284122c9b75092992e862aa3cee16a06890",
        "အထက်ချင်းတွင်းမြစ်နှင့် နန့့််လပ်မြစ်များတွင် ရှားပါးကြောင်း အကြံပြုပါသည်။",
        "အထက်ချင်းတွင်းမြစ်နှင့် နန့်လပ်မြစ်တို့တွင် ထင်ထားသလောက် မရှားပါးကြောင်း ဖော်ပြထားသည်။",
        "The source says 'not as rare' in these rivers; the translation reversed its meaning.",
    ),
    17: (
        "a6277048c47b1be16975135b1b250ca5717b78a54be3c7e7ee564d57266fbb90",
        "အကောင်ရေ လျင်မြန်စွာ (၈၀%) ကျဆင်းလာပြီး",
        "အကောင်ရေ ၈၀ ရာခိုင်နှုန်းကျော် လျင်မြန်စွာ ကျဆင်းခဲ့နိုင်ပြီး",
        "The portal says more than 80 percent, not exactly 80 percent, and treats it as suspected.",
    ),
    21: (
        "b049737bae070b329a7280ce30ac2a301a60537ff7c18bb35d30532c6f3f2572",
        "အင်းကျား ‌ကောင်ရေ ၁၀၀ စတုရန်းကီလိုမီတာတွင် ၃.၀၅ ကောင်အထိ ‌ရှိနိုင်ကြောင်းလည်း‌ သိရသည်။",
        "အင်းကျား သိပ်သည်းဆကို ၁၀၀ စတုရန်းကီလိုမီတာလျှင် ၃.၀၅ ± ၁.၀၃ ကောင်ခန့်ဟု ခန့်မှန်းခဲ့သည်။ ဤသည် ထမံသီဒေသ စစ်တမ်း၏ သိပ်သည်းဆဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း စုစုပေါင်းအကောင်ရေ မဟုတ်ပါ။",
        "The original peer-reviewed paper confirms the per-100-km² unit and standard deviation.",
    ),
    24: (
        "993cfc3aaf05933f70debd64fe22958bf4424e15d31c6ccf8967ee94f1086eef",
        "အဆိုပါ တိရစ္ဆာန်များ၏ ၉၀% သည်",
        "အဆိုပါ တိရစ္ဆာန်များ၏ ၉၀ ရာခိုင်နှုန်းကျော်သည်",
        "The portal says more than 90 percent, not exactly 90 percent.",
    ),
    28: (
        "d3fd69573d1383b73005c43b7657cf92d9571bb73e359f357057746314fbf12c",
        "၁၅၃ ကောင် ဖမ်းမိသည့်အနက် ၄၅ ကောင်ကို မှတ်တမ်းယူနိုင်ခဲ့ကြောင်း",
        "ပိုက်ဖြင့် ဖမ်းဆီးရရှိမှု ၁၅၃ ကြိမ်အနက် ဤမျိုးစိတ် ၄၅ ကောင်ကို မှတ်တမ်းတင်ခဲ့ကြောင်း",
        "The source distinguishes 153 captures from 45 individuals; 153 is not an animal count.",
    ),
    32: (
        "ed6caace467d869ef5078572623f95f1709868eb2cc4343f04a33a0c51ef9b07",
        "မြန်မာနိုင်ငံတွင် အသိုက်ဖွဲ့နေထိုင်သည့် အကောင်ရေ အလွန်နည်းသည် (တစ်နှစ်လျှင် အသိုက် ၁၀ ခု အောက်)။",
        "မြန်မာနိုင်ငံတွင် အသိုက်ဖွဲ့မှု အလွန်နည်းပြီး တစ်နှစ်လျှင် အသိုက် ၁၀ ခုအောက်သာ မှတ်တမ်းတင်ထားသည်။ ဤသည် အသိုက်အရေအတွက်ဖြစ်ပြီး လိပ်အကောင်ရေကို တိုက်ရိုက်ရေတွက်ထားခြင်း မဟုတ်ပါ။",
        "Clarifies that the recorded under-10 quantity is nests, not animals.",
    ),
    33: (
        "5501cff5edfaeb9193ec82a5d4657d5c34fc1bc0d7dfbe08ea2447f4823b49e4",
        "အကောင်ရေမှာ ခန့်မှန်းခြေအားဖြင့် ၅၀ သာရှိသည်။",
        "အကောင်ရေမှာ ၅၀ အောက်သာရှိမည်ဟု ခန့်မှန်းထားသည်။",
        "The portal says fewer than 50, not exactly 50.",
    ),
    34: (
        "0e588b0e4cc91b16c21b509f4e588153600930647141767a70e59a7b9b0ad352",
        "ထိုင်း၊ မလေးရှားနှင့် တရုတ်နိုင်ငံတို့၌ အကောင်ရေ တည်ငြိမ်သော်လည်း",
        "ထိုင်းနှင့် မလေးရှားတွင် အကောင်ရေ တည်ငြိမ်ပြီး တရုတ်နိုင်ငံတွင်လည်း တည်ငြိမ်နိုင်သော်လည်း",
        "The source qualifies China with 'perhaps'; the original translation stated it as certain.",
    ),
    62: (
        "ae01e86ac8732402fd1a8e9a992496e268c5d63907e2b2ffaa7a9b16c4f40144",
        "အကောင်ရေအုပ်စုခွဲ၏ အရေအတွက် အနည်းငယ် တိုးလာပါသည်။",
        "အကောင်ရေအုပ်စုခွဲသည် တည်ငြိမ်နေသော်လည်းကောင်း၊ အနည်းငယ် တိုးလာနေသော်လည်းကောင်း ဖြစ်နိုင်သည်။",
        "The portal says stable or slightly increasing, not definitely increasing.",
    ),
    71: (
        "79f0d921b476149532ba1cf20d3343b9e0feb7ca813c347aff0fe2cdf9fa3556",
        "အကောင်ရေမှာ ခန့်မှန်းခြေအားဖြင့် ၅၀ သာ ရှိသည်။",
        "အကောင်ရေမှာ ၅၀ အောက်သာရှိမည်ဟု ခန့်မှန်းထားသည်။",
        "The portal says fewer than 50, not exactly 50.",
    ),
    77: (
        "d77d180df63bf8132d14f6e74491198408be3a9183f36979c94696b24e15edb7",
        "အကောင်ရေမှာ ခန့်မှန်းခြေအားဖြင့် ၂၀၀ ခန့်ရှိသည်။",
        "အကောင်ရေမှာ ၂၀၀ အောက်သာရှိမည်ဟု ခန့်မှန်းထားသည်။",
        "The portal says fewer than 200, not approximately 200.",
    ),
    78: (
        "0f694b747f074367ff3ab5d91d37c73ececfe46574e45ee920bdb424e4db31a1",
        "အကောင်ရေမှာ ခန့်မှန်းခြေအားဖြင့် ၅၀ သာရှိသည်။",
        "အကောင်ရေမှာ ၅၀ အောက်သာရှိမည်ဟု ခန့်မှန်းထားသည်။",
        "The portal says fewer than 50, not exactly 50.",
    ),
    80: (
        "99c052a610a3d83e8c665194c9456006024f54c183d5215391241cada29c272b",
        "မြန်မာနိုင်ငံတွင် အထူး ရှားပါးသော်လည်း (အကောင်ရေအတော်လေးတည်ငြိမ်ပုံရသည်)",
        "မြန်မာနိုင်ငံတွင် အထူးရှားပါးခြင်း မဟုတ်ဘဲ အကောင်ရေ အတော်လေး တည်ငြိမ်ပုံရသော်လည်း",
        "The portal says 'not particularly rare'; the translation said 'particularly rare'.",
    ),
}


def main():
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    completed = {item["animal_id"] for item in prior}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        with conn:
            for animal_id, (digest, old_part, new_part, reason) in CORRECTIONS.items():
                if animal_id in completed:
                    continue
                animal = conn.execute("SELECT * FROM animals WHERE id=?", (animal_id,)).fetchone()
                if animal is None:
                    raise LookupError(animal_id)
                old_value = animal[FIELD]
                if not old_value or hashlib.sha256(old_value.encode("utf-8")).hexdigest() != digest:
                    raise ValueError(f"Reviewed text changed for {animal_id}")
                if old_value.count(old_part) != 1:
                    raise ValueError(f"Expected phrase missing or repeated for {animal_id}")
                new_value = old_value.replace(old_part, new_part)
                sources = json.loads(animal["field_sources"] or "{}")
                old_sources = list(sources.get(FIELD, []))
                if not old_sources:
                    raise ValueError(f"No linked portal source for {animal_id}")
                if animal_id == 21 and PRIMARY_CLOUDED_LEOPARD not in old_sources:
                    sources[FIELD] = old_sources + [PRIMARY_CLOUDED_LEOPARD]
                conn.execute(
                    f"UPDATE animals SET {FIELD}=?, field_sources=? WHERE id=?",
                    (new_value, json.dumps(sources, ensure_ascii=False), animal_id),
                )
                changes.append({
                    "animal_id": animal_id, "name_my": animal["name_my"], "field": FIELD,
                    "old_value": old_value, "new_value": new_value,
                    "old_sources": old_sources, "new_sources": sources[FIELD], "reason": reason,
                })
            if changes:
                LOG.parent.mkdir(exist_ok=True)
                LOG.write_text(json.dumps(prior + changes, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        conn.close()
    print(f"Corrected {len(changes)} portal translations")
    print(LOG)


if __name__ == "__main__":
    main()
