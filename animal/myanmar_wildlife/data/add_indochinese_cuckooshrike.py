"""Publish the Indochinese cuckooshrike record in the local wildlife catalog."""

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "static/images/animals/indochinese-cuckooshrike.jpg"
COMMONS_FILE = (
    "https://commons.wikimedia.org/wiki/"
    "File:Indochinese_Cuckooshrike,_Nong_Bua_Daeng,_Chaiyaphum,_Thailand_1.jpg"
)
SOURCES = [
    {"label": "[၁] Cornell eBird — ရုပ်သွင်၊ နေထိုင်ရာနှင့် အသံ", "url": "https://ebird.org/species/indcus1"},
    {"label": "[၂] မြန်မာ့သစ်တောဦးစီးဌာန — ပင်းတယ ဇီဝမျိုးစုံမျိုးကွဲ လေ့လာမှု", "url": "https://forestdepartment.gov.mm/sites/default/files/Documents/FD-ICIMOD%20Biodiversity%20Report.pdf"},
    {"label": "[၃] BANCA — တနင်္သာရီဒေသ ငှက်စာရင်း", "url": "https://cdn.digitalagencybangkok.com/file/client-cdn/banca/wp-content/uploads/2018/05/gurneys-pitta-2015-report.pdf"},
    {"label": "[၄] AVONET — ငှက်များ၏ ကိုယ်ခန္ဓာနှင့် အစာရှာပုံ သုတေသန", "url": "https://onlinelibrary.wiley.com/doi/10.1111/ele.13898"},
    {"label": "[၅] Oiseaux.net — ဤမျိုးစိတ်၏ အရွယ်အစားနှင့် အစာအမျိုးအစား", "url": "https://www.oiseaux.net/en/oiseaux/indochinese.cuckooshrike.html"},
    {"label": "[၆] BirdLife DataZone — ဤမျိုးစိတ်၏ အကဲဖြတ်စာမျက်နှာ", "url": "https://datazone.birdlife.org/species/factsheet/indochinese-cuckooshrike-lalage-polioptera"},
    {"label": "[၇] IUCN — စိုးရိမ်ရမှုအနည်းဆုံးအဆင့်၏ အဓိပ္ပာယ်", "url": "https://nrl.iucnredlist.org/"},
    {"label": "[၈] ၂၀၂၁ ခုနှစ် လေ့လာမှု — အကောင်ရေ ပြောင်းလဲမှု ခန့်မှန်းချက်", "url": "https://www.jica.go.jp/english/our_work/social_environmental/id/asia/southeast/laos/fp4rrb000000rqsa-att/fh2q4d000000ozrr.pdf"},
    {"label": "[၉] ITIS — သိပ္ပံအမည်", "url": "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=559473"},
    {"label": "[၁၀] ထိုင်းအမျိုးသားဥယျာဉ်များ — ဖြန့်ကျက်တည်ရှိမှု", "url": "https://www.thainationalparks.com/species/indochinese-cuckooshrike"},
    {"label": "[၁၁] Wikimedia Commons — ဓာတ်ပုံနှင့် အသုံးပြုခွင့်", "url": COMMONS_FILE},
]

