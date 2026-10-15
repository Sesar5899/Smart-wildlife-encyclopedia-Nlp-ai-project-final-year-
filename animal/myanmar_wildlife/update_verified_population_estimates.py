"""Apply source-checked population corrections with a reversible change log."""

import hashlib
import json
import sqlite3
from pathlib import Path

from provenance import decode_field_sources


ROOT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
LOG = ROOT / "docs" / "verified_population_updates.json"

# (animal id, field): (sha256 of reviewed old text, replacement, evidence URL, reason)
UPDATES = {
    (67, "myanmar_population"): (
        "e0e2c69fd3ffd6745b6f16b484e81e807dcdac2e280f62d8b29879a52d125a7c",
        None,
        "https://www.banca-env.org/community-leading-the-vulture-restaurant-activities-at-nam-sang-township-in-southern-shan-state/",
        "The portal's undated under-1,000 national bound is too broad to function as a current national estimate; the recent BANCA survey is local only.",
    ),
    (67, "global_population"): (
        "e40f61c4f37430461274aeb672ef1557a73c2b11d02482ea74adbfa24935ce4e",
        "၂၀၂၄ သုံးသပ်ချက် — ကမ္ဘာတစ်ဝန်း မျိုးပွားနိုင်သော အရွယ်ရောက်အကောင် ၇၃၀–၈၇၀ ကောင်ခန့်",
        "https://boc-online.org/bulletins/downloads/bboc.v144i3.2024.a15.pdf",
        "The published range is for mature individuals; the old field omitted that scope and assessment context.",
    ),
    (67, "wild_population_my"): (
        "bf6c170a383327a28157d8652225da6472b3431c861657e9c485132261467817",
        "၂၀၂၄ ဇန်နဝါရီ ၂၇ ရက် ရှမ်းပြည်နယ်တောင်ပိုင်း Hai Hpak ဒေသ စစ်တမ်းတစ်ခုတွင် လင်းတနှုတ်သီးရှည် ၁၈ ကောင်ကို မှတ်တမ်းတင်ခဲ့သည်။ ဤသည် စစ်တမ်းနေရာတစ်ခု၏ တွေ့ရှိမှုသာဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း အကောင်ရေ မဟုတ်ပါ။",
        "https://www.banca-env.org/community-leading-the-vulture-restaurant-activities-at-nam-sang-township-in-southern-shan-state/",
        "Replaces an undated under-1,000 claim with BANCA's dated local observation and explicit survey scope.",
    ),
    (71, "global_population"): (
        "832cd86593c472c0f9ba8ebf4946627bb2ea45d6e515f259751e5f3f625ab03f",
        "BirdLife ၂၀၂၅ အကဲဖြတ်ချက် — ကမ္ဘာတစ်ဝန်း အရွယ်ရောက်ပြီးသော အကောင်ရေ ၃၀၀–၁,၇၅၀ ကောင်ခန့်",
        "https://malaysianbird.report/wp-content/uploads/Malaysian-Bird-Report-March-2025-Final-31Mar2025-High-Res-3.pdf",
        "The 2025 Malaysian Bird Report cites BirdLife International 2025 for 300–1,750 mature individuals, superseding the older 260–330 range.",
    ),
    (81, "myanmar_population"): (
        "302f57ddcaeb6c49f6d6cc7a0622d9a3b6c7584a1f07d6619ff873b60c24b652",
        None,
        "https://cdn.digitalagencybangkok.com/file/client-cdn/banca/wp-content/uploads/2024/04/Final-report-on-Winter-Bunting-Count-in-Myanmar-BANCA-TDA.pdf",
        "The old Myanmar-wide under-500 bound is contradicted by 6,312 birds counted at one Myanmar roost in 2023.",
    ),
    (81, "wild_population_my"): (
        "6073881e2102f58ce4756eda6f5c8a62c558618905f325d378691ac25e2fcaae",
        "၂၀၂၃ ခုနှစ် ဧရာဝတီတိုင်း Kyon Ka Pyin–Tap Seik ဒေသ စစ်တမ်းတွင် စာဝါကြား ၆,၃၁၂ ကောင်ကို တွေ့ရှိခဲ့သည်။ ၂၀၂၅ ခုနှစ် အင်းလေးကန် ဘေးမဲ့တောမှတ်တမ်းတွင်လည်း ၅၀၀ ကျော်ကို တွေ့ရှိထားသည်။ နှစ်ခုစလုံးသည် ဒေသအလိုက် တွေ့ရှိမှုများဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း အကောင်ရေ ခန့်မှန်းချက် မဟုတ်ပါ။",
        [
            "https://cdn.digitalagencybangkok.com/file/client-cdn/banca/wp-content/uploads/2024/04/Final-report-on-Winter-Bunting-Count-in-Myanmar-BANCA-TDA.pdf",
            "https://www.forestdepartment.gov.mm/news/28789",
        ],
        "Uses two dated, independently scoped Myanmar observations rather than the contradicted national upper bound.",
    ),
    (62, "global_population"): (
        "f7ea2775ed0c07499b439f091ce06a2034af5607b294cf023f0368855a7a2e4f",
        "IUCN ၂၀၁၉ အကဲဖြတ်ချက် (UN သုံးသပ်ချက်တွင် ဖော်ပြ) — ကမ္ဘာတစ်ဝန်း တောရိုင်း အကောင်ရေ ၄၀၀,၀၀၀ ကျော် (ဥမှပေါက်ခါစအကောင်များ မပါ)",
        "https://woa.un.org/third-world-ocean-assessment/changes-second-world-ocean-assessment/biodiversity/chapter-4-subchapter-4f-marine",
        "UN World Ocean Assessment reports more than 400,000 non-hatchlings, contradicting the undated 50,000 global value.",
    ),
    (62, "population_trend"): (
        "f7b0d94df561c787427a3061420f7612d6a774690b9085eee9f733ecb41e968b",
        "မြန်မာနိုင်ငံတွင် ကျဆင်းနေသည်ဟု ခန့်မှန်းထားပြီး ကမ္ဘာလုံးဆိုင်ရာ အခြေအနေမှာ တည်ငြိမ်သည် (IUCN ၂၀၁၉ အကဲဖြတ်ချက်)",
        "https://woa.un.org/third-world-ocean-assessment/changes-second-world-ocean-assessment/biodiversity/chapter-4-subchapter-4f-marine",
        "Clarifies that the declining trend concerns Myanmar; the same UN review lists global status as stable.",
    ),
    (63, "myanmar_population"): (
        "2a8cf6132a5e23202893cacb40f9fff3334ff2562ad4c0c12e35f1e69daf8f1f",
        "၂၀၁၇ ထုတ်ပြန် စစ်တမ်းများအပေါ် အခြေခံသော မြန်မာနိုင်ငံ ခန့်မှန်းချက် — ၃၀၀–၄၀၀ ကောင်။ လက်ရှိအကောင်ရေဟု မယူဆရပါ။",
        "https://savingcranes.org/wp-content/uploads/2024/10/crane_conservation_strategy_sarus_crane.pdf",
        "International Crane Foundation strategy estimates 300–400 Sarus Cranes in Myanmar using 2016–2017 surveys; the portal's under-800 count was undated.",
    ),
    (63, "global_population"): (
        "ca9f79988120746da07c44c9a11280d3705dc8eeff0b566fe789a23f24683f65",
        "International Crane Foundation ဖော်ပြချက် — ကမ္ဘာတစ်ဝန်း ၂၀,၀၀၀–၃၀,၀၀၀ ကောင်ခန့် (ခန့်မှန်းနှစ် မဖော်ပြထား)",
        "https://savingcranes.org/species/sarus-crane/",
        "Current International Crane Foundation species page gives 20,000–30,000; its estimate year is not stated, so it is not presented as a 2026 census.",
    ),
    (63, "wild_population_my"): (
        "3d382b47bf2cea20c59f4377738564969fb2d97fa2963b5438820425d8d6a82a",
        "၂၀၁၈ ခုနှစ် ဧရာဝတီမြစ်ဝကျွန်းပေါ်ဒေသ စစ်တမ်းတွင် ကြိုးကြာခေါင်းနီ ၂၉၉ ကောင်ကို တွေ့ရှိခဲ့သည်။ ဤသည် စစ်တမ်းဧရိယာအတွင်း တွေ့ရှိမှုဖြစ်ပြီး လက်ရှိ မြန်မာနိုင်ငံတစ်ဝန်း အကောင်ရေ မဟုတ်ပါ။",
        "https://savingcranes.org/news/resources/sarus-crane-population-surveys-in-myanmar-discover-new-crane-sites/",
        "Replaces the undated under-800 claim with a dated, explicitly local 2018 direct survey count.",
    ),
    (42, "myanmar_population"): (
        "ba4abf085c0d43a74f8c46552a55a55eb5c005defc772327e32d96dd8411c0cd",
        "၂၀၁၆ ထုတ်ပြန် လေ့လာချက်အရ မြန်မာနိုင်ငံတွင် ကျားသစ် စုစုပေါင်း ၂၂၃–၆၇၀ ကောင်ခန့် (မျိုးပွားနိုင်သော အရွယ်ရောက်အကောင် ၉၄–၂၈၁ ကောင်) ရှိနိုင်သည်ဟု ခန့်မှန်းခဲ့သည်။ ဤသည် သမိုင်းဝင် ခန့်မှန်းချက်ဖြစ်ပြီး ၂၀၂၆ ခုနှစ် လက်ရှိအကောင်ရေကို မဖော်ပြပါ။",
        "https://kpkkt.com.my/storage/upload/2024/06/4D4vXPyPqhQoVEZn7Rh6ZsnZRlIM1LFqVXCCVYhq.pdf",
        "The original 2016 paper gives these two distinct estimates. The previous record misleadingly framed them alongside an unsupported 2026 claim.",
    ),
    (21, "global_population"): (
        "9359926395d6cd2b0e201677140300c18a46085ca8f2b35a3d4995a9e127fbbb",
        "IUCN ၂၀၂၁ အကဲဖြတ်ချက် — ကမ္ဘာတစ်ဝန်း အရွယ်ရောက်ပြီးသော အကောင်ရေ ၃,၇၀၀–၅,၅၈၀ ကောင်ခန့် (ဖြစ်နိုင်ခြေအများဆုံးအပိုင်း)",
        "https://www.catsg.org/living-species-cloudedleopard",
        "The IUCN Cat Specialist Group identifies this as a likely range for mature individuals, not a precise all-age total.",
    ),
    (28, "myanmar_population"): (
        "4d94f103d171a8125d7cd7b65087d234a79a60b8d552ef3f1a5c1e8a5980171d",
        None,
        "https://www.myanmarbiodiversity.org/species/Cynopterus_sphinx_Greater_short_nosed_fruit_bat",
        "The portal's detail describes captures at individual survey sites, not a national estimate of 20–45.",
    ),
    (39, "myanmar_population"): (
        "42143cd07965d8b06adbca7b5a6353f568ae8c6d636ad796ac8581f0d2f80bf6",
        None,
        "https://www.myanmarbiodiversity.org/species/Craseonycteris_thonglongyai_Kittis_Hog_nosed_Bat",
        "1,500 and 3,770 are values reported in old publications, not a recent Myanmar census range.",
    ),
    (39, "wild_population_my"): (
        "91aeb846907334d9e90781706a4a515a6ea5799d705505c30c7b10e10518751f",
        "၂၀၀၆ နှင့် ၂၀၁၃ ခုနှစ် ထုတ်ပြန်စာတမ်းများတွင် မြန်မာနိုင်ငံအတွက် အကောင်ရေ ၁,၅၀၀ နှင့် ၃,၇၇၀ ဟု အသီးသီး ဖော်ပြထားသည်။ ဤသည် ထုတ်ပြန်သည့်နှစ်အလိုက် သမိုင်းဝင် ခန့်မှန်းချက်များဖြစ်ပြီး လက်ရှိအကောင်ရေ မဟုတ်ပါ။",
        "https://www.myanmarbiodiversity.org/species/Craseonycteris_thonglongyai_Kittis_Hog_nosed_Bat",
        "Labels old publication figures as historical; the original wording implied a current count and assigned publication years as census years.",
    ),
    (44, "myanmar_population"): (
        "346b59ac873586cf721675df47eb519de9bb17d773c195e2700e06abf37475f3",
        None,
        "https://www.myanmarbiodiversity.org/species/Cynopterus_brachyotis_Lesser_Short_nosed_Fruit_Bat",
        "The under-10,000 figure is a tentative old extrapolation, not a current national count.",
    ),
    (44, "wild_population_my"): (
        "de62910f3e7055ab3769d5b42f3b584ecf06417e67ffb6b5a02069064fca1255",
        "၂၀၁၂ ခုနှစ် မြစ်ဆုံဒေသ စစ်တမ်းတွင် ဤမျိုးစိတ် ၅ ကောင်ကို မှတ်တမ်းတင်ခဲ့သည်။ ဤအရေအတွက်သည် စစ်တမ်းဧရိယာတစ်ခုအတွက်သာဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း အကောင်ရေမဟုတ်ပါ။",
        "https://www.myanmarbiodiversity.org/species/Cynopterus_brachyotis_Lesser_Short_nosed_Fruit_Bat",
        "Replaces 'recent survey' with the source's 2012 study year and removes an unsupported national extrapolation.",
    ),
    (79, "myanmar_population"): (
        "618c8d0a7f6ab0439e9c36d2e6b6def0cdcbc1fb0ad41cf74de7dbb2289d1ff9",
        "၂၀၂၄ ခန့်မှန်းချက် — မြန်မာနိုင်ငံတွင် အရွယ်ရောက်ပြီးသော အကောင်ရေ ၄၀–၁၀၀ ကောင်",
        "https://media.eaza.net/uploads/202508_Published_WWD_Best_Practice_Guidelines_4e510b9bc5.pdf",
        "2025 EAZA guidance reports the 2024 cautious Myanmar estimate and specifies mature birds.",
    ),
    (79, "global_population"): (
        "b69e63e44fad614e71fc83b1819a23d83841f504a94b643ca6e8f179ec9a01a4",
        "၂၀၂၄ ခန့်မှန်းချက် — ကမ္ဘာတစ်ဝန်း အရွယ်ရောက်ပြီးသော အကောင်ရေ ၁၅၀–၄၅၀ ကောင်",
        "https://media.eaza.net/uploads/202508_Published_WWD_Best_Practice_Guidelines_4e510b9bc5.pdf",
        "2024 BirdLife reassessment supersedes the old 250–999 mature-individual band.",
    ),
    (79, "wild_population_my"): (
        "d6125814e1951be869818380a13f3c184f114ea6f71ddc17bdf45a36aed352cd",
        "၂၀၂၄ ခန့်မှန်းချက်အရ မြန်မာနိုင်ငံတွင် ကြိုးခွေငှက် အရွယ်ရောက်ပြီးသော အကောင်ရေ ၄၀–၁၀၀ ကောင်ခန့် ရှိနိုင်သည်။ ဤသည် စစ်တမ်းဖြင့် တစ်ကောင်ချင်း ရေတွက်ထားသော စုစုပေါင်းမဟုတ်ဘဲ သတိထား၍ ခန့်မှန်းထားသော အပိုင်းအခြားဖြစ်သည်။",
        "https://media.eaza.net/uploads/202508_Published_WWD_Best_Practice_Guidelines_4e510b9bc5.pdf",
        "Replaces an undated under-100 claim with a dated and qualified assessment.",
    ),
    (55, "global_population"): (
        "2d2a952de0c162997446b5bfa620e7b1189c349f3456c8d0ff8a3a4515c79e5b",
        None,
        "https://www.sciencedirect.com/science/article/pii/S2351989425003646",
        "The supposed global total of 100 is below the roughly 400 animals held in one Indian conservation breeding programme in 2025.",
    ),
    (55, "wild_population_my"): (
        "405e1d8b0c0c5fb97641e91cebc7706cb3bd8d4996cd6c5d321d349a01a27220",
        None,
        "https://www.sciencedirect.com/science/article/pii/S2351989425003646",
        "Undated 'recent' Myanmar wording relies on historical reports and does not establish a current Myanmar wild count.",
    ),
    (69, "myanmar_population"): (
        "77af4f8730d297d19d18da0ace110ecc6564c7b97b8db2adfef9da4a92291ceb",
        None,
        "https://eaaflyway.org/gulf-of-mottama-place-for-sbs-non-breeding-season/",
        "The old upper bound is not a current country-wide count; the current source reports a site survey only.",
    ),
    (69, "global_population"): (
        "f6b3ac35a4aa8fc8f67a1f87890a72c04ff0da8728f94341865c0161c916b049",
        "၂၀၂၄ ခန့်မှန်းချက် — ကမ္ဘာတစ်ဝန်း အရွယ်ရောက်ပြီးသော အကောင်ရေ ၃၃၀–၅၅၀ ကောင်",
        "https://eaaflyway.org/wp-content/uploads/2025/11/DD.14_ISSAP_for_the_Conservation_of_the_SBS.pdf",
        "Newer species action plan gives a 2024 estimate and specifies mature individuals.",
    ),
    (69, "wild_population_my"): (
        "baf27e379b634bb8bb0e61f1df88cd4292086b6be21fd2e5844583c2d4f05e0f",
        "၂၀၂၅ ခုနှစ် မုတ္တမကွေ့ စစ်တမ်းတွင် ရေညှောင့်နှုတ်ဝိုင်းငှက် ၅၂ ကောင်ကို တိုက်ရိုက် တွေ့ရှိခဲ့သည်။ ဤသည် စစ်တမ်းဧရိယာအတွင်း တွေ့ရှိမှုသာဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း စုစုပေါင်းအကောင်ရေ မဟုတ်ပါ။",
        "https://eaaflyway.org/gulf-of-mottama-place-for-sbs-non-breeding-season/",
        "Replaces an undated upper bound with a dated, explicitly local direct observation.",
    ),
    (76, "myanmar_population"): (
        "64c892e9397bb9f8372e375bb41955c026af12f6f3c48e35d5b88187228d0c6c",
        None,
        "https://www.cambridge.org/core/journals/oryx/article/conservation-in-response-to-a-crisis-initiating-communityled-conservation-for-the-whitebellied-heron-ardea-insignis-in-northern-myanmar/74127D3E165D2851356506F9721079AF",
        "The old upper bound is not a current Myanmar-wide census; recent research estimates one local population only.",
    ),
    (76, "global_population"): (
        "81afb7b3598957a633d0db3f9893ac5a4cb99ba57d8b05bc03a08a6de51f7aaf",
        "၂၀၂၆ လေ့လာချက် — ကမ္ဘာတစ်ဝန်း တောရိုင်းတွင် အရွယ်ရောက်ပြီးသော အကောင်ရေ ၆၀ အောက်",
        "https://academic.oup.com/auk/article/143/3/1/8586360",
        "Newer study estimates fewer than 60 mature individuals in the wild.",
    ),
    (76, "wild_population_my"): (
        "c18c6b376a8e325b9345bea6863b19d4cc5ee8422a1ae69ff8c26584a26996ce",
        "၂၀၂၂–၂၀၂၃ ခုနှစ် မြန်မာနိုင်ငံမြောက်ပိုင်း စစ်တမ်းဧရိယာတွင် ငဟစ်ဝမ်းဖြူ ၃–၅ ကောင်ရှိမည်ဟု ခန့်မှန်းခဲ့သည်။ ဤသည် ဒေသတစ်ခု၏ ခန့်မှန်းချက်ဖြစ်ပြီး မြန်မာနိုင်ငံတစ်ဝန်း အကောင်ရေ မဟုတ်ပါ။",
        "https://www.cambridge.org/core/journals/oryx/article/conservation-in-response-to-a-crisis-initiating-communityled-conservation-for-the-whitebellied-heron-ardea-insignis-in-northern-myanmar/74127D3E165D2851356506F9721079AF",
        "Replaces an undated estimate of about 50 with a dated local study that states its survey scope.",
    ),
}


