"""IUCN Red List categories, in the two scales this site actually carries.

Species records are assessed on the Red List of Threatened Species; ecosystem
records are assessed on the Red List of Ecosystems, whose end point is
*collapse* rather than extinction.  The two scales share their letter codes,
which is exactly why they are kept apart here: rendering an ecosystem's CR
with the species wording would tell a member that a swamp forest is about to
go extinct.

Every label a member reads comes from this one table, so a badge, a tooltip,
a legend row and the passage the chat retrieves can never disagree.
"""

from typing import NamedTuple


class Category(NamedTuple):
    code: str
    name_en: str
    name_mm: str
    description_mm: str


# The threatened categories, on both scales.  CR, EN and VU are what
# "ခြိမ်းခြောက်ခံနေရသော" means; NT sits next to them and is not one of them.
THREATENED = frozenset({"CR", "EN", "VU"})

SPECIES = (
    Category(
        "EX", "Extinct", "မျိုးသုဉ်းပြီး",
        "နောက်ဆုံးအကောင် သေဆုံးသွားပြီဖြစ်ကြောင်း သံသယဖြစ်စရာ မရှိတော့ပါ။",
    ),
    Category(
        "EW", "Extinct in the Wild", "တောရိုင်းတွင် မျိုးသုဉ်းပြီး",
        "တိရစ္ဆာန်ရုံ၊ မွေးမြူရေးစခန်းများတွင်သာ ကျန်ရှိပြီး သဘာဝနေရင်းတွင် မကျန်တော့ပါ။",
    ),
    Category(
        "CR", "Critically Endangered", "မျိုးသုဉ်းရန် အလွန်အန္တရာယ်ရှိ",
        "တောရိုင်းတွင် မျိုးသုဉ်းရန် အန္တရာယ် အလွန်အမင်း မြင့်မားသည်။",
    ),
    Category(
        "EN", "Endangered", "မျိုးသုဉ်းရန် အန္တရာယ်ရှိ",
        "တောရိုင်းတွင် မျိုးသုဉ်းရန် အန္တရာယ် အလွန်မြင့်မားသည်။",
    ),
    Category(
        "VU", "Vulnerable", "မျိုးသုဉ်းရန် ထိခိုက်လွယ်",
        "တောရိုင်းတွင် မျိုးသုဉ်းရန် အန္တရာယ် မြင့်မားသည်။",
    ),
    Category(
        "NT", "Near Threatened", "အန္တရာယ် နီးကပ်လာ",
        "ယခုအခါ အထက်ပါအဆင့်များနှင့် မကိုက်ညီသေးသော်လည်း မကြာမီ ကိုက်ညီလာဖွယ် ရှိသည်။",
    ),
    Category(
        "LC", "Least Concern", "စိုးရိမ်ရမှု အနည်းဆုံး",
        "မျိုးသုဉ်းရန် ခြိမ်းခြောက်ခံရသော အဆင့်များနှင့် အန္တရာယ်နီးကပ်သော အဆင့်တို့၏ စံနှုန်းများနှင့် မကိုက်ညီပါ။",
    ),
    Category(
        "DD", "Data Deficient", "အချက်အလက် မလုံလောက်",
        "အန္တရာယ်အဆင့်ကို ဆုံးဖြတ်ရန် အချက်အလက် လုံလောက်စွာ မရှိသေးပါ။ "
        "စိုးရိမ်ရန် မလိုဟု မဆိုလိုပါ။",
    ),
    Category(
        "NE", "Not Evaluated", "အကဲဖြတ်ခြင်း မပြုရသေး",
        "IUCN စံနှုန်းများဖြင့် တစ်ကြိမ်မျှ အကဲမဖြတ်ရသေးပါ။",
    ),
    Category(
        "NA", "Not Applicable", "သက်ဆိုင်ခြင်း မရှိ",
        "ဒေသအလိုက် အကဲဖြတ်ရာတွင် ဤမျိုးစိတ်ကို ထည့်သွင်းရန် မသင့်လျော်ပါ။",
    ),
)