RECORD = {
    "name_my": "မီးခိုးရောင်ဥသြ",
    "name_en": "Indochinese Cuckooshrike",
    "scientific_name": "Coracina polioptera",
    "category_id": 2,
    "taxon_rank": "species",
    "species_order": "Passeriformes",
    "species_family": "Campephagidae",
    "description_my": (
        "မီးခိုးရောင်ဥသြသည် မြန်မာ၊ ထိုင်း၊ လာအို၊ ကမ္ဘောဒီးယားနှင့် ဗီယက်နမ်တို့တွင် "
        "တွေ့ရှိရသော ငှက်မျိုးစိတ်ဖြစ်သည်။ မီးခိုးရောင်ကိုယ်ထည်နှင့် အရောင်ရင့်အတောင်ရှိပြီး "
        "သစ်တောနှင့် သစ်တောအစပ်များတွင် နေထိုင်သည်။ သိပ္ပံစာပေအချို့၌ "
        "Lalage polioptera ဟူသောအမည်ဖြင့် ဖော်ပြသည်။ ရင်းမြစ် [၁]၊ [၉]၊ [၁၀]။"
    ),
    "physical_description_my": (
        "အထီးတွင် ကိုယ်ထည်မီးခိုးရောင်၊ အတောင်ဖျားအရောင်ရင့်နှင့် ဝမ်းအောက်ဘက် "
        "အဖြူရောင်ရှိသည်။ အမသည် အရောင်ပိုဖျော့ပြီး ကိုယ်အောက်ပိုင်း၌ အစင်းပါးပါးများ "
        "ရှိသည်။ အတောင်အရောင်နှင့် အမြီးအောက်ဘက် အဖြူရောင်စုပြုံပုံတို့ကို "
        "ဆင်တူသော မီးခိုးရောင်ငှက်မျိုးများနှင့် ခွဲခြားရာတွင် အသုံးပြုနိုင်သည်။ ရင်းမြစ် [၁]။"
    ),
    "habitat_my": (
        "ပွင့်လင်းသော သစ်တောများ၊ အထူးသဖြင့် ရွက်ကြွေသစ်တောများ၊ သစ်တောအစပ်နှင့် "
        "သစ်ပင်များရှိသော ဥယျာဉ်များတွင် တွေ့ရသည်။ စိုစွတ်သော မြေနိမ့်သစ်တောနှင့် "
        "တောင်တန်းသစ်တောတို့လည်း ၎င်း၏ နေထိုင်ရာတွင် ပါဝင်သည်။ ရင်းမြစ် [၁]၊ [၁၀]။"
    ),
    "diet_my": (
        "အဓိကအားဖြင့် ပိုးမွှားများအပါအဝင် ကျောရိုးမဲ့သတ္တဝါငယ်များကို စားသည်။ "
        "သစ်ပင်ပေါ်ရှိ အရွက်၊ အကိုင်းများအကြား အစာရှာကာ ကောက်ယူစားသောက်သည့် "
        "ပုံစံရှိသည်။ ဤအချက်မှာ မျိုးစိတ်အဆင့် အစာအိမ်စစ်ဆေးမှုစာရင်း မဟုတ်ဘဲ "
        "ထုတ်ဝေထားသော အစာရှာပုံဆိုင်ရာ အချက်အလက်ကို အခြေခံသည်။ ရင်းမြစ် [၄]၊ [၅]။"
    ),
    "distribution_my": (
        "အရှေ့တောင်အာရှပြည်မကြီးရှိ မြန်မာ၊ ထိုင်း၊ လာအို၊ ကမ္ဘောဒီးယားနှင့် "
        "ဗီယက်နမ်တို့တွင် ဖြန့်ကျက်တည်ရှိသည်။ မြန်မာနိုင်ငံအတွင်း ရှမ်းပြည်နယ်တောင်ပိုင်း "
        "ပင်းတယဒေသမှ ကွင်းဆင်းမှတ်တမ်းနှင့် တနင်္သာရီဒေသမှ ငှက်စာရင်းများ ရှိသည်။ "
        "ဤမှတ်တမ်းများက နိုင်ငံအတွင်း ဖြန့်ကျက်မှု အပြည့်အစုံကို မဖော်ပြနိုင်ပါ။ "
        "ရင်းမြစ် [၂]၊ [၃]၊ [၁၀]။"
    ),
    "behaviour_my": (
        "နေ့ဘက်တွင် သစ်ပင်များအကြား အစာရှာလေ့ရှိသည်။ အုပ်စုငယ်ဖြင့် ပျံသန်းရာ၌ "
        "ညှစ်သံဆန်သော အော်သံများ ကြားရတတ်ပြီး အသံမြင့်ရာမှ နိမ့်ဆင်းသွားသော "
        "လေချွန်သံစဉ်ကိုလည်း ထုတ်တတ်သည်။ ရင်းမြစ် [၁]၊ [၅]။"
    ),
    "size_my": "ကိုယ်အရှည် ၂၁–၂၃ စင်တီမီတာခန့်၊ ပျမ်းမျှအလေးချိန် ၃၆ ဂရမ်ခန့်။ ရင်းမြစ် [၄]၊ [၅]။",
    "lifespan_my": "စစ်ဆေးခဲ့သော မျိုးစိတ်ဆိုင်ရာ ရင်းမြစ်များတွင် သဘာဝအခြေအနေ၌ တိုက်ရိုက်မှတ်တမ်းတင်ထားသည့် သက်တမ်းအချက်အလက် မတွေ့ရှိရသေးပါ။ ရင်းမြစ် [၁]၊ [၆]။",
    "region_my": "ရှမ်းပြည်နယ်တောင်ပိုင်း ပင်းတယဒေသနှင့် တနင်္သာရီဒေသတို့မှ မှတ်တမ်းများ ရှိသည်။ ရင်းမြစ် [၂]၊ [၃]။",
    "fun_facts_my": (
        "အင်္ဂလိပ်အမည်တွင် ဥသြပါသော်လည်း ဥသြမျိုးရင်းဝင် မဟုတ်ဘဲ "
        "Campephagidae မျိုးရင်းဝင်ဖြစ်သည်။ သိပ္ပံအမည်ကို Coracina polioptera နှင့် "
        "Lalage polioptera ဟူ၍ စာရင်းအလိုက် မတူညီစွာ တွေ့နိုင်သည်။ "
        "အမ၏ ကိုယ်အောက်ပိုင်းရှိ အစင်းပါးများသည် ခွဲခြားရာတွင် အထောက်အကူဖြစ်သည်။ "
        "ရင်းမြစ် [၁]၊ [၉]။"
    ),
    "global_iucn_status": "LC",
    "population_trend": "၂၀၂၁ ခုနှစ် အစီရင်ခံစာအရ တည်ငြိမ်နေသည်ဟု ခန့်မှန်းထားသည်။ ရင်းမြစ် [၈]။",
    "myanmar_population": "မြန်မာနိုင်ငံရှိ အကောင်ရေကို နိုင်ငံအဆင့် တိကျစွာ ခန့်မှန်းထားသော ထုတ်ပြန်ချက် မတွေ့ရှိရသေးပါ။ ရင်းမြစ် [၂]၊ [၆]။",
    "global_population": "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေကို တိကျစွာ ခန့်မှန်းထားသော ထုတ်ပြန်ချက် မတွေ့ရှိရသေးပါ။ ရင်းမြစ် [၆]။",
    "iucn_justification_my": (
        "ကမ္ဘာလုံးဆိုင်ရာ အဆင့်မှာ LC — စိုးရိမ်ရမှု အနည်းဆုံး ဖြစ်သည်။ IUCN သတ်မှတ်ချက်အရ "
        "ဤအဆင့်သည် မျိုးသုဉ်းရန် ခြိမ်းခြောက်ခံရသော အဆင့်များ သို့မဟုတ် အန္တရာယ်နီးကပ်သော "
        "အဆင့်၏ စံနှုန်းများနှင့် မကိုက်ညီကြောင်း ဆိုလိုသည်။ ဤမျိုးစိတ်အတွက် "
        "အသေးစိတ် အကဲဖြတ် အကြောင်းပြချက်ကို ဖတ်ရှုနိုင်သော ရင်းမြစ်တွင် "
        "မရရှိသဖြင့် ဖြန့်ကျက်မှုကျယ်ခြင်းတစ်ခုတည်းကို တရားဝင်အကြောင်းပြချက်ဟု "
        "မသတ်မှတ်ထားပါ။ မြန်မာနိုင်ငံအဆင့် သီးခြား IUCN အကဲဖြတ်ရလဒ်ကိုလည်း "
        "အတည်မပြုနိုင်သေးပါ။ ရင်းမြစ် [၆]၊ [၇]၊ [၈]။"
    ),
    "threats_my": (
        "ဤမျိုးစိတ်အတွက် သီးခြားတိုင်းတာထားသော ခြိမ်းခြောက်မှုအဆင့်ကို "
        "အတည်မပြုနိုင်သေးပါ။ သစ်တောတွင် နေထိုင်သောကြောင့် သစ်တောပျက်စီးမှုနှင့် "
        "အပိုင်းပိုင်းကွဲမှုသည် နေထိုင်ရာကို ထိခိုက်နိုင်သည်ဟု ယူဆရသော်လည်း "
        "ဤသည်မှာ နေထိုင်ရာနှင့် မြန်မာ့သစ်တောလေ့လာမှုမှ ဆင်ခြင်ထားချက်ဖြစ်ပြီး "
        "ဤမျိုးစိတ်၏ အကောင်ရေကျဆင်းမှုကို တိုက်ရိုက်သက်သေပြခြင်း မဟုတ်ပါ။ "
        "ရင်းမြစ် [၁]၊ [၂]၊ [၆]။"
    ),
    "conservation_actions_my": (
        "ပင်းတယဒေသရှိ သစ်တောများကို ဒေသခံများနှင့် သံဃာများက ထိန်းသိမ်းကာ "
        "သစ်ပင်ခုတ်ခြင်းနှင့် တိရစ္ဆာန်သတ်ဖြတ်ခြင်းကို ကန့်သတ်ထားသည်။ "
        "သစ်တောပြန်လည်စိုက်ပျိုးခြင်းနှင့် ငှက်မျိုးစုံ စာရင်းကောက်ခြင်းများလည်း "
        "လုပ်ဆောင်ခဲ့သည်။ ဤငှက်ကို ပင်းတယစစ်တမ်းတွင် မှတ်တမ်းတင်ထားသော်လည်း "
        "ဖော်ပြပါလုပ်ငန်းများသည် ဤမျိုးစိတ်ကိုသာ ရည်ရွယ်သည့် ထိန်းသိမ်းရေး "
        "အစီအစဉ် မဟုတ်ပါ။ ရင်းမြစ် [၂]။"
    ),
    "conservation_needs_my": (
        "မြန်မာနိုင်ငံရှိ အကောင်ရေနှင့် ဖြန့်ကျက်နေရာများကို ပုံမှန်စစ်တမ်းကောက်ရန်၊ "
        "သစ်တောနှင့် သစ်တောအစပ် နေထိုင်ရာများကို ထိန်းသိမ်းရန်၊ "
        "အစာရှာပုံနှင့် မျိုးပွားရာနေရာများကို ပိုမိုလေ့လာရန် လိုအပ်သည်ဟု "
        "အချက်အလက်ကွာဟချက်များကို အခြေခံ၍ အကြံပြုထားသည်။ "
        "ဤအကြံပြုချက်များကို ဤမျိုးစိတ်အတွက် တရားဝင်ထုတ်ပြန်ထားသော "
        "လုပ်ငန်းစီမံချက်ဟု မယူဆသင့်ပါ။ ရင်းမြစ် [၂]၊ [၆]။"
    ),
    "use_trade_my": (
        "ဤမျိုးစိတ်ကို လက်ရှိ အသုံးပြုမှု သို့မဟုတ် တရားမဝင် ဖမ်းဆီးရောင်းဝယ်မှု "
        "ရှိနေကြောင်း အတည်ပြုနိုင်သည့် မျိုးစိတ်အလိုက် မှတ်တမ်း မတွေ့ရှိရသေးပါ။ "
        "မြန်မာ့သစ်တောလေ့လာမှုတွင် တောရိုင်းတိရစ္ဆာန် ကုန်သွယ်မှုကို "
        "ယေဘုယျပြဿနာအဖြစ် ဖော်ပြထားသော်လည်း ဤငှက်အတွက် သီးခြား "
        "သက်သေမပြပါ။ ရင်းမြစ် [၂]၊ [၆]။"
    ),
    "image_url": "/static/images/animals/indochinese-cuckooshrike.jpg",
    "source_image_url": "https://upload.wikimedia.org/wikipedia/commons/d/dc/Indochinese_Cuckooshrike%2C_Nong_Bua_Daeng%2C_Chaiyaphum%2C_Thailand_1.jpg",
    "image_credit": "Jan Ebr · CC BY 4.0 · Wikimedia Commons",
    "source_name": SOURCES[0]["label"],
    "source_url": SOURCES[0]["url"],
    "source_urls": json.dumps(SOURCES, ensure_ascii=False),
}


def main():
    if not PHOTO.is_file():
        raise FileNotFoundError(PHOTO)
    connection = sqlite3.connect(ROOT / "wildlife.db")
    try:
        existing = connection.execute(
            "SELECT id FROM animals WHERE scientific_name IN (?, ?)",
            ("Coracina polioptera", "Lalage polioptera"),
        ).fetchone()
        with connection:
            if existing:
                assignments = ", ".join(f"{field} = ?" for field in RECORD)
                connection.execute(
                    f"UPDATE animals SET {assignments} WHERE id = ?",
                    (*RECORD.values(), existing[0]),
                )
                animal_id = existing[0]
            else:
                columns = ", ".join(RECORD)
                placeholders = ", ".join("?" for _ in RECORD)
                cursor = connection.execute(
                    f"INSERT INTO animals ({columns}) VALUES ({placeholders})",
                    tuple(RECORD.values()),
                )
                animal_id = cursor.lastrowid
        print(f"Published animal {animal_id}: {RECORD['name_my']}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
