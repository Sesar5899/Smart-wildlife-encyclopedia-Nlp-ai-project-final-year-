"""Attach manually reviewed semantic evidence for animal descriptions/habitats.

The hashes pin each verdict to the exact published paragraph. A changed
paragraph needs another review before this script can attribute it.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from provenance import decode_field_sources, decode_sources


DB = Path(__file__).with_name("wildlife.db")
REPORT = Path(__file__).with_name("docs") / "description_habitat_source_review.md"

REVIEW_NOTES = {
    8: "ငါးဖမ်းမှုလွန်ကဲခြင်း၊ မျိုးပွားနှုန်းနှင့် ဒေသမျိုးရင်းမဟုတ်သောသားကောင်များကို ဤမျိုးစိတ်အတွက် တစ်စုတစ်စည်းတည်း အတည်ပြုမရသေး။",
    25: "စာသားရှိ ၂၄ စတုရန်းကီလိုမီတာနှင့် မျိုးသုဉ်းရန်အန္တရာယ်အဆင့်ကို ဤမျိုးစိတ်၏ လက်ရှိအကဲဖြတ်ချက်နှင့် တိုက်စစ်ရန်လိုသည်။",
    95: "မှတ်တမ်းတွင် Neofelis diardi ဟုရေးထားသော်လည်း ယင်းမျိုးစိတ်၏ သိရှိထားသောနေရာမှာ ဘော်နီယိုနှင့် ဆူမတြား ဖြစ်သည်။ မြန်မာနိုင်ငံဆိုင်ရာစာသားကို မျိုးစိတ်ပြန်စစ်ရန်လိုသည်။",
    103: "ဆူမတြားကြံ့သည် အမွေးအများဆုံးရှိသော ကြံ့မျိုးစိတ်ဟု source များဖော်ပြသော်လည်း တစ်မျိုးတည်းသာ အမွေးရှိသည်ဆိုသောစာသားကို မထောက်ခံ။",
    106: "ကတိုးမျိုးစိတ်များစွာကို field တစ်ခုတည်းတွင် ပေါင်းဖော်ပြထားသည်။ မျိုးစိတ်တစ်ခု၏ source ဖြင့် အားလုံးကို မအတည်ပြုနိုင်။",
    111: "Naemorhedus griseus ကို မြန်မာမြောက်ပိုင်းတွင် ရှိနိုင်သည်ဟု နောက်ဆုံး checklist က ဖော်ပြထားပြီး taxonomy လည်း မတည်ငြိမ်သေး။ မြန်မာမှတ်တမ်းနှင့် နေထိုင်ရာအသေးစိတ်ကို ဆက်စစ်ရန်လိုသည်။",
    131: "လင်းပိုင်အကောင်ရေနှင့် ဖြန့်ကျက်ဒေသဆိုင်ရာ အချက်များကို သီးခြား၊ နောက်ဆုံးပေါ် source ဖြင့် ဆက်စစ်ရန်လိုသည်။",
    158: "Megalaimidae သည် မျိုးစိတ်တစ်ခုမဟုတ်ဘဲ မျိုးရင်းဖြစ်သည်။ စာသားတစ်ခုလုံးကို မျိုးရင်းအဆင့်တွင် စစ်ရန်လိုသည်။",
    169: "Gallus gallus က မျိုးစေ့ဖြန့်ဝေသည်ဆိုသော ဖော်ပြချက်ကို မအတည်ပြုရသေး။",
    177: "Columbidae သည် မျိုးစိတ်တစ်ခုမဟုတ်ဘဲ မျိုးရင်းဖြစ်သည်။ မျိုးရင်းအဆင့်တွင် ပြန်စစ်ရန်လိုသည်။",
    179: "Chloropseidae သည် မျိုးစိတ်တစ်ခုမဟုတ်ဘဲ မျိုးရင်းဖြစ်သည်။ မျိုးရင်းအဆင့်တွင် ပြန်စစ်ရန်လိုသည်။",
    184: "နေထိုင်မှုစာသားရှိ မြန်မာဒေသအားလုံးကို စစ်ထားသော checklist က တစ်ခုချင်းမထောက်ခံသေး။",
    186: "Tragulus သည် genus ဖြစ်သဖြင့် မျိုးစိတ်သီးသန့်ဖော်ပြချက်များကို taxonomy ပြန်စစ်ရန်လိုသည်။",
    192: "နေထိုင်မှုစာသားတွင် အပူပိုင်းသစ်တောပါသော်လည်း စစ်ထားသော Vulpes vulpes source များက ရှင်းလင်းစွာ မထောက်ခံသေး။",
    193: "Database တွင် Arctonyx spp. ဟုရှိပြီး ဖော်ပြချက်တွင် Arctonyx collaris ဟုဆိုထားသည်။ မျိုးစိတ်သတ်မှတ်ချက် အရင်ညှိရန်လိုသည်။",
    194: "Javan rhino အတွက် အပူပိုင်းတော၊ စိမ့်မြေနှင့် ရွှံ့လူးရာကို source များထောက်ခံသော်လည်း သမပိုင်းအမြဲစိမ်းသစ်တောဟူသော အချက်ကို မအတည်ပြုရသေး။",
    207: "စိမ့်မြေနှင့် နေ့ဘက်ခိုအောင်းရာအမျိုးမျိုးကို စစ်ထားသော source များက အပြည့်အစုံ မထောက်ခံသေး။",
    210: "နေထိုင်ရာစာရင်းနှင့် နှစ်သက်သောနေရာကို မျိုးစိတ်သီးသန့် source ပိုမိုခိုင်မာစွာ ရှာစစ်ရန်လိုသည်။",
    212: "တွင်းကို အသုံးပြုခြင်းသာ အတည်ပြုရသေးပြီး ကိုယ်တိုင်တွင်းတူးသည်ဆိုသည်ကို မအတည်ပြုရသေး။",
}

# Each source was inspected for the claims in the corresponding full field.
# A pair of URLs can jointly support a paragraph when neither does alone.
VERIFIED = {
    2: {
        "scientific_name": "Elephas maximus",
        "fields": {
            "description_my": (
                "19fd45ce6cb548f6fa9ae1f4a502fcd541526f959cc60b650fd433d5450c7d21",
                (
                    ("WWF — Asian elephants", "https://www.worldwildlife.org/species/elephant/asian-elephant/"),
                    ("WWF — elephant species and social behaviour", "https://www.worldwildlife.org/species/elephant/"),
                    ("Smithsonian — Asian elephant", "https://nationalzoo.si.edu/animals/asian-elephant"),
                    ("Myanmar Biodiversity Portal — Asian Elephant", "https://www.myanmarbiodiversity.org/species/Elephas_maximus_Asian_Elephant"),
                ),
            ),
            "habitat_my": (
                "fd713a2c441594a407aa6a56ad105eac3acd71406cf492f7848290fd760ce6fc",
                (
                    ("WWF — Asian elephant habitat and corridors (PDF)", "https://assets.worldwildlife.org/www-prd/documents/9izehtmuji_2021_12_5_AsETWG_Primer_final_en.pdf"),
                    ("WWF UK — Asian elephant habitats", "https://www.wwf.org.uk/learn/wildlife/asian-elephant"),
                ),
            ),
        },
    },
    4: {
        "scientific_name": "Ursus thibetanus",
        "fields": {
            "description_my": (
                "d42d1831c7de119eeebd1a8ee3c0d47cbd739af5f0f27713ec561a466bc8e95f",
                (
                    ("IUCN SSC Bear Specialist Group — Asiatic Black Bear", "https://www.globalbearconservation.org/Species/species_cls/7"),
                    ("International Association for Bear Research — Asiatic Black Bear", "https://www.bearbiology.org/the-eight-bear-species/ursus-thibetanus-asiatic-black-bear/"),
                ),
            ),
            "habitat_my": (
                "5e711ff53c438c6d18f3a1dd2c5404de09cb9d12fe22afd791102bf53cd58d6c",
                (
                    ("International Association for Bear Research — Asiatic Black Bear habitat", "https://www.bearbiology.org/the-eight-bear-species/ursus-thibetanus-asiatic-black-bear/"),
                    ("Myanmar Biodiversity Portal — Asiatic Black Bear", "https://www.myanmarbiodiversity.org/species/Ursus_thibetanus_Asiatic_Black_Bear"),
                ),
            ),
        },
    },
    5: {
        "scientific_name": "Catopuma temminckii",
        "fields": {
            "description_my": (
                "fcceee470d3c6af748e6e044d94da6fb9c0f2a86c1db12d460fec8205f5ce940",
                (
                    ("IUCN SSC Cat Specialist Group — Asian Golden Cat", "https://www.catsg.org/living-species-asiangoldencat"),
                    ("Myanmar Biodiversity Portal — Asiatic Golden Cat", "https://www.myanmarbiodiversity.org/species/Catopuma_temminckii_Asiatic_Golden_Cat"),
                    ("Myanmar Forest Department — Notification 690/2020 (PDF)", "https://www.myanmartradeportal.gov.mm/uploads/legals/2021/6/Notification%20690-2021.pdf"),
                ),
            ),
            "habitat_my": (
                "0559b0a839849b7a3882c024197edf3baa2a7d4032031f3e675f418a09b97c89",
                (
                    ("Myanmar Biodiversity Portal — Asiatic Golden Cat", "https://www.myanmarbiodiversity.org/species/Catopuma_temminckii_Asiatic_Golden_Cat"),
                    ("IUCN SSC Cat Specialist Group — Asian Golden Cat", "https://www.catsg.org/living-species-asiangoldencat"),
                ),
            ),
        },
    },
    7: {
        "scientific_name": "Bos javanicus",
        "fields": {
            "description_my": (
                "85b020640fee867f86b4b80cbc9ed6268033f17dff82133f22868a38e01982aa",
                (
                    ("Mammals of Myanmar: an annotated checklist (PDF)", "https://www.rhinoresourcecenter.com/pdf_files/171/1712413987.pdf"),
                    ("IUCN SSC Asian Wild Cattle Specialist Group — banteng", "https://www.asianwildcattle.org/news.html"),
                    ("Population structure and domestication history of Javan banteng", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12829435/"),
                    ("Myanmar Biodiversity Portal — Banteng", "https://www.myanmarbiodiversity.org/species/Bos_javanicus_Banteng"),
                ),
            ),
            "habitat_my": (
                "771eeae9b945f48e75519334175b1a20754e7d7b26037b276754154887d5ec29",
                (
                    ("Myanmar Biodiversity Portal — Banteng", "https://www.myanmarbiodiversity.org/species/Bos_javanicus_Banteng"),
                    ("Banteng habitat study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC10376307/"),
                ),
            ),
        },
    },
    40: {
        "scientific_name": "Hylobates lar",
        "fields": {
            "description_my": (
                "6c6d08889351f2415102423e22faf3813bcf2c752a042c08ea488c4f3207444a",
                (("UW–Madison National Primate Research Center — Lar gibbon", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-lar-gibbon/"),),
            ),
            "habitat_my": (
                "bc3035ef79e69d5a151b3530ce9d1f4734d8dea77719eef6a487798bcc82bad1",
                (("UW–Madison National Primate Research Center — Lar gibbon", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-lar-gibbon/"),),
            ),
        },
    },
    49: {
        "scientific_name": "Tapirus indicus",
        "fields": {
            "description_my": (
                "a6a54641e159230cdece5390f6eae431a3544c1416a9b062d978d5bf3f77e426",
                (
                    ("IUCN SSC Tapir Specialist Group — Malayan tapir", "https://tapirs.org/tapirs/"),
                    ("Denver Zoo — Malayan tapir anatomy", "https://denverzoo.org/animals/malayan-tapir/"),
                ),
            ),
            "habitat_my": (
                "816962d1eff30fddbde25f07e614bba038182d2a5b215d162dc246c782c13880",
                (
                    ("Animal Diversity Web — Malayan tapir habitat", "https://animaldiversity.org/accounts/Tapirus_indicus/"),
                    ("Denver Zoo — Malayan tapir habitats", "https://denverzoo.org/animals/malayan-tapir/"),
                ),
            ),
        },
    },
    59: {
        "scientific_name": "Macaca mulatta",
        "fields": {
            "description_my": (
                "02337bd011a30cf66d25be605a1f1cee0e03df33e7c6ddc1766cac8362557c6e",
                (
                    ("Myanmar Biodiversity Portal — Rhesus Macaque", "https://www.myanmarbiodiversity.org/species/Macaca_mulatta_Rhesus_Macaque"),
                    ("UW–Madison National Primate Research Center — Rhesus macaque", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-rhesus-macaque/"),
                ),
            ),
            "habitat_my": (
                "e9682a77264fbeed0e47add64b9e5a0b49f847a7d638261829179a191b76227b",
                (
                    ("Myanmar Biodiversity Portal — Rhesus Macaque habitat", "https://www.myanmarbiodiversity.org/species/Macaca_mulatta_Rhesus_Macaque"),
                    ("UW–Madison National Primate Research Center — Rhesus macaque habitat", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-rhesus-macaque/"),
                ),
            ),
        },
    },
    74: {
        "scientific_name": "Panthera tigris",
        "fields": {
            "description_my": (
                "ba26e1b16aa163a0195ab449fc216edf8cacd5fa1640786665ea2b9510e66d7a",
                (
                    ("WWF — Tiger", "https://www.worldwildlife.org/species/tiger/"),
                    ("Myanmar Biodiversity Portal — Tiger", "https://www.myanmarbiodiversity.org/species/Panthera_tigris_Tiger"),
                ),
            ),
            "habitat_my": (
                "72a00ac449450e590dd9a38bc3e99c5c14e1522012373f79b082e8aedd61dbcc",
                (
                    ("WWF — Tiger habitats and territory", "https://www.worldwildlife.org/species/tiger/"),
                    ("Myanmar Biodiversity Portal — Tiger habitats", "https://www.myanmarbiodiversity.org/species/Panthera_tigris_Tiger"),
                ),
            ),
        },
    },
    82: {
        "scientific_name": "Manis javanica",
        "fields": {
            "description_my": (
                "1fcf15d075b65328bfcc251f2465b14777a1244ef9508210f2b3a434a627379c",
                (
                    ("IUCN SSC Pangolin Specialist Group — Sunda pangolin", "https://pangolinsg.org/portfolio/sunda-pangolin/"),
                    ("Singapore National Parks — Sunda pangolin ecology and threats", "https://www.nparks.gov.sg/florafaunaweb/fauna/2/1/212"),
                    ("Singapore Animal and Veterinary Service — pangolin scales", "https://avs.nparks.gov.sg/wildlife/encountering-wildlife/pangolins/"),
                ),
            ),
            "habitat_my": (
                "23793454a928ac6f915a90ba0f8e12a9b7a52740af4f7b4f81c22be9771117a9",
                (
                    ("Animal Diversity Web — Sunda pangolin habitat and burrows", "https://animaldiversity.org/accounts/Manis_javanica/"),
                    ("World Bank — Sunda pangolin forest and agricultural habitats (PDF)", "https://documents1.worldbank.org/curated/en/981561468041078798/pdf/E1050v3rev-EAMP-March20050Annexes010.pdf"),
                ),
            ),
        },
    },
    83: {
        "scientific_name": "Manis pentadactyla",
        "fields": {
            "description_my": (
                "842c567d391694b973ff36f882c809d19f1db854f5a303b0f0ca25405c628902",
                (
                    ("IUCN SSC Pangolin Specialist Group — Chinese pangolin", "https://pangolinsg.org/portfolio/chinese-pangolin/"),
                    ("Hong Kong AFCD — Chinese Pangolin Species Action Plan (PDF)", "https://www.afcd.gov.hk/english/conservation/hkbiodiversity/speciesgroup/files/Chinese_Pangolin_SAP_Dec2019.pdf"),
                    ("IUCN — pangolin poaching and habitat degradation", "https://portals.iucn.org/library/sites/library/files/documents/iucn-wcc-6th-005.pdf"),
                ),
            ),
            "habitat_my": (
                "a25e02798190d04b55c59d0c4151c1725e3bd858f9ca7fa29a81bcbcc80a57e2",
                (
                    ("Chinese pangolin habitat survey", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12291737/"),
                    ("Hong Kong AFCD — Chinese Pangolin Species Action Plan (PDF)", "https://www.afcd.gov.hk/english/conservation/hkbiodiversity/speciesgroup/files/Chinese_Pangolin_SAP_Dec2019.pdf"),
                ),
            ),
        },
    },
    85: {
        "scientific_name": "Nycticebus bengalensis",
        "fields": {
            "description_my": (
                "f800defb3719c231f07ad060a9a0263eb9e08a6181ec3458bc575b2230223c33",
                (
                    ("Bengal slow loris ecology and conservation study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12099303/"),
                    ("Slow loris venom study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6055083/"),
                    ("Animal Diversity Web — Bengal slow loris", "https://animaldiversity.org/accounts/Nycticebus_bengalensis/"),
                ),
            ),
            "habitat_my": (
                "94dc7ddcf0be6ef3733ba46f599d2d686b2a3a18eea318661519c9c68ee3d6c5",
                (
                    ("ICIMOD — Primates of the Far Eastern Himalaya (PDF)", "https://lib.icimod.org/records/z2yj8-d8s08/files/HimalDoc2021_Primates_of_the_FarEasternHimalaya.pdf?download=1"),
                    ("Animal Diversity Web — Bengal slow loris habitat", "https://animaldiversity.org/accounts/Nycticebus_bengalensis/"),
                ),
            ),
        },
    },
    88: {
        "scientific_name": "Macaca arctoides",
        "fields": {
            "description_my": (
                "7be6c8fb9da95f82a3d146d23e09e277b0dfb541c3d28dc8f90af4155edbd3c6",
                (("UW–Madison National Primate Research Center — Stump-tailed macaque", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-stump-tailed-macaque/"),),
            ),
            "habitat_my": (
                "d0b18c89e5975aa1e81c8b5e60eb46820696d1a39fd4dcdc3fda20479e30ffed",
                (
                    ("ICIMOD — Primates of the Far Eastern Himalaya (PDF)", "https://lib.icimod.org/records/z2yj8-d8s08/files/HimalDoc2021_Primates_of_the_FarEasternHimalaya.pdf?download=1"),
                    ("UW–Madison National Primate Research Center — Stump-tailed macaque habitat", "https://primate.wisc.edu/primate-info-net/pin-factsheets/pin-factsheet-stump-tailed-macaque/"),
                ),
            ),
        },
    },
    93: {
        "scientific_name": "Cuon alpinus",
        "fields": {
            "description_my": (
                "305c9f292d364618722b6cb992273e68b2c559c057a17e93dfea64d731b8c108",
                (
                    ("IUCN SSC Canid Specialist Group — Dhole", "https://www.canids.org/species/view/PREKQW171301"),
                    ("Canid Biology and Conservation — Dhole (PDF)", "https://www.canids.org/CBC/23/Dhole_wolf_association.pdf"),
                ),
            ),
            "habitat_my": (
                "a8a0200dec4f53747cef582a732a33049cbb367e4f0f27c27ca0d37daf1117ee",
                (("IUCN SSC Canid Specialist Group — Dhole habitat", "https://www.canids.org/species/view/PREKQW171301"),),
            ),
        },
    },
    94: {
        "scientific_name": "Ailurus fulgens",
        "fields": {
            "description_my": (
                "357ef27c1cf7386907e4ae471c978d5bc4c173cae83cad7be16687b97f263908",
                (
                    ("Smithsonian National Zoo — Red panda", "https://nationalzoo.si.edu/animals/red-panda"),
                    ("WWF — Red panda report (PDF)", "https://files.worldwildlife.org/wwfcmsprod/files/Publication/file/3duh1dztfc_red_panda_report_2_.pdf"),
                ),
            ),
            "habitat_my": (
                "6a01d759ee89de59b0e749b434f097937ce972cabe45a4a28efbf86d5b9a816b",
                (
                    ("WWF — Red panda report (PDF)", "https://files.worldwildlife.org/wwfcmsprod/files/Publication/file/3duh1dztfc_red_panda_report_2_.pdf"),
                    ("Red panda habitat study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC3198399/"),
                ),
            ),
        },
    },
    97: {
        "scientific_name": "Lutrogale perspicillata",
        "fields": {
            "description_my": (
                "f5589f327e105a58e8f877f4b233ff46cef67dccc90563a04a3555d47c91754f",
                (
                    ("IUCN SSC Otter Specialist Group — Smooth-coated Otter", "https://www.otterspecialistgroup.org/otter-species/lutrogale-perspicillata/"),
                    ("IUCN Red List — Smooth-coated Otter (PDF)", "https://www.otterspecialistgroup.org/osg-newsite/wp-content/uploads/2018/03/9.-Lutrogale-perspicillata-Red-List-2020.pdf"),
                ),
            ),
            "habitat_my": (
                "ebe02a036098edeeb01085cd01f2721e5de3c31740e7c1a8c5690ecdb27dcbbe",
                (("IUCN Red List — Smooth-coated Otter habitat (PDF)", "https://www.otterspecialistgroup.org/osg-newsite/wp-content/uploads/2018/03/9.-Lutrogale-perspicillata-Red-List-2020.pdf"),),
            ),
        },
    },
    98: {
        "scientific_name": "Lutra lutra",
        "fields": {
            "description_my": (
                "d71798356b38d169e1c3aea696b0f09a2475349d512ffb2ece163f2465fe470b",
                (
                    ("IUCN SSC Otter Specialist Group — Eurasian Otter", "https://www.otterspecialistgroup.org/otter-species/lutra-lutra/"),
                    ("Mammals of Myanmar: an annotated checklist (PDF)", "https://ir.xtbg.ac.cn/bitstream/353005/14067/1/Mammals%20of%20Myanmar_%20an%20annotated%20checklist.pdf"),
                    ("IUCN SSC Otter Specialist Group — Otter taxonomy", "https://www.otterspecialistgroup.org/otter-species/"),
                ),
            ),
            "habitat_my": (
                "63529997e2a3829b3317cfb616a85054e4facfd50b913784cb2e214bc5f5edca",
                (
                    ("IUCN SSC Otter Specialist Group — Otter aquatic habitat review", "https://iucnosgbull.org/Volume36A/Brooks_Serfass_2019.html"),
                    ("Government of India — Eurasian Otter habitat", "https://nmcg.nic.in/mammals.aspx"),
                    ("IUCN UK Peatland Programme — European Otter", "https://www.iucn-uk-peatlandprogramme.org/wildlife-explorer/mammals/european-otter"),
                ),
            ),
        },
    },
    99: {
        "scientific_name": "Lutra sumatrana",
        "fields": {
            "description_my": (
                "9b8d0d172c0935f3ddc492aa92a4c3251d9c7f7c1ccad3e4c6545b991e574715",
                (("IUCN SSC Otter Specialist Group — Hairy-nosed Otter", "https://www.otterspecialistgroup.org/otter-species/lutra-sumatrana/"),),
            ),
            "habitat_my": (
                "922bfd469c63a64ebbe424c5a8cd606ca936e9c13c75e270e1b44def5cd4d145",
                (("IUCN Red List — Hairy-nosed Otter habitats (PDF)", "https://www.otterspecialistgroup.org/osg-newsite/wp-content/uploads/2018/03/8.-Lutra-sumatrana-Red-List-2020.pdf"),),
            ),
        },
    },
    139: {
        "scientific_name": "Rhodonessa caryophyllacea",
        "fields": {
            "description_my": (
                "b2cadd5b3d6601267ff2a1a02e4ef188dc4be59ba65c7e1a7ceb8fd000988941",
                (("BirdLife International — Pink-headed Duck species account (PDF)", "https://birdlifedata.blob.core.windows.net/red-data-books/rhodcary.pdf"),),
            ),
            "habitat_my": (
                "dd259c287869b507b9dbd4e159d8283512a8217d35015ef18812bfc4054f50a5",
                (("BirdLife International — Pink-headed Duck habitat (PDF)", "https://birdlifedata.blob.core.windows.net/red-data-books/rhodcary.pdf"),),
            ),
        },
    },
    143: {
        "scientific_name": "Caloenas nicobarica",
        "fields": {
            "description_my": (
                "853c2f54e76b0d0dbdba364be2bccc6e439a28e925dd3480ae007f1f647271d2",
                (
                    ("Oxford University Museum — Nicobar pigeon and dodo", "https://www.oumnh.ox.ac.uk/learn-how-did-dodo-evolve"),
                    ("Toronto Zoo — Nicobar pigeon", "https://www.torontozoo.com/animals/Nicobar%20pigeon"),
                    ("Nicobar pigeon genome study", "https://doi.org/10.1093/jhered/esaf031"),
                    ("Nicobar pigeon breeding range review (PDF)", "https://www.dolphininstitute.ac.in/wp-content/uploads/2020/09/July-Sept.-2017-Edit.pdf"),
                ),
            ),
            "habitat_my": (
                "4c89eba2128a062e49ef97d96f5c05b2faa0703f6620bb5b2888367ffe8a3220",
                (
                    ("Toronto Zoo — Nicobar pigeon habitat", "https://www.torontozoo.com/animals/Nicobar%20pigeon"),
                    ("Nicobar pigeon nesting colony study", "https://www.researchgate.net/publication/369761893_The_incredible_Nicobar_Pigeon_Caloenas_nicobarica_nesting_colony_on_Pulau_Jiew_North_Maluku_Indonesia"),
                ),
            ),
        },
    },
    144: {
        "scientific_name": "Grus nigricollis",
        "fields": {
            "description_my": (
                "514f132954bb81d385e0c48b360392578ed6cbc518b6a1aa8d8772a924b29cbb",
                (("International Crane Foundation — Cranes status survey (PDF)", "https://savingcranes.org/wp-content/uploads/2024/11/the_cranes_status_survey_and_action_plan.pdf"),),
            ),
            "habitat_my": (
                "bb924bcad18c3b7a468edd3cd86f6b66e6c16608392362d60ba94d982a697786",
                (
                    ("International Crane Foundation — Cranes status survey (PDF)", "https://savingcranes.org/wp-content/uploads/2024/11/the_cranes_status_survey_and_action_plan.pdf"),
                    ("Royal Society for Protection of Nature Bhutan — Black-necked Crane (PDF)", "https://www.rspnbhutan.org/wp-content/uploads/2023/10/BNC-Brochure_Digital_Original.pdf"),
                    ("Black-necked Crane nesting habitat study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5289107/"),
                ),
            ),
        },
    },
    157: {
        "scientific_name": "Coracias benghalensis",
        "fields": {
            "description_my": (
                "00798b839493c69e519be896d68c08930a16421b835860bbb91dbb92b87999a9",
                (
                    ("CSIR-NEERI Biodiversity Portal — Indian Roller", "https://neeriathome.neeri.res.in/biodiversity/IndianRoller.php"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
            "habitat_my": (
                "cd3716449879ddea3269cd06ca27aab5041d14078a41543b9bf6f87ffb03e823",
                (
                    ("CSIR-NEERI Biodiversity Portal — Indian Roller habitat", "https://neeriathome.neeri.res.in/biodiversity/IndianRoller.php"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
        },
    },
    162: {
        "scientific_name": "Acridotheres tristis",
        "fields": {
            "description_my": (
                "bb07c61d437047417bef83903a20baa88218e11ab45ee5c54ff0ea2e8dd4d9a1",
                (("Cornell Lab of Ornithology — Common Myna", "https://www.allaboutbirds.org/guide/commyn"),),
            ),
            "habitat_my": (
                "3632bcb9371090dad0dba874272fcf8506a1af6562f52aad7ad865b740b03aff",
                (
                    ("Cornell Lab of Ornithology — Common Myna", "https://www.allaboutbirds.org/guide/commyn"),
                    ("Cornell Lab of Ornithology — Common Myna nesting", "https://www.allaboutbirds.org/guide/Common_Myna/lifehistory"),
                ),
            ),
        },
    },
    172: {
        "scientific_name": "Chrysococcyx maculatus",
        "fields": {
            "habitat_my": (
                "b39b9cee5a580fb970e23d8decab6ce5ca6f3f7481630f77db28528b33404d5e",
                (
                    ("Bangladesh Forest Department — Asian Emerald Cuckoo distribution (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                    ("Oiseaux.net — Asian Emerald Cuckoo habitat", "https://www.oiseaux.net/en/oiseaux/asian.emerald.cuckoo.html"),
                    ("Bird Society of Singapore — canopy, forest and forest edge", "https://singaporebirds.com/species/asian-emerald-cuckoo/"),
                    ("BirdForum Opus — evergreen forest and forest edges", "https://www.birdforum.net/opus/Chrysococcyx_maculatus"),
                ),
            ),
        },
    },
    174: {
        "scientific_name": "Cacomantis merulinus",
        "fields": {
            "description_my": (
                "11f073ab7b4e65f78d08e040feb667c244b93b99dcac365a44bba3f4c0231d41",
                (
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                    ("Plaintive Cuckoo brood parasitism study", "https://link.springer.com/article/10.1186/s40657-019-0143-z"),
                    ("Wildlife of Lao PDR — species account", "https://www.laofab.org/document/download/4265"),
                ),
            ),
            "habitat_my": (
                "ad9d41e1623ce3a6f9994f34940515ac77a9b91cfdd9c496747e7e1d95abe93c",
                (
                    ("Wildlife of Lao PDR — species account", "https://www.laofab.org/document/download/4265"),
                    ("Plaintive Cuckoo habitat survey (PDF)", "https://gamudaland.com.my/wp-content/uploads/2020/12/Biodiversity-Assessment-for-Celadon-City-2019.pdf"),
                ),
            ),
        },
    },
    145: {
        "scientific_name": "Hypothymis azurea",
        "fields": {
            "description_my": (
                "08a190215068b34a74cab9d7457f2428d940f846a23ab01f5ea7dc2ceae9b97c",
                (
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                    ("Hong Kong Baptist University — Black-naped Monarch", "https://digital.lib.hkbu.edu.hk/hkwildtracks/animal_detail.php?ids=HWT-000044"),
                ),
            ),
            "habitat_my": (
                "038407b73cef6f9ff06cc0ff2eebe54d70e1afb8cb7bec2ab3ec5be07823a9d4",
                (
                    ("Avibase — Black-naped Monarch habitat", "https://avibase.bsc-eoc.org/species.jsp?avibaseid=0AC5BA0A3247344C&lang=EN"),
                    ("Birds of Singapore — Black-naped Monarch", "https://singaporebirds.com/species/black-naped-monarch/"),
                ),
            ),
        },
    },
    146: {
        "scientific_name": "Milvus migrans",
        "fields": {
            "description_my": (
                "c3514a11f8036050a07b6ff3cc389b9fcd41b16853a09bcbe153dbc25df9aa16",
                (("Animal Diversity Web — Black Kite", "https://animaldiversity.org/accounts/Milvus_migrans/"),),
            ),
            "habitat_my": (
                "c72bbb6d5ebb0b05ce9324c15471a5d6c03a2800813fbab53d01d9e367f69e87",
                (
                    ("Animal Diversity Web — Black Kite habitat", "https://animaldiversity.org/accounts/Milvus_migrans/"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
        },
    },
    150: {
        "scientific_name": "Athene brama",
        "fields": {
            "description_my": (
                "938e2c2b7cf92c87b2aee5881c2951fe545258bb93ce96616256bdd79e43bd94",
                (
                    ("CSIR-NEERI Biodiversity Portal — Spotted Owlet", "https://neeriathome.neeri.res.in/biodiversity/SpottedOwlets.php"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
            "habitat_my": (
                "312517322550580494f29e96b90bd02cd2e8a728eaef884c434346a2d84a13d7",
                (
                    ("Spotted Owlet habitat and nesting study", "https://threatenedtaxa.org/index.php/JoTT/article/download/4020/4465?inline=1"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
        },
    },
    177: {
        "scientific_name": "Columbidae",
        "fields": {
            "description_my": (
                "65fb6599f0da122ba3ae1ef02be0ed4c932fca7e1295810b8539a77d52d4eb18",
                (
                    ("University of Michigan Animal Diversity Web — Columbidae", "https://animaldiversity.org/accounts/Columbidae/"),
                    ("British Trust for Ornithology — Columbidae", "https://www.bto.org/learn/about-birds/bird-families/columbidae-pigeons"),
                ),
            ),
            "habitat_my": (
                "4865e6b5f06d0a2efcfa49d9d041affd4c753d2bdd154ac370e9a2fda3b17417",
                (("University of Michigan Animal Diversity Web — Columbidae habitat", "https://animaldiversity.org/accounts/Columbidae/"),),
            ),
        },
    },
    180: {
        "scientific_name": "Lanius schach",
        "fields": {
            "description_my": (
                "9cb9a17db5af03e60f434a8c02053f2128c3b594f57b9a4b68745b00796c7505",
                (
                    ("Great Himalayan National Park — Long-tailed Shrike", "https://greathimalayannationalpark.org/long-tailed-shrike/"),
                    ("Chinese University of Hong Kong — Long-tailed Shrike", "https://srsdo.cuhk.edu.hk/en-gb/trees-and-birds-at-cuhk/birds/long-tail-shrike/"),
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                ),
            ),
            "habitat_my": (
                "443afac8a2f09cd5a776939e235300ee4265648a0b6486e4f850e6a0bcc81e0c",
                (
                    ("Great Himalayan National Park — Long-tailed Shrike habitat", "https://greathimalayannationalpark.org/long-tailed-shrike/"),
                    ("Chinese University of Hong Kong — Long-tailed Shrike", "https://srsdo.cuhk.edu.hk/en-gb/trees-and-birds-at-cuhk/birds/long-tail-shrike/"),
                ),
            ),
        },
    },
    105: {
        "scientific_name": "Bos gaurus",
        "fields": {
            "description_my": (
                "79ba15b1890dc6ee95080b0a991ab205b7a89b28a7b23b984a32e5cc3c8c1d74",
                (
                    ("Oxford Mammalian Species — Gaur", "https://academic.oup.com/mspecies/article/50/959/34/5075367"),
                    ("Bangladesh Red List — Gaur (PDF)", "https://portals.iucn.org/library/sites/library/files/documents/RL-549.3-003-v.2.pdf"),
                ),
            ),
            "habitat_my": (
                "8c41566dc02443c132e7caed69b57404583c41874c61b6d69262900951a4debc",
                (
                    ("Oxford Mammalian Species — Gaur habitat", "https://academic.oup.com/mspecies/article/50/959/34/5075367"),
                    ("Wildlife Institute of India — Gaur studbook (PDF)", "https://digitalrepository.wii.gov.in/server/api/core/bitstreams/e19f87a2-d7ea-48be-8036-12fb60267184/content"),
                ),
            ),
        },
    },
    185: {
        "scientific_name": "Bubalus arnee",
        "fields": {
            "description_my": (
                "104d49af94748a18ba4bbea05b1a8d7af3700794b36463914600f8615160b55e",
                (
                    ("National Trust for Nature Conservation — Wild Water Buffalo", "https://ntnc.org.np/thematic-area/wild-water-buffalo"),
                    ("Wild buffalo domestication genetics study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC4453062/"),
                    ("Wild buffalo conservation genetics", "https://pubmed.ncbi.nlm.nih.gov/33527322/"),
                ),
            ),
            "habitat_my": (
                "f1b30090cddbadf9ae1e9456a154afb7831b7849083263fa6436fc20ce8f748a",
                (
                    ("National Trust for Nature Conservation — Wild Water Buffalo", "https://ntnc.org.np/thematic-area/wild-water-buffalo"),
                    ("Wild buffalo feeding and habitat study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC7391305/"),
                    ("Wild buffalo habitat use study", "https://www.nieindia.org/Journal/index.php/ijees/article/view/2746"),
                ),
            ),
        },
    },
    190: {
        "scientific_name": "Sus scrofa",
        "fields": {
            "description_my": (
                "54eab8d1db75f8f8ee4e8b3716468b8b7c816e341c1c679f3c8ee71e41591e94",
                (
                    ("Mammal Species of the World — Wild Boar distribution", "https://www.departments.bucknell.edu/biology/resources/msw3/browse.asp?id=14200054"),
                    ("Wild boar domestication genetic study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC1461048/"),
                    ("University of Michigan Animal Diversity Web — Wild Boar", "https://animaldiversity.org/accounts/Sus_scrofa/"),
                ),
            ),
            "habitat_my": (
                "a8a5e1ce6a18aa83e5f0936282a07900376726f9f88a9f663ee30c4f54bcd12b",
                (("University of Michigan Animal Diversity Web — Wild Boar habitat", "https://animaldiversity.org/accounts/Sus_scrofa/"),),
            ),
        },
    },
    192: {
        "scientific_name": "Vulpes vulpes",
        "fields": {
            "description_my": (
                "73fb00170fe0da075ebf8807faa65f1c35453413e226caa5c9faab412e30f090",
                (("University of Michigan Animal Diversity Web — Red Fox", "https://animaldiversity.org/accounts/Vulpes_vulpes/"),),
            ),
        },
    },
    92: {
        "scientific_name": "Presbytis femoralis",
        "fields": {
            "description_my": (
                "73113a037925d316c7998875fb1cd382c4d190bcad662b61a218f3edebfbe44d",
                (
                    ("Singapore National Parks — Raffles' Banded Langur", "https://biodiversitysg.nparks.gov.sg/our-biodiversity/mammals/primates/raffles-banded-langur/"),
                    ("Banded Langur dietary field study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9168899/"),
                ),
            ),
            "habitat_my": (
                "d7891a20d12b856441ea65586e22144505e13f2225c8c17f4482f27d6c751672",
                (
                    ("Singapore National Parks — Raffles' Banded Langur", "https://biodiversitysg.nparks.gov.sg/our-biodiversity/mammals/primates/raffles-banded-langur/"),
                    ("Banded Langur dietary field study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9168899/"),
                    ("Ecology Asia — Banded Langur habitats", "https://www.ecologyasia.com/verts/mammals/raffles-banded-langur.htm"),
                ),
            ),
        },
    },
    103: {
        "scientific_name": "Dicerorhinus sumatrensis",
        "fields": {
            "habitat_my": (
                "e45828ed6a2fd6e286aa379b94107627416d4c28ec2c609299649d9b40226121",
                (
                    ("IUCN Red List — Sumatran Rhino assessment (PDF)", "https://www.rhinoresourcecenter.com/pdf_files/172/1724167738.pdf"),
                    ("Sumatran Rhino field research thesis", "https://research.wur.nl/en/publications/sumatran-rhinoceros-dicerorhinus-sumatrensis-fischer-1814-in-the-/"),
                    ("University of Michigan Animal Diversity Web — Sumatran Rhino", "https://animaldiversity.org/accounts/Dicerorhinus_sumatrensis/"),
                ),
            ),
        },
    },
    108: {
        "scientific_name": "Muntiacus gongshanensis",
        "fields": {
            "description_my": (
                "f9d62f501cbdb11ef0be187137d09819f6a8c1b4f7cea4b2cc481a2c4ad6f5c7",
                (
                    ("Gongshan Muntjac morphology and genetics study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9656157/"),
                    ("Deer Specialist Group — Gongshan and Leaf Muntjac (PDF)", "https://www.deerspecialistgroup.org/wp-content/uploads/2021/05/DSG-News-23.pdf"),
                ),
            ),
            "habitat_my": (
                "3f6dde3e39a741becb317888b9d3219bdfe31077393bdc18f93fe264b8732ba8",
                (
                    ("Gongshan Muntjac habitat field study", "https://onlinelibrary.wiley.com/doi/full/10.1002/ece3.71646"),
                    ("University of Michigan Animal Diversity Web — Gongshan Muntjac", "https://animaldiversity.org/accounts/Muntiacus_gongshanensis/"),
                ),
            ),
        },
    },
    175: {
        "scientific_name": "Megalaima haemacephala",
        "fields": {
            "habitat_my": (
                "a59c29e90ff5c28a8e19bcb9c4da320a66b6c08e8e54b034af1dce35f4c003cf",
                (
                    ("Singapore National Parks — Coppersmith Barbet", "https://biodiversitysg.nparks.gov.sg/our-biodiversity/birds/woodpeckers-barbets/coppersmith-barbet/"),
                    ("Singapore National Parks — Fig tree and Coppersmith Barbet", "https://www.nparks.gov.sg/florafaunaweb/flora/2/9/2915"),
                    ("CSIR-NEERI — Coppersmith Barbet", "https://neeriathome.neeri.res.in/biodiversity/coppersmith.php"),
                ),
            ),
        },
    },
    181: {
        "scientific_name": "Eurystomus orientalis",
        "fields": {
            "habitat_my": (
                "79b0f09eca20eb9490a3b7233fdd1b6976741cb21aa02898e848215657762c08",
                (
                    ("Australian Museum — Dollarbird", "https://australian.museum/learn/animals/birds/dollarbird/"),
                    ("Birds of Singapore — Oriental Dollarbird", "https://singaporebirds.com/species/oriental-dollarbird/"),
                ),
            ),
        },
    },
    109: {
        "scientific_name": "Capricornis sumatraensis",
        "fields": {
            "description_my": (
                "ca920103c8702fe58cdab98488392585758eee3a189e8bd27f79943628f22a92",
                (
                    ("Grzimek's Animal Life Encyclopedia — Serow (PDF)", "https://lib.ysu.am/open_books/311929_16.pdf"),
                    ("Myanmar serow trade and conservation study", "https://link.springer.com/article/10.1007/s10344-022-01622-6"),
                    ("Sumatran Mammals field guide (PDF)", "https://www.internationaltigerproject.org/static/media/uploads/pdf/Sumatran_Mammals_FZS_ebook_2020.pdf"),
                ),
            ),
        },
    },
    112: {
        "scientific_name": "Budorcas taxicolor",
        "fields": {
            "description_my": (
                "b4e9c1871554a0d733aa59618b2c04677a56f184cbaecbe19b0ee86ab12b7279",
                (
                    ("IUCN — Takin species factsheet (PDF)", "https://nc.iucnredlist.org/redlist/amazing-species/budorcas-taxicolor/pdfs/original/budorcas-taxicolor.pdf"),
                    ("University of Michigan Animal Diversity Web — Takin", "https://animaldiversity.org/accounts/Budorcas_taxicolor/"),
                    ("Myanmar takin conservation study", "https://link.springer.com/article/10.1007/s10344-022-01622-6"),
                ),
            ),
        },
    },
    132: {
        "scientific_name": "Neophocaena phocaenoides",
        "fields": {
            "description_my": (
                "97cd15178528dae71e648adb37f91a3961ef375656951d0675ddde18743f62ab",
                (
                    ("Singapore National Parks — Indo-Pacific Finless Porpoise", "https://www.nparks.gov.sg/florafaunaweb/fauna/2/3/231"),
                    ("Range-wide Neophocaena conservation assessment", "https://www.sciencedirect.com/science/article/pii/S2772735124001069"),
                ),
            ),
            "habitat_my": (
                "a367d7ca6fd35517143a1aa74b2d7584c8b5b08714476a490dbb30fa0cf5a799",
                (
                    ("Singapore National Parks — Indo-Pacific Finless Porpoise", "https://www.nparks.gov.sg/florafaunaweb/fauna/2/3/231"),
                    ("Duke University OBIS-SEAMAP — Finless Porpoise", "https://seamap.env.duke.edu/species/180478/html"),
                ),
            ),
        },
    },
    194: {
        "scientific_name": "Rhinoceros sondaicus",
        "fields": {
            "description_my": (
                "fa10501821426007a65a6be185a51831cd52de7ac9596424e2efb78dbf2bc84a",
                (
                    ("WWF — Javan Rhinoceros", "https://www.worldwildlife.org/species/rhino/javan-rhino/"),
                    ("IUCN Red List — Javan Rhino assessment (PDF)", "https://www.rhinoresourcecenter.com/pdf_files/172/1724167753.pdf"),
                ),
            ),
        },
    },
    209: {
        "scientific_name": "Bungarus fasciatus",
        "fields": {
            "description_my": (
                "e1d88bf669662f5dd02b03bc0fe6b9cb1d3fb8e2edcd560ea26b419885a4c878",
                (
                    ("Singapore National Parks — Banded Krait", "https://www.nparks.gov.sg/florafaunaweb/fauna/2/4/245"),
                    ("Banded Krait venom study", "https://www.sciencedirect.com/science/article/pii/S0041010124000230"),
                    ("WHO — Snakebite management guidance (PDF)", "https://cdn.who.int/media/docs/default-source/searo/india/health-topic-pdf/who-guidance-on-management-of-snakebites.pdf?sfvrsn=552"),
                ),
            ),
            "habitat_my": (
                "2e7f7b4e10b8c97ea997b78c03869c7c9b0734e713a339ac75cbed3b5c3a509b",
                (
                    ("India Biodiversity Portal — Banded Krait habitats", "https://indiabiodiversity.org/species/show/257460"),
                    ("Singapore National Parks — Banded Krait", "https://www.nparks.gov.sg/florafaunaweb/fauna/2/4/245"),
                ),
            ),
        },
    },
    210: {
        "scientific_name": "Daboia siamensis",
        "fields": {
            "description_my": (
                "8571b65bab9bc4980c9a19516b300c95a6a1724368022efee9602efe143a835b",
                (
                    ("Myanmar Department of Medical Research — Snakebite report (PDF)", "https://dmr.gov.mm/publication/AnnualCur/2020-2022.pdf"),
                    ("Eastern Russell's Viper snakebite study in Myanmar", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6732752/"),
                    ("WHO — Snakebite management guidance", "https://www.who.int/publications/i/item/9789290223774"),
                ),
            ),
        },
    },
    211: {
        "scientific_name": "Naja kaouthia",
        "fields": {
            "description_my": (
                "58ab661482d9e9490c35a28aad02c087891a516c931dec249de5443f24a01d08",
                (
                    ("Toronto Zoo — Monocled Cobra", "https://www.torontozoo.com/animals/Monocled%20Cobra"),
                    ("Monocled Cobra envenoming clinical study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5392636/"),
                    ("Monocled Cobra venom cytotoxicity study", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9144634/"),
                ),
            ),
            "habitat_my": (
                "272de5a4158e6a316707c9a6327d9df77e0a5f3d427b2f81cd4d22087a6bee35",
                (("Monocled Cobra habitat and venom study", "https://www.sciencedirect.com/science/article/abs/pii/S004101011500063X"),),
            ),
        },
    },
    169: {
        "scientific_name": "Gallus gallus",
        "fields": {
            "habitat_my": (
                "91910353135a8341ef8139e8a5c001c2a01c5b595b445266d2f800a480372b8a",
                (
                    ("Bangladesh Forest Department — Birds Red List (PDF)", "https://sufal.bforest.gov.bd/redlist/wp-content/uploads/2023/03/Volume-3-Birds-Full-Book.pdf"),
                    ("Cornell Lab of Ornithology — Red Junglefowl", "https://www.allaboutbirds.org/guide/Red_Junglefowl/lifehistory"),
                    ("Journal of Threatened Taxa — Red Junglefowl roosting (PDF)", "https://threatenedtaxa.org/index.php/JoTT/article/download/2256/3755?inline=1"),
                ),
            ),
        },
    },
    183: {
        "scientific_name": "Muntiacus putaoensis",
        "fields": {
            "description_my": (
                "285520f7aef71018d2c9f005738dc676b8d2c894daa29576ffb2dc6877bc3b9b",
                (("Original leaf deer species description", "https://zslpublications.onlinelibrary.wiley.com/doi/10.1111/j.1469-7998.1999.tb01212.x"),),
            ),
            "habitat_my": (
                "97c30239d126ea6fc247df73e89c15bf1291ee99e4d7108972a4de80a7c546c1",
                (
                    ("Original leaf deer species description", "https://zslpublications.onlinelibrary.wiley.com/doi/10.1111/j.1469-7998.1999.tb01212.x"),
                    ("Grzimek's Animal Life Encyclopedia — Muntjacs (PDF)", "https://lib.ysu.am/open_books/311929_15.pdf"),
                ),
            ),
        },
    },
    184: {
        "scientific_name": "Rusa unicolor",
        "fields": {
            "description_my": (
                "d1f8051ff867d9734a18bec174595bac3f601249505242a00f28a7423269f1b8",
                (
                    ("Oxford Mammalian Species — Sambar", "https://academic.oup.com/mspecies/article/43/871/1/2642975"),
                    ("Mammals of Myanmar checklist (PDF)", "https://ir.xtbg.ac.cn/bitstream/353005/14067/1/Mammals%20of%20Myanmar_%20an%20annotated%20checklist.pdf"),
                    ("University of Michigan Animal Diversity Web — Sambar", "https://animaldiversity.org/accounts/Rusa_unicolor/"),
                    ("Sambar alarm call study", "https://journals.rcsi.science/0012-4966/article/view/154062"),
                ),
            ),
        },
    },
    204: {
        "scientific_name": "Hystrix brachyura",
        "fields": {
            "description_my": (
                "cd4412e88f1f5c634520e3733287a81a841e8431fd1dcc50945503bd1995e382",
                (
                    ("Zoo Taiping — Malayan Porcupine", "https://zootaiping.gov.my/en/animal/146/details"),
                    ("Sumatran Mammals field guide (PDF)", "https://www.orangutan.org.au/static/media/uploads/pdf/Sumatran_Mammals_FZS_ebook_2020.pdf"),
                ),
            ),
            "habitat_my": (
                "c9167d29ecc19436ae5b8e4390174090041340842b90962734a5cf81414a46e6",
                (
                    ("Sumatran Mammals field guide (PDF)", "https://www.orangutan.org.au/static/media/uploads/pdf/Sumatran_Mammals_FZS_ebook_2020.pdf"),
                    ("Nepal Red List — Himalayan Crestless Porcupine (PDF)", "https://awsassets.panda.org/downloads/nepal_redlist_low_09_06_2012_1.pdf"),
                    ("Zoo Taiping — Malayan Porcupine", "https://zootaiping.gov.my/en/animal/146/details"),
                ),
            ),
        },
    },
    207: {
        "scientific_name": "Viverricula indica",
        "fields": {
            "description_my": (
                "f961ecf5a786436788a408742532e56e89bec7571fae5344f3a76501b3b1a99f",
                (("University of Michigan Animal Diversity Web — Small Indian Civet", "https://animaldiversity.org/accounts/Viverricula_indica/"),),
            ),
        },
    },
    208: {
        "scientific_name": "Malayopython reticulatus",
        "fields": {
            "description_my": (
                "d1e24b621cee300cadf5b7a8c0bbf436e08aa219062867bdfffff57b73dbfd17",
                (
                    ("Singapore National Parks — Reticulated Python", "https://biodiversitysg.nparks.gov.sg/our-biodiversity/reptiles/snakes/reticulated-python/"),
                    ("Reptile Database — Malayopython reticulatus", "https://reptile-database.reptarium.cz/Malayopython/reticulatus"),
                    ("Ecology Asia — Reticulated Python", "https://www.ecologyasia.ecologyasia.net/verts/snakes/reticulated_python.htm"),
                ),
            ),
            "habitat_my": (
                "a94821aac7de461985c4b83a43b440cafc3e0302b922158aad81628ea89de190",
                (
                    ("Ecology Asia — Reticulated Python", "https://www.ecologyasia.ecologyasia.net/verts/snakes/reticulated_python.htm"),
                    ("Reticulated Python habitat study (PDF)", "https://amphibian-reptile-conservation.org/pdfs/Volume/Vol_14_no_2/ARC_14_2_%5BGeneral_Section%5D_250-263_e249.pdf"),
                ),
            ),
        },
    },
    212: {
        "scientific_name": "Varanus salvator",
        "fields": {
            "description_my": (
                "8847badab84d73c7f9859e7ccffab759c1168403892d86e2dba1ea67744199b1",
                (
                    ("Singapore National Parks — Malayan Water Monitor", "https://biodiversitysg.nparks.gov.sg/our-biodiversity/reptiles/lizards/malayan-water-monitor/"),
                    ("USGS — Common Water Monitor species profile", "https://nas.er.usgs.gov/queries/FactSheet.aspx?SpeciesID=1086"),
                ),
            ),
        },
    },
}


def apply():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    linked = []
    try:
        with conn:
            for animal_id, review in VERIFIED.items():
                row = conn.execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
                if row is None or row["scientific_name"] != review["scientific_name"]:
                    raise ValueError(f"Species identity changed for ID {animal_id}")
                mapping = decode_field_sources(row["field_sources"])
                sources = json.loads(row["source_urls"] or "[]")
                seen = decode_sources(dict(row))
                for field, (expected_hash, evidence) in review["fields"].items():
                    value = row[field] or ""
                    if hashlib.sha256(value.encode("utf-8")).hexdigest() != expected_hash:
                        raise ValueError(f"Reviewed text changed for ID {animal_id}, {field}")
                    if not value or (mapping.get(field) and set(mapping[field]) != {u for _, u in evidence}):
                        # Do not overwrite a subsequent independent editor review.
                        if mapping.get(field):
                            continue
                        raise ValueError(f"Empty reviewed field for ID {animal_id}, {field}")
                    urls = [url for _, url in evidence]
                    for label, url in evidence:
                        if url not in seen:
                            sources.append({"label": label, "url": url})
                            seen.add(url)
                    if not mapping.get(field):
                        mapping[field] = urls
                        linked.append((animal_id, field))
                conn.execute("UPDATE animals SET source_urls = ?, field_sources = ? WHERE id = ?",
                             (json.dumps(sources, ensure_ascii=False),
                              json.dumps(mapping, ensure_ascii=False), animal_id))
    finally:
        conn.close()
    return linked


def write_review_report():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    pending = []
    try:
        for row in conn.execute("SELECT id, name_my, name_en, scientific_name, description_my, habitat_my, field_sources FROM animals ORDER BY id"):
            mapping = decode_field_sources(row["field_sources"])
            for field in ("description_my", "habitat_my"):
                if row[field] and not mapping.get(field):
                    pending.append((row, field))
    finally:
        conn.close()
    lines = [
        "# ဖော်ပြချက်နှင့် နေထိုင်မှု source စစ်ဆေးမှု",
        "",
        "- မူလ source မချိတ်ရသေးသော target field: 124 (ဖော်ပြချက် 64၊ နေထိုင်မှု 60)",
        f"- ဤစစ်ဆေးမှုတွင် source ချိတ်ပြီး: {124 - len(pending)}",
        f"- Source မချိတ်ရသေး၍ ဆက်စစ်ရန်: {len(pending)}",
        "",
        "စာကြောင်းအတိအကျတူရန် မလိုအပ်ပါ။ သို့သော် field တစ်ခုလုံး၏ အဓိပ္ပာယ်နှင့် အရေးကြီးသော အချက်များကို source တစ်ခု သို့မဟုတ် source အစုတစ်ခုက အတည်ပြုနိုင်မှ ချိတ်ထားသည်။ "
        "Species အမည်နှင့် field စာသား hash ကို စစ်ပြီးမှ database တွင် သိမ်းထားသည်။",
        "",
        "## ဆက်စစ်ရန် ကျန်သော field များ",
        "",
        "| ID | တိရစ္ဆာန် / သိပ္ပံအမည် | Field | စစ်ဆေးမှုမှတ်ချက် |",
        "| --- | --- | --- | --- |",
    ]
    for row, field in pending:
        name = f"{row['name_my']} / {row['scientific_name']}".replace("|", " ")
        note = REVIEW_NOTES.get(row["id"], "စာသားတစ်ခုလုံးကို ထောက်ခံသော species-specific source မအတည်ပြုရသေး။")
        lines.append(f"| {row['id']} | {name} | `{field}` | {note} |")
    lines += [
        "",
        "အသေးစိတ် အခြား field များ၏ ကျန်စာရင်းကို `docs/unverified_animal_field_sources.md` တွင် ကြည့်နိုင်သည်။",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return len(pending)


if __name__ == "__main__":
    fields = apply()
    print(f"Linked {len(fields)} semantically verified description/habitat fields: {fields}")
    print(f"Remaining description/habitat fields: {write_review_report()} ({REPORT})")
