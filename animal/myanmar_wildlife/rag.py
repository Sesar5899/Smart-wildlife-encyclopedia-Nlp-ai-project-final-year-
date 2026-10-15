"""Retrieval and scope control for the grounded encyclopedia chats.

Every chat on this site answers about exactly one subject — one species, one
ecosystem or one protected area — and only from that subject's published
record.  A small local model will not honour that on instruction alone, so the
two guarantees are enforced here, before the model is ever reached:

``find_subject``
    The question names a *different* subject.  Nothing is generated; the
    member is handed one button to that subject's own chat.

``retrieve``
    The question is about this subject, so the passages that can actually
    answer it are selected.  When the record holds nothing relevant the chat
    says so rather than letting the model improvise.

Both run on Myanmar text, which has no spaces between words.  Everything here
is therefore built on the syllable segmentation in :mod:`myanmar.phonetic`
rather than on whitespace tokens.

Matching a subject deliberately uses *literal* text suffixes rather than
phonetic ones.  Burmese phonetic keys collapse real distinctions: ``သည်``, the
ubiquitous copula, keys identically to ``ဆင်`` ("elephant"), so a phonetic
suffix rule would redirect almost every sentence to the Asian Elephant.  A
literal suffix still resolves ``ဆင်`` inside ``အာရှဆင်`` while colliding with
none of the common function words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import iucn
from myanmar import contains_myanmar, normalize_mm, phonetic_key, syllables


# --------------------------------------------------------------------------
# Tuning
# --------------------------------------------------------------------------

# A Latin name shorter than this matches too much ordinary English to be
# treated as a subject mention.
MIN_LATIN_NAME = 4

# A Myanmar head noun (the ``ဆင်`` of ``အာရှဆင်``) needs this much substance.
MIN_MYANMAR_HEAD = 3

# Passages scoring below this are treated as irrelevant to the question.
RELEVANCE_THRESHOLD = 0.5

# When a question asks about none of the facets the records model, a chance
# word in common is not enough.  "Who is Myanmar's prime minister?" shares
# "Myanmar" with a population passage and is still nothing this record can
# answer, so a purely lexical hit has to be substantial to count.
LEXICAL_ONLY_THRESHOLD = 1.3

# Passages handed to the model for one answer.
MAX_PASSAGES = 8

# Cosine similarity a passage must reach before semantic retrieval will add it
# to a selection.  Deliberately above the out-of-scope band rather than between
# it and the in-scope band: a similarity score never reaches zero, so a bar set
# "in the middle" would quietly answer questions the record cannot answer.  See
# Config.EMBED_THRESHOLD, which the app passes in.
SEMANTIC_THRESHOLD = 0.55


# Burmese particles, pronouns and question words.  These are never a subject
# and never evidence that a passage is relevant.
STOPWORDS = frozenset(
    """
    ဒီ ဤ ထို သည် သော တဲ့ တယ် သည့် က ကို မှာ တွင် နှင့် နဲ့ ရဲ့ ၏ များ တွေ
    ပါ ပြီ ပြီး လဲ လား ဘာ ဘယ် ဘယ်လို ဘယ်လောက် ဘယ်မှာ ဘယ်သူ ဘာကြောင့် အဘယ်
    ရှိ ဖြစ် လုပ် ပြော ပြ ပေး သိ ချင် နိုင် ရ မ မဟုတ် မရှိ လို့ လျှင် ရင်
    အကြောင်း အတွက် အနေ အဖြစ် နောက် ထပ် ဖြင့် ထဲ မှ သို့ ဆီ ခု ခြင်း မှု
    ငါ ကျွန်တော် ကျွန်မ သင် သူ သူတို့ ငါတို့ ဟာ တစ် နှစ် သုံး လေး ငါး
    နေ သွား လာ ကျ ထား ခဲ့ တတ် ကြ ဘူး သေး တော့ ပဲ ပဲ့ လေ နော် ကား
    ဆို ဆိုတာ တာ ရမ ရမလဲ မလဲ သလဲ လေး
    """.split()
)

# Heads are extracted from normalized text, so the stopwords have to be
# normalized too — "ဘာကြောင့်" written literally does not compare equal to its
# own normalized form, and would survive stripping as the head noun "ကြောင့်".
STOPWORDS = frozenset(normalize_mm(word).casefold() for word in STOPWORDS)

# The longest stopword, in syllables, so both edges can strip it whole.
_STOPWORD_SYLLABLES = max(len(syllables(word)) for word in STOPWORDS)

LATIN_STOPWORDS = frozenset(
    """
    a an the is are was were be been being do does did what which who whom
    whose when where why how this that these those it its they them their
    and or but if then than of to in on at by for with from about into over
    can could will would shall should may might must have has had i you we
    me my your our tell show give explain please list many much more most
    """.split()
)


# --------------------------------------------------------------------------
# Tokenising
# --------------------------------------------------------------------------

_LATIN_WORD = re.compile(r"[a-z][a-z'-]*")


def _latin_words(text: str) -> list[str]:
    return _LATIN_WORD.findall(text.casefold())


@dataclass(frozen=True)
class Units:
    """The meaning-bearing units of a string, split by how much they prove.

    ``strong`` holds adjacent Myanmar syllable pairs and whole Latin words —
    in a script without word separators, a syllable pair is the closest thing
    to a word, and sharing one is real evidence of a shared topic.  ``weak``
    holds single Myanmar syllables, which recur across unrelated words and so
    can support a match but never establish one on their own.
    """

    strong: frozenset
    weak: frozenset


def _content_units(text: str) -> Units:
    normalized = normalize_mm(text)
    marks = [s for s in syllables(normalized) if s not in STOPWORDS]
    # Pairs are filtered against the stopword list as well: a multi-syllable
    # particle such as ``အကြောင်း`` survives per-syllable filtering and would
    # otherwise reappear as a "strong" unit once its syllables are rejoined.
    strong = {
        pair for index in range(len(marks) - 1)
        if (pair := marks[index] + marks[index + 1]) not in STOPWORDS
    }
    strong.update(
        word for word in _latin_words(normalized)
        if len(word) > 2 and word not in LATIN_STOPWORDS
    )
    return Units(frozenset(strong), frozenset(marks))


# --------------------------------------------------------------------------
# Subjects — everything this site has a chat for
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Subject:
    """One chattable record, with every name it may be called by."""

    key: str
    kind: str          # 'animal' | 'ecosystem' | 'protected-area'
    ident: object      # animal id, or collection slug
    name: str          # Myanmar display name
    name_en: str
    names: tuple[str, ...] = field(default=(), compare=False)

    @property
    def label(self) -> str:
        return {
            "animal": "မျိုးစိတ်",
            "ecosystem": "ဂေဟစနစ်",
            "protected-area": "ကာကွယ်ထိန်းသိမ်းနယ်မြေ",
        }[self.kind]


def animal_subject(animal: dict) -> Subject:
    names = [
        animal.get("name_my"),
        animal.get("name_en"),
        animal.get("scientific_name"),
        *(animal.get("aliases") or []),
    ]
    return Subject(
        key=f"animal:{animal['id']}",
        kind="animal",
        ident=animal["id"],
        name=animal.get("name_my") or animal.get("name_en") or "",
        name_en=animal.get("name_en") or "",
        names=tuple(name for name in names if name),
    )


def collection_subject(kind: str, record: dict) -> Subject:
    names = [record.get("name_mm"), record.get("name")]
    return Subject(
        key=f"{kind}:{record.get('slug')}",
        kind=kind,
        ident=record.get("slug"),
        name=record.get("name_mm") or record.get("name") or "",
        name_en=record.get("name") or "",
        names=tuple(name for name in names if name),
    )


def build_subjects(animals, ecosystems, protected_areas) -> list[Subject]:
    """Index every chattable record across the three catalogs."""
    subjects = [animal_subject(animal) for animal in animals]
    subjects.extend(collection_subject("ecosystem", item) for item in ecosystems)
    subjects.extend(
        collection_subject("protected-area", item) for item in protected_areas
    )
    return subjects


# --------------------------------------------------------------------------
# Which subject is this question really about?
# --------------------------------------------------------------------------

def _latin_mentioned(name: str, message: str) -> bool:
    """A Latin name counts only as a whole word, so 'cat' misses 'category'."""
    if len(name) < MIN_LATIN_NAME:
        return False
    return re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", message) is not None


# A Myanmar run bounded by anything that is not Myanmar script: Burmese
# separates phrases with spaces even though it does not separate words.
_PHRASE_SPLIT = re.compile(r"[^က-႟]+")


def _phrase_heads(message: str) -> set[str]:
    """Whole Myanmar phrases, stripped of grammatical particles.

    Only a delimited phrase may nominate a subject by its head noun.  Free
    syllable n-grams cannot: ``ခြိမ်းခြောက်မှု`` ("threats") ends in the same
    syllable as a bird whose name is ``မျက်ခုံးဖြူငှက်ပြာခြောက်``, and a
    perfectly ordinary question about threats must not be redirected to it.
    """
    heads = set()
    for phrase in _PHRASE_SPLIT.split(message):
        marks = syllables(phrase)
        start, end = 0, len(marks)
        # Strip the longest stopword at each edge, not one syllable at a time.
        # ``ဘယ်လို`` ("how") is a stopword but ``ဘယ်`` alone is too, and taking
        # the short match first leaves ``လို`` behind as a head noun — which is
        # how "ဘယ်လိုလဲ" came to name a pelican whose spelling ends in it.
        while start < end:
            for size in range(min(_STOPWORD_SYLLABLES, end - start), 0, -1):
                if "".join(marks[start : start + size]) in STOPWORDS:
                    start += size
                    break
            else:
                break
        while end > start:
            for size in range(min(_STOPWORD_SYLLABLES, end - start), 0, -1):
                if "".join(marks[end - size : end]) in STOPWORDS:
                    end -= size
                    break
            else:
                break
        span = "".join(marks[start:end])
        if len(span) >= MIN_MYANMAR_HEAD and span not in STOPWORDS:
            heads.add(span)
    return heads


def _latin_heads(message: str) -> set[str]:
    """Ordinary words from the message that could be the head of a name."""
    return {
        word for word in _latin_words(message)
        if len(word) >= MIN_LATIN_NAME and word not in LATIN_STOPWORDS
    }


def find_subject(message: str, subjects, *, exclude_key: str | None = None):
    """The subject a question is really about, or None to answer it here.

    Scored in tiers so that a whole name always beats a head noun, and a head
    noun beats a merely similar spelling:

    3. the message literally contains a complete name
    2. the message contains a phrase that is the head of exactly one
       subject's name (``ဆင်`` -> ``အာရှဆင်``, ``elephant`` -> Asian Elephant)
    1. a phrase is phonetically the same word as a whole name, which is what
       forgives Burmese spelling variation

    Returning None means the current chat should answer.  That includes the
    case where the question names the subject already being viewed, even if it
    also mentions another one — comparing two species from one species' page
    is still a question that page can answer.
    """
    if not message or not subjects:
        return None

    normalized = normalize_mm(message).casefold()
    if not normalized:
        return None

    heads = _phrase_heads(normalized)
    latin_heads = _latin_heads(normalized)
    best: dict[str, tuple[int, int]] = {}
    by_key = {subject.key: subject for subject in subjects}

    # A head noun is only trustworthy when it points at a single subject.
    # ``လိပ်`` ("turtle") ends a dozen species names and identifies none of
    # them, so it must not pick one arbitrarily.
    head_owners: dict[str, set[str]] = {}

    for subject in subjects:
        for name in subject.names:
            canonical = normalize_mm(name).casefold()
            if not canonical:
                continue

            if contains_myanmar(canonical):
                if canonical in normalized:
                    score = (3, len(canonical))
                    if score > best.get(subject.key, (0, 0)):
                        best[subject.key] = score
                    continue
                if len(syllables(canonical)) < 2:
                    continue
                for head in heads:
                    if canonical.endswith(head) and head != canonical:
                        head_owners.setdefault(head, set()).add(subject.key)
                name_key = phonetic_key(canonical)
                if name_key:
                    for head in heads:
                        if phonetic_key(head) == name_key:
                            score = (1, len(head))
                            if score > best.get(subject.key, (0, 0)):
                                best[subject.key] = score
            elif _latin_mentioned(canonical, normalized):
                score = (3, len(canonical))
                if score > best.get(subject.key, (0, 0)):
                    best[subject.key] = score
            else:
                words = _latin_words(canonical)
                if len(words) >= 2 and words[-1] in latin_heads:
                    head_owners.setdefault(words[-1], set()).add(subject.key)

    for head, owners in head_owners.items():
        if len(owners) != 1:
            continue
        key = next(iter(owners))
        score = (2, len(head))
        if score > best.get(key, (0, 0)):
            best[key] = score

    if not best:
        return None

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    top_key, _ = ranked[0]
    if exclude_key and top_key == exclude_key:
        return None
    return by_key[top_key]


# --------------------------------------------------------------------------
# Passages — the retrievable content of one record
# --------------------------------------------------------------------------

@dataclass
class Passage:
    """One labelled, retrievable piece of a published record."""

    label: str
    text: str
    intents: tuple[str, ...] = ()
    identity: bool = False
    field: str = ""

    def __post_init__(self):
        # Scored on the record's own words only.  The labels are our curated
        # Burmese headings, and counting them would let a question match a
        # passage merely by reusing the vocabulary we chose for its heading.
        self._units = _content_units(self.text)

    @property
    def units(self) -> Units:
        return self._units


# Question vocabulary -> the kind of passage that can answer it.  Burmese and
# English are listed together because members mix both in one sentence.
INTENT_TERMS = {
    "identity": ["အမည်", "နာမည်", "ခေါ်", "name", "called", "ဘာလဲ", "what is"],
    "taxonomy": [
        "မျိုးရင်း", "မျိုးစု", "အမျိုးအစား", "သိပ္ပံ", "order", "family",
        "class", "scientific", "taxonomy", "species",
    ],
    "habitat": [
        "နေထိုင်", "နေရာ", "ကျက်စား", "ဇီဝ", "တော", "habitat", "live", "lives",
        "living", "ecology", "ဂေဟ", "ဘယ်မှာ", "ဘယ်နေရာ", "နေသလဲ", "နေလဲ",
    ],
    "diet": ["စား", "အစာ", "အာဟာရ", "diet", "eat", "eats", "food", "feed", "prey"],
    "threats": [
        "ခြိမ်းခြောက်", "အန္တရာယ်", "အမဲလိုက်", "ဖမ်းဆီး", "သတ်", "ဆုံးရှုံး",
        "threat", "threats", "danger", "hunting", "poaching", "risk",
    ],
    "population": [
        "အကောင်ရေ", "ဦးရေ", "ကျန်", "လမ်းကြောင်း", "population", "many",
        "number", "trend", "count",
    ],
    "conservation": [
        "ထိန်းသိမ်း", "ကာကွယ်", "ပြုစု", "လုပ်ဆောင်", "conservation",
        "protect", "protection", "research", "manage",
    ],
    "status": [
        "အဆင့်", "မျိုးသုဉ်း", "စိုးရိမ်", "ထိခိုက်", "iucn", "status",
        "endangered", "threatened", "vulnerable", "red list",
    ],
    "size": [
        "အရွယ်", "အလျား", "အလေးချိန်", "အမြင့်", "size", "length", "weight",
        "height", "big", "large", "measurement",
    ],
    "appearance": [
        "ရုပ်သွင်", "အသွင်အပြင်", "အရောင်", "အမွေးအရောင်",
        "appearance", "colour", "color", "coat", "fur pattern",
    ],
    # Do not use bare "အမ" here: it is also the beginning of ordinary words
    # such as "အမည်".  Phrase-level terms recognise questions comparing the
    # sexes without turning unrelated questions into animal lookups.
    "sex_difference": [
        "အမနဲ့အထီး", "အမနှင့်အထီး", "အမနဲ့ အထီး", "အမနှင့် အထီး",
        "အထီးနဲ့အမ", "အထီးနှင့်အမ", "အထီးနဲ့ အမ", "အထီးနှင့် အမ",
        "အမတွေကအထီးတွေ", "အမတွေက အထီးတွေ", "လိင်ကွဲပြား",
        "ကျားမကွဲပြား", "male and female", "female and male",
        "sexual dimorphism", "sex difference", "differences between sexes",
    ],
    "distribution": [
        "ဖြန့်ကျက်", "ဒေသ", "တိုင်း", "ပြည်နယ်", "တွေ့", "မြေပုံ",
        "distribution", "region", "range", "found", "occur", "where",
        "ဘယ်မှာ", "ဘယ်ဒေသ", "တွေ့နိုင်",
    ],
    "use_trade": [
        "ကုန်သွယ်", "ရောင်းဝယ်", "အသုံးပြု", "trade", "use", "commercial",
    ],
    "legal": [
        "ဥပဒေ", "ကာကွယ်ထား", "တားမြစ်", "ပြစ်ဒဏ်", "တရားမဝင်", "ခွင့်ပြု",
        "ဖမ်းဆီး", "အမဲလိုက်", "မွေးမြူခွင့်", "စာရင်းသွင်း",
        "law", "legal", "illegal", "protected", "protection", "penalty",
        "permit", "poach", "hunting", "banned", "prohibited",
    ],
    "behaviour": [
        "အပြုအမူ", "အနေအထိုင်", "ကျင့်ကြံ", "မျိုးပွား", "သားပေါက်", "အသံ",
        "အုပ်စု", "behaviour", "behavior", "reproduction", "breeding",
        "social", "call", "communicat", "active", "nocturnal",
    ],
    "tourism": ["ခရီးသွား", "လည်ပတ်", "tourism", "visit", "tourist"],
    "area": ["ဧရိယာ", "ကျယ်", "ဟက်တာ", "ဧက", "area", "hectare", "size of"],
    "management": [
        "စီမံ", "အုပ်ချုပ်", "တာဝန်", "management", "authority", "governance",
        "established", "တည်ထောင်",
    ],
}


def question_intents(question: str) -> set[str]:
    normalized = normalize_mm(question).casefold()
    return {
        intent for intent, terms in INTENT_TERMS.items()
        if any(term in normalized for term in terms)
    }


def _passage(label, value, intents=(), identity=False, field=""):
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (list, tuple)):
        value = "၊ ".join(str(item) for item in value if item)
    text = str(value).strip()
    return Passage(label, text, tuple(intents), identity, field) if text else None


ANIMAL_PASSAGE_FIELDS = {
    "မြန်မာအမည်": "name_my", "အင်္ဂလိပ်အမည်": "name_en",
    "သိပ္ပံအမည်": "scientific_name", "Order": "species_order",
    "Family": "species_family", "ဖော်ပြချက်": "description_my",
    "ရုပ်သွင်ဖော်ပြချက်": "physical_description_my",
    "နေထိုင်ရာနှင့် ဂေဟဗေဒ": "habitat_my", "အစာစားနည်း": "diet_my",
    "အရွယ်အစား": "size_my", "သက်တမ်း": "lifespan_my",
    "တွေ့ရှိရသော ဒေသများ": "region_my",
    "ဥပဒေအရ ကာကွယ်ထားမှု": "protection_status_my",
    "ကာကွယ်ရသည့် အကြောင်းရင်း": "protection_basis_my",
    "ကာကွယ်စောင့်ရှောက်သည့် ဥပဒေ": "protection_law_my",
    "မြန်မာ IUCN အဆင့်": "conservation_status",
    "ကမ္ဘာလုံးဆိုင်ရာ IUCN အဆင့်": "global_iucn_status",
    "တွေ့ရှိမှု အခြေအနေ": "population_trend",
    "မြန်မာနိုင်ငံ အကောင်ရေ": "myanmar_population",
    "ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ": "global_population",
    "ထူးခြားအချက်များ": "fun_facts_my",
    "တောရိုင်း အကောင်ရေ": "wild_population_my",
    "IUCN အကဲဖြတ် အကြောင်းပြချက်": "iucn_justification_my",
    "ဖြန့်ကျက်တည်ရှိမှု": "distribution_my",
    "ခြိမ်းခြောက်မှုများ": "threats_my",
    "ထိန်းသိမ်းရေး လုပ်ဆောင်ချက်များ": "conservation_actions_my",
    "ထိန်းသိမ်းရေး လိုအပ်ချက်များ": "conservation_needs_my",
    "အသုံးပြုမှုနှင့် ကုန်သွယ်မှု": "use_trade_my",
    "ကာကွယ်ထားသော နယ်မြေများတွင်": "protected_areas_my",
    "ဆက်စပ် ဂေဟစနစ်များ": "ecosystems_my",
    "အဓိက ဇီဝမျိုးစုံမျိုးကွဲ နယ်မြေများ": "kba_my",
    "အနေအထိုင်နှင့် အပြုအမူ": "behaviour_my",
}


def animal_passages(animal: dict) -> list[Passage]:
    """Split one species record into retrievable, labelled passages."""
    candidates = [
        ("မြန်မာအမည်", animal.get("name_my"), ("identity",), True),
        ("အင်္ဂလိပ်အမည်", animal.get("name_en"), ("identity",), True),
        ("သိပ္ပံအမည်", animal.get("scientific_name"), ("identity", "taxonomy"), True),
        ("အခြားအမည်များ", animal.get("aliases"), ("identity",), True),
        ("အမျိုးအစား", animal.get("category_name_my"), ("identity", "taxonomy"), True),
        ("Order", animal.get("species_order"), ("taxonomy",), False),
        ("Family", animal.get("species_family"), ("taxonomy",), False),
        ("ဖော်ပြချက်", animal.get("description_my"), ("identity", "threats"), False),
        (
            "ရုပ်သွင်ဖော်ပြချက်",
            animal.get("physical_description_my"),
            ("size", "identity", "appearance", "sex_difference"),
            False,
        ),
        ("နေထိုင်ရာနှင့် ဂေဟဗေဒ", animal.get("habitat_my"), ("habitat", "diet"), False),
        ("အစာစားနည်း", animal.get("diet_my"), ("diet",), False),
        ("အရွယ်အစား", animal.get("size_my"), ("size",), False),
        ("သက်တမ်း", animal.get("lifespan_my"), ("size",), False),
        ("တွေ့ရှိရသော ဒေသများ", animal.get("region_my"), ("distribution",), False),
        (
            "ဥပဒေအရ ကာကွယ်ထားမှု",
            animal.get("protection_status_my"),
            ("legal", "conservation", "status", "use_trade"),
            True,
        ),
        (
            "ကာကွယ်ရသည့် အကြောင်းရင်း",
            animal.get("protection_basis_my"),
            ("legal", "conservation", "taxonomy"),
            False,
        ),
        (
            "ကာကွယ်စောင့်ရှောက်သည့် ဥပဒေ",
            animal.get("protection_law_my"),
            ("legal", "conservation"),
            False,
        ),
        (
            "မှတ်တမ်းအဆင့်",
            animal.get("taxon_rank_label_my"),
            ("identity", "taxonomy"),
            False,
        ),
        # Expanded, because "EN" on its own tells the model nothing: a chat
        # asked what the status means has to answer from the record, and this
        # is the record.
        (
            "မြန်မာ IUCN အဆင့်",
            iucn.summary(animal.get("conservation_status")),
            ("status",),
            False,
        ),
        (
            "ကမ္ဘာလုံးဆိုင်ရာ IUCN အဆင့်",
            iucn.summary(animal.get("global_iucn_status")),
            ("status",),
            False,
        ),
        ("တွေ့ရှိမှု အခြေအနေ", animal.get("population_trend"), ("population",), False),
        ("မြန်မာနိုင်ငံ အကောင်ရေ", animal.get("myanmar_population"), ("population",), False),
        ("ကမ္ဘာလုံးဆိုင်ရာ အကောင်ရေ", animal.get("global_population"), ("population",), False),
        ("ထူးခြားအချက်များ", animal.get("fun_facts_my"), ("identity",), False),
        ("တောရိုင်း အကောင်ရေ", animal.get("wild_population_my"), ("population",), False),
        ("IUCN အကဲဖြတ် အကြောင်းပြချက်", animal.get("iucn_justification_my"), ("status", "threats"), False),
        (
            "ဖြန့်ကျက်တည်ရှိမှု",
            animal.get("distribution_my"),
            ("distribution", "habitat"),
            False,
        ),
        (
            "ခြိမ်းခြောက်မှုများ",
            animal.get("threats_my"),
            ("threats",),
            False,
        ),
        (
            "ထိန်းသိမ်းရေး လုပ်ဆောင်ချက်များ",
            animal.get("conservation_actions_my"),
            ("conservation",),
            False,
        ),
        (
            "ထိန်းသိမ်းရေး လိုအပ်ချက်များ",
            animal.get("conservation_needs_my"),
            ("conservation",),
            False,
        ),
        (
            "အသုံးပြုမှုနှင့် ကုန်သွယ်မှု",
            animal.get("use_trade_my"),
            ("use_trade",),
            False,
        ),
        (
            "ကာကွယ်ထားသော နယ်မြေများတွင်",
            animal.get("protected_areas_my"),
            ("conservation", "distribution"),
            False,
        ),
        (
            "ဆက်စပ် ဂေဟစနစ်များ",
            animal.get("ecosystems_my"),
            ("habitat", "distribution"),
            False,
        ),
        (
            "အဓိက ဇီဝမျိုးစုံမျိုးကွဲ နယ်မြေများ",
            animal.get("kba_my"),
            ("conservation", "distribution"),
            False,
        ),
        (
            "အနေအထိုင်နှင့် အပြုအမူ",
            animal.get("behaviour_my"),
            ("behaviour", "habitat"),
            False,
        ),
    ]
    return [
        passage for passage in (
            _passage(label, value, intents, identity, ANIMAL_PASSAGE_FIELDS.get(label, ""))
            for label, value, intents, identity in candidates
        ) if passage
    ]


COLLECTION_PASSAGES = {
    "ecosystem": [
        ("မြန်မာအမည်", ("name_mm",), ("identity",), True),
        ("အင်္ဂလိပ်အမည်", ("name",), ("identity",), True),
        ("စနစ်ကုဒ်", ("code",), ("identity", "taxonomy"), True),
        ("ဖော်ပြချက်", ("description_mm",), ("identity", "habitat"), False),
        ("ဖြန့်ကျက်တည်ရှိမှု", ("distribution_mm",), ("distribution",), False),
        ("ဇီဝဒေသ", ("in_biome_mm",), ("taxonomy", "habitat"), False),
        ("နယ်ပယ်", ("in_realm_mm",), ("taxonomy", "habitat"), False),
        ("တိုင်း/ပြည်နယ်", ("in_state_region_mm",), ("distribution",), False),
        (
            "လုပ်ဆောင်ချက်အုပ်စု",
            ("in_functional_group_mm",),
            ("taxonomy",),
            False,
        ),
        ("IUCN အဆင့်", ("national_iucn_status",), ("status",), False),
        ("ဂေဟစနစ် အကဲဖြတ်ချက်", ("assessment_summary_mm",), ("status", "conservation"), False),
        ("ဂေဟစနစ် ပျက်စီးဆုံးရှုံးမှု သတ်မှတ်ချက်", ("collapse_definition_mm",), ("status", "threats"), False),
        ("ပျက်စီးစေသည့် အချက်များ", ("threats_mm",), ("threats",), False),
        ("ဇီဝမဲ့ပတ်ဝန်းကျင်", ("abiotic_environment_mm",), ("habitat",), False),
        ("မူရင်း ဇီဝအစုအဖွဲ့", ("native_biota_mm",), ("habitat",), False),
        (
            "အဓိက လုပ်ငန်းစဉ်များနှင့် ဆက်နွယ်မှု",
            ("key_processes_and_interactions_mm",),
            ("habitat",),
            False,
        ),
        ("ပျမ်းမျှအပူချိန်", ("temperature_text_mm",), ("habitat",), False),
        ("မိုးရေချိန်", ("precipitation_text_mm",), ("habitat",), False),
        ("မြေဆီလွှာ", ("soil_text_mm",), ("habitat",), False),
        ("အမြင့်", ("elevation_text_mm",), ("habitat", "size"), False),
        (
            "တွေ့ရှိရသော သတ္တဝါများ",
            ("species_fauna_mm",),
            ("habitat",),
            False,
        ),
        (
            "တွေ့ရှိရသော အပင်များ",
            ("species_flora_mm",),
            ("habitat",),
            False,
        ),
        ("အကဲဖြတ်သည့်နေ့", ("date_assessed",), ("management",), False),
        ("ထုတ်ဝေသည့်နှစ်", ("year_published",), ("management",), False),
    ],
    "protected-area": [
        ("မြန်မာအမည်", ("name_mm",), ("identity",), True),
        ("အင်္ဂလိပ်အမည်", ("name",), ("identity",), True),
        ("သတ်မှတ်အမျိုးအစား", ("designation_mm", "designation"), ("identity", "taxonomy"), True),
        ("အခြေအနေ", ("status_mm", "status"), ("status",), False),
        ("ဖော်ပြချက်", ("description_mm", "description"), ("identity", "habitat"), False),
        ("တိုင်း/ပြည်နယ်", ("in_state_region_mm", "in_state_region"), ("distribution",), False),
        ("နယ်နိမိတ်", ("boundary_mm", "boundary"), ("distribution", "area"), False),
        ("တည်ထောင်သည့်နှစ်", ("established_year",), ("management",), False),
        ("သတ်မှတ်ကြေညာသည့်နေ့", ("designaton_date",), ("management",), False),
        ("အကဲဖြတ်သည့်နှစ်", ("eval_year",), ("management",), False),
        ("ဧရိယာ (ဟက်တာ)", ("area_ha",), ("area", "size"), False),
        ("ဧရိယာ (ဧက)", ("area_acre",), ("area", "size"), False),
        ("ဇီဝနယ်မြေ", ("bio_unit_mm", "bio_unit_n"), ("taxonomy", "habitat"), False),
        ("ဇီဝနယ်မြေ ကုဒ်/အမျိုးအစား", ("bio_unit",), ("taxonomy", "habitat"), False),
        ("အဓိက ရည်ရွယ်ချက်များ", ("main_purposes_mm", "main_purposes"), ("conservation", "management"), False),
        ("ကာကွယ်မှုအဆင့်", ("protection_level_mm", "protection_level"), ("conservation", "status"), False),
        ("စီမံခန့်ခွဲသူ", ("management_authority_mm", "management_authority"), ("management",), False),
        ("အုပ်ချုပ်မှုပုံစံ", ("governance_type_mm", "governance_type"), ("management",), False),
        ("နေထိုင်ရာပတ်ဝန်းကျင်", ("habitat_types_mm", "habitat_types"), ("habitat",), False),
        (
            "သဘာဝရင်းမြစ်နှင့် ဇီဝမျိုးစုံမျိုးကွဲ",
            ("natural_resources_mm", "natural_resources_biodiversity"),
            ("habitat", "conservation"),
            False,
        ),
        ("တွေ့ရှိရသော သတ္တဝါများ", ("species_fauna_mm", "species_fauna"), ("habitat",), False),
        ("အခြား သတ္တဝါများ", ("other_fauna_mm", "other_fauna"), ("habitat",), False),
        ("တွေ့ရှိရသော အပင်များ", ("species_flora_mm", "species_flora"), ("habitat",), False),
        ("အခြား အပင်များ", ("other_flora_mm", "other_flora"), ("habitat",), False),
        ("အခြား မျိုးစိတ်များ", ("other_species_mm", "other_species"), ("habitat",), False),
        ("ခရီးသွားနှင့် လေ့လာရေး", ("tourism_mm", "tourism"), ("tourism",), False),
        (
            "နယ်မြေအတွင်း ခြိမ်းခြောက်မှု",
            ("threats_subcategory_inside_mm", "threats_subcategory_inside"),
            ("threats",),
            False,
        ),
        (
            "နယ်မြေအပြင် ခြိမ်းခြောက်မှု",
            ("threats_subcategory_outside_mm", "threats_subcategory_outside"),
            ("threats",),
            False,
        ),
    ],
}


def collection_passages(kind: str, record: dict) -> list[Passage]:
    passages = []
    for label, fields, intents, identity in COLLECTION_PASSAGES.get(kind, []):
        value = next((record.get(name) for name in fields if record.get(name)), None)
        passage = _passage(label, value, intents, identity)
        if passage:
            passages.append(passage)
    return passages


def record_passages(kind: str, record: dict) -> list[Passage]:
    return animal_passages(record) if kind == "animal" else collection_passages(kind, record)


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

def _overlap_score(question: Units, passage: Passage) -> float:
    """How much of the question this passage actually speaks to.

    A shared syllable pair or Latin word carries the match; lone syllables
    only sharpen a match that already exists.  Requiring at least one strong
    agreement is what stops an unrelated question from finding a foothold in
    a long passage that happens to reuse one common syllable.
    """
    shared_strong = question.strong & passage.units.strong
    if not shared_strong:
        return 0.0
    shared_weak = question.weak & passage.units.weak
    weight = len(shared_strong) + 0.25 * len(shared_weak)
    return weight / max(1.0, len(question.strong) ** 0.5)


def _cosine(left, right) -> float:
    """Both sides are stored unit-length, so cosine is the dot product."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def semantic_scores(question_vector, passages, passage_vectors):
    """``[(similarity, passage), ...]`` for every passage that has a vector."""
    if not question_vector or not passage_vectors:
        return []
    return [
        (_cosine(question_vector, vector), passage)
        for passage, vector in zip(passages, passage_vectors)
        if vector
    ]