def main():
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    completed = {(item["animal_id"], item["field"]) for item in prior}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        with conn:
            for (animal_id, field), (digest, new_value, evidence, reason) in UPDATES.items():
                if (animal_id, field) in completed:
                    continue
                row = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                if row is None:
                    raise LookupError(animal_id)
                old_value = row[field]
                if old_value is None or hashlib.sha256(old_value.encode()).hexdigest() != digest:
                    raise ValueError(f"Reviewed value changed: {animal_id} {field}")
                sources = decode_field_sources(row["field_sources"])
                old_sources = sources.pop(field, [])
                if new_value is not None:
                    sources[field] = [evidence] if isinstance(evidence, str) else list(evidence)
                conn.execute(
                    f"UPDATE animals SET {field} = ?, field_sources = ? WHERE id = ?",
                    (new_value, json.dumps(sources, ensure_ascii=False), animal_id),
                )
                changes.append({
                    "animal_id": animal_id, "name_my": row["name_my"],
                    "name_en": row["name_en"], "field": field,
                    "old_value": old_value, "new_value": new_value,
                    "old_sources": old_sources,
                    "new_sources": sources.get(field, []),
                    "reason": reason, "evidence_url": evidence,
                })
            if changes:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                LOG.write_text(json.dumps(prior + changes, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        conn.close()
    print(f"Updated {len(changes)} field values across {len({x['animal_id'] for x in changes})} animals")
    print(LOG)


if __name__ == "__main__":
    main()
