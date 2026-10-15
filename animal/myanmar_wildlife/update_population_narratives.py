"""Correct source-checked animal population narratives with a reversible log."""

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "population_narrative_corrections.json"
FIELD = "wild_population_my"

# Animal ID: (SHA256 of the reviewed old value, replacement, explanation).
CORRECTIONS = {
    3: (
        "3372e697e9e6f44f088fc1ba1811bd4c3a724be1a9edf15222f47abe5549d63c",
        "လိပ်မောင်းမျိုးစိတ်သည် ရှားပါးပြီး အကောင်ရေ ကျဆင်းနေသည်။ မူရင်းအကဲဖြတ်ချက်အရ လွန်ခဲ့သည့် မျိုးဆက် ၃ ဆက် (၁၃၅ နှစ်ခန့်) အတွင်း ကမ္ဘာတစ်ဝန်း အကောင်ရေ ၈၀ ရာခိုင်နှုန်းကျော် လျော့ကျခဲ့နိုင်သည်ဟု ခန့်မှန်းထားသည်။ အလွန်အကျွံ ဖမ်းဆီးအသုံးပြုမှုနှင့် နေထိုင်ကျက်စားရာဒေသ လျော့နည်းမှုကြောင့် မြန်မာနိုင်ငံတွင်း အကောင်ရေကျဆင်းမှုသည် အလားတူ သို့မဟုတ် ပိုများနိုင်သည်။ ရခိုင်ပြည်နယ်ရှိ အကောင်ရေသည် ၂၀၀၀ ပြည့်နှစ်များအစောပိုင်းတွင် ဒေသအလိုက် မျိုးသုဉ်းသွားခဲ့နိုင်သည်ဟု ၂၀၁၈ ခုနှစ် အချက်အလက်တွင် ဖော်ပြထားသည်။ ဤသည် သမိုင်းဝင် အကဲဖြတ်ချက်ဖြစ်ပြီး လက်ရှိ တိကျသောအကောင်ရေကို မဖော်ပြပါ။",
        "Removes garbled Burmese wording and identifies the historical, inferred nature of the decline.",
    ),
    20: (
        "60a30039c1974383da476f7fce41429c13a8d73eaba0d4eef934dcb785882ce3",
        "၂၀၀၀ ပြည့်နှစ်များအစောပိုင်းတွင် မြန်မာ့ကြယ်လိပ်သည် တောရိုင်းတွင် မျိုးသုဉ်းသွားသည်ဟု ယူဆခဲ့သည်။ ၂၀၁၃ ခုနှစ်မှစ၍ မင်းစုံတောင်နှင့် ရွှေစက်တော် ဘေးမဲ့တောများတွင် ပြန်လည်လွှတ်ပေးခဲ့ရာ အသက် ၅ နှစ်ခန့်ရှိသည့် အရွယ်မရောက်သေးသော ကြယ်လိပ် ၂,၁၀၀ ခန့် ပါဝင်သည်။ ၂၀၁၇ ခုနှစ် စစ်တမ်းတွင် တောရိုင်း၌ ပေါက်ဖွားသော လိပ်ငယ် ၅၁ ကောင်ကို တွေ့ရှိခဲ့သည်။ ၂,၁၀၀ ကောင်သည် ပြန်လည်လွှတ်ပေးခဲ့သည့် အရေအတွက်ဖြစ်ပြီး လက်ရှိ တောရိုင်းတွင် အသက်ရှင်ကျန်ရှိသော စုစုပေါင်းအကောင်ရေ မဟုတ်ပါ။",
        "Portal says 2,100 reintroduced subadults, not mature animals or a current surviving population.",
    ),
    30: (
        "b669fea77d5166b2a5e52406ba1d6bbb52d47a8e868e43cc2af2736a668d9a88",
        "မြန်မာနိုင်ငံရှိ စစ်တမ်းနေရာတစ်ခုတွင် ၂၀၀၃ ခုနှစ်က ပြင်သာလိပ်အသိုက် ၂၅၀ ကျော်နှင့် ဥ ၂၂,၀၀၀ ကျော်ကို မှတ်တမ်းတင်ခဲ့ပြီး ၂၀၁၈ ခုနှစ်တွင် ထိုနေရာ၌ အသိုက် ၁၂၀ နှင့် ဥ ၅,၀၀၀ ခန့်ကို မှတ်တမ်းတင်ခဲ့သည်။ ဤကိန်းဂဏန်းများသည် အသိုက်နှင့် ဥအရေအတွက်ဖြစ်ပြီး လိပ်အကောင်ရေကို တိုက်ရိုက်ရေတွက်ထားခြင်း မဟုတ်ပါ။ မူရင်းအကဲဖြတ်ချက်က အသိုက်ဖွဲ့ရာ ကမ်းခြေများ ဆုံးရှုံးမှုအပါအဝင် အချက်အလက်များအပေါ် အခြေခံ၍ ထိုကာလအတွင်း အကောင်ရေ ၈၀ ရာခိုင်နှုန်းကျော် လျော့ကျခဲ့နိုင်သည်ဟု ခန့်မှန်းထားသည်။ ဤသည် သမိုင်းဝင် အကဲဖြတ်ချက်ဖြစ်ပြီး လက်ရှိအကောင်ရေ မဟုတ်ပါ။",
        "Distinguishes observed nests and eggs from the portal's inferred population decline and removes ambiguous currentness wording.",
    ),
    42: (
        "8ace5c4cc45fb60e20760adb2a4c252e9979f1be9d5a7f3bede9b8a73bb39283",
        "၁၉၉၉–၂၀၀၄ ခုနှစ် မြန်မာနိုင်ငံတစ်ဝန်း စစ်တမ်းနယ်မြေ ၁၈ ခုအနက် ၉ ခုတွင် ကျားသစ်ကို တွေ့ရှိခဲ့သည်။ ၂၀၁၆ ခုနှစ် ထုတ်ပြန် လေ့လာချက်အရ ယခင်ကျက်စားခဲ့သည့် နယ်မြေ၏ ၁၁.၃ ရာခိုင်နှုန်းခန့်၌သာ တွေ့ရှိခဲ့ပြီး စုစုပေါင်း ၂၂၃–၆၇၀ ကောင်ခန့်၊ ထိုအထဲမှ မျိုးပွားနိုင်သော အရွယ်ရောက်အကောင် ၉၄–၂၈၁ ကောင်ခန့် ရှိနိုင်သည်ဟု ခန့်မှန်းခဲ့သည်။ ဤသည် ၂၀၁၆ ခုနှစ် လေ့လာချက်၏ သမိုင်းဝင် ခန့်မှန်းချက်ဖြစ်ပြီး လက်ရှိအကောင်ရေကို မဖော်ပြပါ။",
        "Corrects the survey period from 1994 to 1999 and labels the 2016 estimate as historical.",
    ),
    48: (
        "481fb9f8c4b5056ed350441cb409a0bbf8da3a7b56d5ae6a37efcbecdc265ef9",
        "မလေးဝက်ဝံ၏ မျိုးဆက်သက်တမ်းမှာ ၁၀ နှစ်ခန့်ဖြစ်သည်။ စစ်တမ်းနယ်မြေများတွင်ပင် အကောင်ရေကို တိကျစွာ ခန့်မှန်းရန် ခက်ခဲသည်။ FAO သစ်တောသယံဇာတ အကဲဖြတ်ချက်အရ ၁၉၇၅–၂၀၁၀ ခုနှစ်အတွင်း မြန်မာနိုင်ငံရှိ အဓိကနေထိုင်ရာဖြစ်သော ထူထပ်သည့် သစ်တောဧရိယာ ၅၀ ရာခိုင်နှုန်းခန့် ဆုံးရှုံးခဲ့သည်။ မူရင်းအကဲဖြတ်ချက်က ယခင်မျိုးဆက် ၃ ဆက်အတွင်း မလေးဝက်ဝံအကောင်ရေ ၃၀ ရာခိုင်နှုန်းကျော် လျော့ကျခဲ့နိုင်ပြီး နောင်တွင်လည်း အလားတူနှုန်းဖြင့် ဆက်လက်လျော့ကျနိုင်သည်ဟု ခန့်မှန်းထားသည်။ ဤကိန်းဂဏန်းသည် စစ်တမ်းဖြင့် တိုက်ရိုက်ရေတွက်ထားသော အကောင်ရေ မဟုတ်ပါ။",
        "Corrects a mistranslated forecast that previously said it was uncertain whether decline would continue.",
    ),
    57: (
        "cf3956bf9dbd7c0acf7d233dd3d92e4fb30eadfb012b63f8e7c448fc69f82cb7",
        "ဂယက်ကြီးကျွန်းတွင် ၁၉၉၉ ခုနှစ်က လိပ်လှောင်းအသိုက် ၃၄၀ နှင့် ဥ ၃၆,၀၀၀ ကို မှတ်တမ်းတင်ခဲ့ပြီး ၂၀၁၈ ခုနှစ်တွင် အသိုက် ၂၀ နှင့် ဥ ၂,၅၀၀ ကို မှတ်တမ်းတင်ခဲ့သည်။ ထိုနေရာ၏ အသိုက်အရေအတွက်သည် ၁၉ နှစ်အတွင်း ၉၄ ရာခိုင်နှုန်းခန့် လျော့ကျခဲ့သည်။ ဤကိန်းဂဏန်းသည် အသိုက်ရေကျဆင်းမှုဖြစ်ပြီး လိပ်အကောင်ရေကို တိုက်ရိုက်ရေတွက်ထားခြင်း မဟုတ်ပါ။ မူရင်းအကဲဖြတ်ချက်က ဤအချက်အလက်များအပေါ် အခြေခံ၍ အကောင်ရေ အလားတူ လျော့ကျခဲ့နိုင်သည်ဟု ခန့်မှန်းထားသည်။ လက်ရှိအကောင်ရေကို ဤမှတ်တမ်းက မဖော်ပြပါ။",
        "Separates the observed 94 percent decline in nests from the inferred decline in individuals.",
    ),
    79: (
        "7d00164ca459a20b5af706e5da6859c93f0f3f038a2fb12b6ab3d7542ddd7a9f",
        "၂၀၂၄ ခုနှစ် ခန့်မှန်းချက်အရ မြန်မာနိုင်ငံတွင် တောဘဲမန်ဒါလီ မျိုးပွားနိုင်သော အရွယ်ရောက်အကောင် ၄၀–၁၀၀ ကောင်ခန့် ရှိနိုင်သည်။ ဤသည် တစ်ကောင်ချင်း တိုက်ရိုက်ရေတွက်ထားသော စုစုပေါင်းမဟုတ်ဘဲ သတိထား၍ ခန့်မှန်းထားသော အပိုင်းအခြားဖြစ်သည်။",
        "Corrects the mistakenly inserted name of another bird while retaining the sourced 2024 estimate.",
    ),
}


def main():
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    done = {item["animal_id"] for item in prior}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        with conn:
            for animal_id, (digest, replacement, reason) in CORRECTIONS.items():
                if animal_id in done:
                    continue
                animal = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                if animal is None:
                    raise LookupError(animal_id)
                old = animal[FIELD]
                if not old or hashlib.sha256(old.encode("utf-8")).hexdigest() != digest:
                    raise ValueError(f"Reviewed value changed for animal {animal_id}")
                sources = json.loads(animal["field_sources"] or "{}")
                if not sources.get(FIELD):
                    raise ValueError(f"Missing field source for animal {animal_id}")
                conn.execute(f"UPDATE animals SET {FIELD} = ? WHERE id = ?", (replacement, animal_id))
                changes.append({
                    "animal_id": animal_id, "name_my": animal["name_my"], "field": FIELD,
                    "old_value": old, "new_value": replacement, "source_links": sources[FIELD],
                    "reason": reason,
                })
            if changes:
                LOG.parent.mkdir(exist_ok=True)
                LOG.write_text(json.dumps(prior + changes, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        conn.close()
    print(f"Corrected {len(changes)} population narratives")
    print(LOG)


if __name__ == "__main__":
    main()