ECOSYSTEMS = (
    Category(
        "CO", "Collapsed", "ပြိုကွဲပျက်သုဉ်းပြီး",
        "ဂေဟစနစ်၏ လက္ခဏာရပ်များ လုံးဝ ပျောက်ကွယ်သွားပြီ ဖြစ်သည်။",
    ),
    Category(
        "CR", "Critically Endangered", "ပြိုကွဲပျက်သုဉ်းရန် အလွန်အန္တရာယ်ရှိ",
        "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ် အလွန်အမင်း မြင့်မားသည်။",
    ),
    Category(
        "EN", "Endangered", "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ်ရှိ",
        "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ် အလွန်မြင့်မားသည်။",
    ),
    Category(
        "VU", "Vulnerable", "ပြိုကွဲပျက်သုဉ်းရန် ထိခိုက်လွယ်",
        "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ် မြင့်မားသည်။",
    ),
    Category(
        "NT", "Near Threatened", "အန္တရာယ် နီးကပ်လာ",
        "ယခုအခါ အထက်ပါအဆင့်များနှင့် မကိုက်ညီသေးသော်လည်း မကြာမီ ကိုက်ညီလာဖွယ် ရှိသည်။",
    ),
    Category(
        "LC", "Least Concern", "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ်နည်း",
        "ပြိုကွဲပျက်သုဉ်းရန် အန္တရာယ် နည်းပါးပြီး အထက်ပါ အဆင့်များနှင့် မကိုက်ညီပါ။",
    ),
    Category(
        "DD", "Data Deficient", "အချက်အလက် မလုံလောက်",
        "အန္တရာယ်အဆင့်ကို ဆုံးဖြတ်ရန် အချက်အလက် လုံလောက်စွာ မရှိသေးပါ။",
    ),
    Category(
        "NE", "Not Evaluated", "အကဲဖြတ်ခြင်း မပြုရသေး",
        "IUCN စံနှုန်းများဖြင့် တစ်ကြိမ်မျှ အကဲမဖြတ်ရသေးပါ။",
    ),
)

SCALES = {"species": SPECIES, "ecosystem": ECOSYSTEMS}

_BY_CODE = {
    scale: {item.code: item for item in categories}
    for scale, categories in SCALES.items()
}
# Assessments are sometimes written out in full rather than abbreviated.
_BY_NAME = {
    scale: {item.name_en.casefold(): item.code for item in categories}
    for scale, categories in SCALES.items()
}

# The abbreviation for every long form, for normalising crawled assessments.
CODES_BY_NAME = dict(_BY_NAME["species"])
CODES_BY_NAME.update(_BY_NAME["ecosystem"])


def normalize(value, scale="species"):
    """The category code inside an assessment as it is stored, or None.

    Ecosystem assessments carry a plausible range after the outcome —
    ``"CR (CR-CO)"`` is an overall CR whose uncertainty spans CR to CO — so
    the leading token is the category and the rest is the range.
    """
    text = (value or "").strip()
    if not text:
        return None
    head = text.split("(")[0].strip().split()[0] if text.split("(")[0].strip() else ""
    code = head.upper()
    if code in _BY_CODE.get(scale, {}):
        return code
    return _BY_NAME.get(scale, {}).get(text.casefold())


def describe(value, scale="species"):
    """The category an assessment names, or None when it names none."""
    code = normalize(value, scale)
    return _BY_CODE.get(scale, {}).get(code) if code else None


def legend(scale="species"):
    """Every category on one scale, most severe first."""
    return SCALES.get(scale, SPECIES)


def is_threatened(value, scale="species"):
    return normalize(value, scale) in THREATENED


def summary(value, scale="species"):
    """One line naming an assessment in both languages, or the raw value.

    Used wherever a code on its own would be unreadable — a tooltip, and the
    passage the chat retrieves when it is asked about conservation status.
    """
    category = describe(value, scale)
    if not category:
        return (value or "").strip()
    return (
        f"{value} — {category.name_en} ({category.name_mm})။ "
        f"{category.description_mm}"
    )