def retrieve(question: str, passages: list[Passage], *, question_vector=None,
             passage_vectors=None, semantic_threshold=SEMANTIC_THRESHOLD):
    """Select the passages that can answer this question.

    Returns ``(selected, reason)``.  An empty selection means the record holds
    nothing that speaks to the question, and the caller must answer with the
    out-of-scope notice rather than calling the model.

    Lexical matching decides the outcome.  When vectors are supplied, semantic
    matches may *fill remaining slots* above ``semantic_threshold``, but they
    never displace a lexical hit and never rescue a question that lexical
    matching refused unless they clear that bar on their own.  Called without
    vectors — as every existing caller and test does — this behaves exactly as
    it did before semantic retrieval existed.
    """
    if not passages:
        return [], "empty"

    question_units = _content_units(question)
    intents = question_intents(question)

    threshold = RELEVANCE_THRESHOLD if intents else LEXICAL_ONLY_THRESHOLD

    scored = []
    for passage in passages:
        score = _overlap_score(question_units, passage)
        if intents & set(passage.intents):
            score += 1.0
        if score >= threshold:
            scored.append((score, passage))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [passage for _, passage in scored[:MAX_PASSAGES]]

    # Semantic retrieval is additive: it can only occupy slots lexical
    # matching left empty, so a weak embedding model cannot make an answer
    # worse than it already was — only longer.
    taken = {id(passage) for passage in selected}
    semantic = sorted(
        (
            (score, passage)
            for score, passage in semantic_scores(
                question_vector, passages, passage_vectors
            )
            # Identity passages are appended below whatever happens, and they
            # are short strings that sit near the top of a cosine ranking for
            # any question at all.  Letting them win semantic slots would
            # spend the budget on passages the answer already has.
            if score >= semantic_threshold and not passage.identity
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    for _, passage in semantic:
        if len(selected) >= MAX_PASSAGES:
            break
        if id(passage) not in taken:
            taken.add(id(passage))
            selected.append(passage)

    if selected:
        # Identity is cheap and stops the model from mislabelling its subject.
        for passage in passages:
            if passage.identity and id(passage) not in taken:
                taken.add(id(passage))
                selected.append(passage)
        return selected[:MAX_PASSAGES + 3], "matched" if scored else "semantic"

    # No lexical or intent evidence.  A question that only refers to the
    # subject generally ("tell me about this animal") is still answerable, and
    # is served a summary rather than a refusal.
    if _is_general_question(question):
        summary = [passage for passage in passages if passage.identity]
        summary.extend(
            passage for passage in passages
            if not passage.identity and len(passage.text) > 40
        )
        return summary[:MAX_PASSAGES], "general"

    return [], "out-of-scope"


_GENERAL_TERMS = (
    "အကြောင်း", "ဖော်ပြ", "ရှင်းပြ", "အကျဉ်း", "မိတ်ဆက်", "ဘာလဲ", "ဘာတွေလဲ",
    "မှတ်တမ်း", "အချက်အလက်", "about", "describe", "summary", "summarise",
    "summarize", "overview", "introduce", "information", "tell me",
)


def _is_general_question(question: str) -> bool:
    normalized = normalize_mm(question).casefold()
    return any(term in normalized for term in _GENERAL_TERMS)


def passages_as_context(passages: list[Passage]) -> str:
    return "\n".join(f"- {passage.label}: {passage.text}" for passage in passages)


# --------------------------------------------------------------------------
# Tracing — the same run, recorded step by step for the admin console
# --------------------------------------------------------------------------

def trace(question: str, kind: str, record: dict, subjects=(), current_key=None, *,
          question_vector=None, passage_vectors=None,
          semantic_threshold=SEMANTIC_THRESHOLD):
    """Run one question through the real retrieval path and record each step.

    Every value returned here is produced by the functions the chat endpoints
    themselves call — ``find_subject``, ``question_intents``, ``retrieve`` and
    ``_overlap_score``.  Nothing is re-derived for display, so the console
    cannot drift into describing a pipeline the site no longer runs.
    """
    normalized = normalize_mm(question)
    marks = syllables(normalized)
    kept = [mark for mark in marks if mark not in STOPWORDS]
    units = _content_units(question)

    # ``strong`` mixes rejoined Myanmar syllable pairs with whole Latin words;
    # they are worth showing apart because they are found two different ways.
    pairs = sorted(unit for unit in units.strong if contains_myanmar(unit))
    latin = sorted(unit for unit in units.strong if not contains_myanmar(unit))

    subject = find_subject(question, subjects, exclude_key=current_key)
    intents = question_intents(question)
    passages = record_passages(kind, record)
    threshold = RELEVANCE_THRESHOLD if intents else LEXICAL_ONLY_THRESHOLD

    if passage_vectors is None:
        passage_vectors = [None] * len(passages)
    selected, reason = retrieve(
        question,
        passages,
        question_vector=question_vector,
        passage_vectors=passage_vectors,
        semantic_threshold=semantic_threshold,
    )
    chosen = {id(passage) for passage in selected}
    similarity = {
        id(passage): score
        for score, passage in semantic_scores(
            question_vector, passages, passage_vectors
        )
    }

    # The order the chat endpoints try their branches in.  Retrieval is traced
    # either way, so the console can still show what it *would* have chosen
    # when an earlier gate answers the question first.
    if subject:
        outcome = "handover"
    elif wants_photos(question):
        outcome = "photos"
    elif not selected:
        outcome = "refusal"
    else:
        outcome = "model"

    scored = []
    for passage in passages:
        overlap = _overlap_score(units, passage)
        bonus = 1.0 if intents & set(passage.intents) else 0.0
        cosine = similarity.get(id(passage))
        scored.append({
            "label": passage.label,
            "text": passage.text,
            "intents": list(passage.intents),
            "identity": passage.identity,
            "shared_strong": sorted(units.strong & passage.units.strong),
            "shared_weak": sorted(units.weak & passage.units.weak),
            "overlap": round(overlap, 3),
            "bonus": bonus,
            "score": round(overlap + bonus, 3),
            "over_threshold": overlap + bonus >= threshold,
            "cosine": None if cosine is None else round(cosine, 3),
            "over_semantic": cosine is not None and cosine >= semantic_threshold,
            "selected": id(passage) in chosen,
        })
    scored.sort(
        key=lambda row: (row["score"], row["cosine"] or 0.0), reverse=True
    )

    return {
        "question": question,
        "normalized": normalized,
        "syllables": marks,
        "dropped": [mark for mark in marks if mark in STOPWORDS],
        "kept": kept,
        "pairs": pairs,
        "latin": latin,
        "weak": sorted(units.weak),
        "subject": subject,
        "wants_photos": wants_photos(question),
        "requested_sexes": sorted(requested_sexes(question)),
        "intents": sorted(intents),
        "threshold": threshold,
        "threshold_is_lexical_only": not intents,
        "passages": scored,
        "selected": selected,
        "reason": reason,
        "outcome": outcome,
        "semantic_threshold": semantic_threshold,
        "semantic_available": any(vector for vector in passage_vectors)
        and question_vector is not None,
        "semantic_dims": len(question_vector) if question_vector else 0,
        "context": passages_as_context(selected),
        "max_passages": MAX_PASSAGES,
    }


# --------------------------------------------------------------------------
# Photographs — answered from the record's own files, never by the model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Photo:
    """One picture the site can show, already published under /static."""

    url: str
    caption: str
    sex: str | None = None


# Asking for a picture is matched on whole syllable runs rather than on the
# filtered units used for retrieval: ``မ`` is a stopword, so ``အမ``
# ("female") disappears before it can ever be recognised.
PHOTO_TERMS = ("ဓာတ်ပုံ", "ရုပ်ပုံ", "ပုံ")
PHOTO_TERMS_LATIN = ("photo", "photos", "photograph", "picture", "pictures", "image", "images", "pic")

# ``ပုံစံ`` ("form", as in governance type) contains ``ပုံ`` and is not a
# request for a picture.
PHOTO_TERM_EXCLUSIONS = ("ပုံစံ",)

SEX_TERMS = {
    "male": ("အထီး",),
    "female": ("အမ", "အမီ"),
}
SEX_TERMS_LATIN = {"male": ("male",), "female": ("female",)}

SEX_LABELS = {"male": "အထီး", "female": "အမ"}


def _syllable_runs(message: str) -> list[str]:
    return syllables(normalize_mm(message))


def _count_run(marks: list[str], term: str) -> int:
    run = syllables(normalize_mm(term))
    if not run:
        return 0
    size = len(run)
    return sum(
        1 for index in range(len(marks) - size + 1)
        if marks[index:index + size] == run
    )


def wants_photos(question: str) -> bool:
    """True when the member asked to see a picture."""
    marks = _syllable_runs(question)
    excluded = sum(_count_run(marks, term) for term in PHOTO_TERM_EXCLUSIONS)
    myanmar_hits = sum(_count_run(marks, term) for term in PHOTO_TERMS)
    if myanmar_hits > excluded:
        return True
    words = set(_latin_words(normalize_mm(question)))
    return bool(words & set(PHOTO_TERMS_LATIN))


def requested_sexes(question: str) -> set[str]:
    """Which sex the member asked for, if they named one."""
    marks = _syllable_runs(question)
    words = set(_latin_words(normalize_mm(question)))
    found = set()
    for sex, terms in SEX_TERMS.items():
        if any(_count_run(marks, term) for term in terms):
            found.add(sex)
        elif words & set(SEX_TERMS_LATIN[sex]):
            found.add(sex)
    return found


def _is_local_asset(url) -> bool:
    """Only files this site publishes may be shown in a reply."""
    return (
        isinstance(url, str)
        and url.startswith("/static/")
        and "//" not in url[1:]
        and ".." not in url
    )


def record_photos(kind: str, record: dict) -> list[Photo]:
    """Every published picture of one record, labelled where the record says."""
    photos = []
    seen = set()

    def add(url, caption, sex=None):
        if _is_local_asset(url) and url not in seen:
            seen.add(url)
            photos.append(Photo(url, caption, sex))

    name = (
        record.get("name_my") or record.get("name_mm")
        or record.get("name_en") or record.get("name") or ""
    )
    if kind == "animal":
        add(record.get("male_image_url"), f"{name} — အထီး", "male")
        add(record.get("female_image_url"), f"{name} — အမ", "female")
        add(record.get("image_url"), name)
    else:
        urls = record.get("image_urls") or []
        if not isinstance(urls, list):
            urls = []
        for position, url in enumerate(urls, start=1):
            add(url, name if position == 1 else f"{name} ({position})")
        add(record.get("image_url"), name)
    return photos


def resolve_photos(question: str, kind: str, record: dict):
    """Pictures that answer this question, and why there are none if empty.

    A named sex is never answered with an unlabelled photograph.  The site
    promises not to substitute a stand-in picture, and quietly showing the
    cover photo as "the female" would break exactly that promise.
    """
    photos = record_photos(kind, record)
    sexes = requested_sexes(question)

    if sexes:
        picked = [photo for photo in photos if photo.sex in sexes]
        if picked:
            return picked, "matched"
        return [], "no-sex-photo"

    return (photos, "matched") if photos else ([], "no-photo")
