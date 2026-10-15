"""အုပ်စုခွဲခြားမှု — controlled vocabularies shared by the dataset and the UI."""

GROUPS = {
    "mammal":    {"mm": "နို့တိုက်သတ္တဝါ",      "en": "Mammals",    "icon": "paw"},
    "bird":      {"mm": "ငှက်",                   "en": "Birds",      "icon": "bird"},
    "reptile":   {"mm": "တွားသွားသတ္တဝါ",      "en": "Reptiles",   "icon": "snake"},
    "amphibian": {"mm": "ကုန်းနေရေနေသတ္တဝါ",  "en": "Amphibians", "icon": "frog"},
    "fish":      {"mm": "ငါးနှင့် ရေနေသတ္တဝါ", "en": "Aquatic",    "icon": "fish"},
    "insect":    {"mm": "အင်းဆက်ပိုးမွှား",     "en": "Insects",    "icon": "bug"},
}

# IUCN Red List categories, with the DESIGN.md badge token each maps to.
IUCN = {
    "EX": {"mm": "မျိုးသုဉ်းပြီး",              "en": "Extinct",               "badge": "critical", "rank": 0},
    "EW": {"mm": "သဘာဝတွင် မျိုးသုဉ်းပြီး",   "en": "Extinct in the Wild",   "badge": "critical", "rank": 1},
    "CR": {"mm": "မျိုးသုဉ်းရန် အလွန်စိုးရိမ်ရ", "en": "Critically Endangered", "badge": "critical", "rank": 2},
    "EN": {"mm": "မျိုးသုဉ်းရန် စိုးရိမ်ရ",      "en": "Endangered",            "badge": "critical", "rank": 3},
    "VU": {"mm": "ထိခိုက်လွယ်",                  "en": "Vulnerable",            "badge": "attention","rank": 4},
    "NT": {"mm": "စိုးရိမ်ရန် နီးစပ်",           "en": "Near Threatened",       "badge": "promo",    "rank": 5},
    "LC": {"mm": "စိုးရိမ်ရန် မလို",            "en": "Least Concern",         "badge": "success",  "rank": 6},
    "DD": {"mm": "အချက်အလက် မလုံလောက်",       "en": "Data Deficient",        "badge": "neutral",  "rank": 7},
}

DIETS = {
    "carnivore":  {"mm": "အသားစား",           "en": "Carnivore"},
    "herbivore":  {"mm": "အပင်စား",            "en": "Herbivore"},
    "omnivore":   {"mm": "အစုံစား",            "en": "Omnivore"},
    "insectivore":{"mm": "အင်းဆက်စား",        "en": "Insectivore"},
    "piscivore":  {"mm": "ငါးစား",              "en": "Piscivore"},
    "frugivore":  {"mm": "သစ်သီးစား",          "en": "Frugivore"},
    "scavenger":  {"mm": "အသေကောင်စား",      "en": "Scavenger"},
}

HABITATS = {
    "evergreen":  {"mm": "အမြဲစိမ်းတောနက်",   "en": "Evergreen forest"},
    "deciduous":  {"mm": "ရွက်ကြွေတော",        "en": "Deciduous forest"},
    "dry":        {"mm": "အညာ ခြောက်သွေ့ဒေသ", "en": "Dry zone"},
    "montane":    {"mm": "တောင်ပေါ်ဒေသ",       "en": "Montane"},
    "grassland":  {"mm": "မြက်ခင်းပြင်",        "en": "Grassland"},
    "wetland":    {"mm": "ရေအိုင်နှင့် ရေလွှမ်းမြေ", "en": "Wetland"},
    "mangrove":   {"mm": "ဒီရေတော",             "en": "Mangrove"},
    "river":      {"mm": "မြစ်နှင့် ချောင်း",   "en": "River"},
    "coastal":    {"mm": "ကမ်းရိုးတန်းနှင့် ပင်လယ်", "en": "Coastal & marine"},
    "urban":      {"mm": "မြို့ပြနှင့် လယ်ယာ",  "en": "Urban & farmland"},
    "bamboo":     {"mm": "ဝါးတော",              "en": "Bamboo forest"},
}
