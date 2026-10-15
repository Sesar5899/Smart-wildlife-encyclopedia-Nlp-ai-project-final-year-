"""Public sources a species chat falls back to when this project is silent.

A chat answers from the published record and nothing else.  That is still the
rule, but a record that was never filled in for a question used to end the
conversation: the member was told the information is not in the record and was
left to go and find it somewhere else.  This module is the second place a chat
may look — Wikipedia, GBIF and relevant pages from established wildlife,
government, zoo and research sites — so the answer can be given here, in
Burmese, with every outside page actually used named under it.

Two things keep the fallback honest:

* It is reached only for questions that are about the species.  A question the
  site refuses outright — a recipe, a share price — is refused exactly as it
  was before and never becomes an outside lookup.
* What it returns is passages, not answers.  They are retrieved and prompted
  the same way the record's own passages are, so the model still writes only
  what a source placed in front of it actually says.

Nothing here writes to the database, and nothing here is on the path of a
question the record can answer.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import rag
import species_sources
from config import Config
from myanmar import normalize_mm

EN_WIKI = species_sources.EN_WIKI
MY_WIKI = species_sources.MY_WIKI

# One reader waiting on an answer is not an overnight import: a slow source is
# dropped rather than retried until the request times out.
USER_AGENT = (
    "MyanmarWildlifeEncyclopedia/1.0 "
    "(educational encyclopedia; contact myominko1011@gmail.com)"
)
# DuckDuckGo's lightweight HTML endpoint serves its result page only to a
# browser-shaped request.  Destination publishers still receive the honest
# encyclopedia user agent above.
SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
LEAD_LIMIT = 1500
SECTION_LIMIT = 1600
CONTEXT_LIMIT = 12000
MIN_ARTICLE_LENGTH = 120
MAX_WEB_ARTICLES = 4
MAX_SAVED_SOURCE_ARTICLES = 6
MAX_WEB_BYTES = 1_500_000
SEARCH_URL = "https://lite.duckduckgo.com/lite/"
GBIF_API = "https://api.gbif.org/v1"
# A lookup that failed is remembered only briefly, so a moment without a
# network connection does not silence the fallback for the rest of the day.
FAILURE_TTL = 600

LANGUAGES = {
    "my": ("Wikipedia (မြန်မာ)", "https://my.wikipedia.org/wiki/"),
    "en": ("Wikipedia (အင်္ဂလိပ်)", "https://en.wikipedia.org/wiki/"),
}
# What a passage's heading says about it in the prompt.  The source is named
# under the answer, by the page, from data the model never sees — so a passage
# label says only which language its words are in.  A label that named the
# source would be read back out in the answer, which is the one place it must
# not appear.
LANGUAGE_NAMES = {"my": "မြန်မာ", "en": "အင်္ဂလိပ်"}

# Search is broad, fetching is not.  Only established animal, conservation,
# government, zoo and research publishers are eligible to become evidence.
# A search result can therefore never turn a member's wording into an
# arbitrary server-side request.
SOURCE_DOMAINS = (
    ("catsg.org", "IUCN SSC Cat Specialist Group"),
    ("iucnredlist.org", "IUCN Red List"),
    ("iucn.org", "IUCN"),
    ("worldwildlife.org", "WWF"),
    ("animaldiversity.org", "Animal Diversity Web"),
    ("nationalzoo.si.edu", "Smithsonian's National Zoo"),
    ("si.edu", "Smithsonian Institution"),
    ("animals.sandiegozoo.org", "San Diego Zoo Wildlife Alliance"),
    ("ielc.libguides.com", "San Diego Zoo Wildlife Alliance Library"),
    ("britannica.com", "Encyclopaedia Britannica"),
    ("nationalgeographic.com", "National Geographic"),
    ("birdlife.org", "BirdLife International"),
    ("ebird.org", "eBird"),
    ("fws.gov", "U.S. Fish & Wildlife Service"),
    ("nps.gov", "U.S. National Park Service"),
    ("fao.org", "FAO"),
    ("cites.org", "CITES"),
    ("cms.int", "Convention on Migratory Species"),
    ("wcs.org", "Wildlife Conservation Society"),
    ("fauna-flora.org", "Fauna & Flora"),
    ("link.springer.com", "Springer Nature"),
    ("cambridge.org", "Cambridge University Press"),
    ("onlinelibrary.wiley.com", "Wiley Online Library"),
    ("ncbi.nlm.nih.gov", "PubMed Central"),
    ("jstage.jst.go.jp", "J-STAGE"),
    ("asianjab.com", "Asian Journal of Agriculture and Biology"),
    ("indiabiodiversity.org", "India Biodiversity Portal"),
    ("nparks.gov.sg", "Singapore National Parks"),
    ("singapore.biodiversity.online", "Singapore Biodiversity"),
    ("ecologyasia.com", "Ecology Asia"),
)

INTENT_SEARCH_TERMS = {
    "population": "population estimate number remaining",
    "status": "conservation status endangered",
    "conservation": "conservation threats recovery",
    "threats": "threats decline poaching habitat loss",
    "habitat": "habitat ecology",
    "diet": "diet feeding food",
    "distribution": "range distribution countries",
    "size": "size weight length lifespan",
    "appearance": "appearance colour color coat fur markings",
    "sex_difference": "male female sexual dimorphism appearance coloration",
    "behaviour": "behavior reproduction lifespan",
    "taxonomy": "taxonomy species classification",
    "legal": "legal protection CITES",
    "use_trade": "wildlife trade use CITES",
}

# A fetched page is credited only if the excerpt used for a specific question
# actually speaks to its subject. Search ranking or a species name alone is not
# evidence about diet, population, habitat or the other facts below.
EVIDENCE_TERMS = {
    "diet": ("diet", "feed", "food", "eat", "prey", "insect", "seed", "grain", "အစာ", "စား"),
    "population": ("population", "individual", "remaining", "number", "count", "အကောင်ရေ", "ဦးရေ"),
    "habitat": ("habitat", "wetland", "forest", "grassland", "reedbed", "live", "နေထိုင်", "တော"),
    "distribution": ("distribution", "range", "found in", "occurs", "native to", "ဖြန့်ကျက်", "ဒေသ"),
    "size": ("length", "weight", "height", "size", "cm", "kg", "အရွယ်", "အလေးချိန်"),
    "appearance": (
        "appearance", "colour", "color", "coat", "fur", "marking",
        "pattern", "ရုပ်သွင်", "အသွင်အပြင်", "အရောင်", "အမွေး",
    ),
    "sex_difference": (
        "sexual dimorphism", "sex difference", "male", "female", "sexes",
        "အမနဲ့အထီး", "အမနှင့်အထီး", "လိင်ကွဲပြား", "ကျားမကွဲပြား",
    ),
    "behaviour": ("behav", "breed", "nest", "sleep", "active", "အပြုအမူ", "အိပ်", "မျိုးပွား"),
    "threats": ("threat", "decline", "poach", "habitat loss", "အန္တရာယ်", "ခြိမ်းခြောက်"),
    "status": ("status", "vulnerable", "endangered", "iucn", "red list", "မျိုးသုဉ်း"),
    "conservation": ("conservation", "protect", "recovery", "ထိန်းသိမ်း", "ကာကွယ်"),
}


def _mentions_topic(text: str, terms: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(
        re.search(r"\b" + re.escape(term) + r"[a-z]*\b", folded)
        if term.isascii() else term in folded
        for term in terms
    )
EXTRA_SEARCH_TERMS = (
    (("သက်တမ်း", "lifespan", "how long", "how old"), "lifespan longevity"),
    (("အိပ်", "sleep"), "sleep hours behavior"),
    (("ပြေး", "speed", "fast", "run"), "running speed"),
    (("ရေကူး", "swim"), "swimming behavior"),
    (("ကိုယ်ဝန်", "gestation", "pregnan"), "gestation reproduction"),
    (("ရောဂါ", "disease", "illness"), "health disease"),
    (
        (
            "အမနဲ့အထီး", "အမနှင့်အထီး", "အထီးနဲ့အမ", "အထီးနှင့်အမ",
            "လိင်ကွဲပြား", "ကျားမကွဲပြား", "male and female",
            "female and male", "sexual dimorphism", "sex difference",
        ),
        "male female sexual dimorphism appearance coloration",
    ),
    (
        ("ရုပ်သွင်", "အသွင်အပြင်", "အရောင်", "appearance", "colour", "color"),
        "appearance colour coat fur markings",
    ),
)

# An English article's headings are what say which questions its sections can
# answer, so each field carries the question intents ``rag`` reads out of a
# Burmese question.  Without this an English passage would have no word in
# common with the question and could never be retrieved at all.
FIELD_PASSAGES = (
    (
        "physical",
        "ရုပ်သွင်နှင့် အရွယ်အစား",
        ("size", "identity", "appearance", "sex_difference"),
    ),
    ("habitat", "နေထိုင်ရာ", ("habitat",)),
    ("diet", "အစာစားနည်း", ("diet",)),
    ("distribution", "ဖြန့်ကျက်မှု", ("distribution",)),
    ("behaviour", "အပြုအမူနှင့် မျိုးပွားခြင်း", ("behaviour",)),
    ("threats", "ခြိမ်းခြောက်မှုများ", ("threats", "population")),
    (
        "conservation",
        "ထိန်းသိမ်းရေး",
        ("conservation", "status", "population", "legal"),
    ),
    ("use_trade", "အသုံးပြုမှုနှင့် ကုန်သွယ်မှု", ("use_trade", "legal", "tourism")),
)
LEAD_LABEL = "အကျဉ်းချုပ်"
LEAD_INTENTS = ("identity", "taxonomy")

# Wildlife vocabulary that ``rag.INTENT_TERMS`` does not cover.  A question
# about a lifespan, a top speed or how an animal sleeps is a question about the
# species even though no passage of the record is filed under it, and it is
# exactly the kind of question the record tends not to answer.
TOPIC_TERMS = (
    "သက်တမ်း", "အသက်", "အိပ်", "ပြေး", "ရေကူး", "ကူးခတ်", "ပျံ", "ကြီးထွား",
    "မျိုးပွား", "သားပေါက်", "သားငယ်", "ကလေး", "မျိုးဥ", "သားကောင်", "ရန်သူ",
    "အလေးချိန်", "အမြင့်", "အလျား", "အမြီး", "ဦးချို", "စွယ်", "နှာမောင်း",
    "အတောင်", "နှုတ်သီး", "ခြေသည်း", "အမွေး", "အရေခွံ", "အသံ", "ဉာဏ်",
    "ကိုယ်ခန္ဓာ", "တိရစ္ဆာန်", "သတ္တဝါ", "မျိုးစိတ်", "မျိုးသုဉ်း", "ဇီဝ",
    "ရာသီ", "ပြောင်းရွှေ့", "အုပ်စု", "နေထိုင်", "ထူးခြား", "စိတ်ဝင်စား",
    "အရောင်", "မျိုးဆက်", "နှလုံး", "သွေး", "ကိုယ်အပူချိန်", "ကိုယ်ဝန်",
    "ရောဂါ", "ကျန်းမာ", "အာရုံ", "အမြင်", "အကြား", "အနံ့", "ဆင့်ကဲ",
    "လိုက်လျောညီထွေ", "ဆက်သွယ်", "ဒီတိရစ္ဆာန်", "ဒီမျိုးစိတ်", "၎င်း",
    "lifespan", "how long", "how old", "colour", "color", "grow",
    "live", "lives", "sleep", "run", "swim", "fly", "breed",
    "reproduc", "baby", "calf", "cub", "egg", "predator", "enemy", "weight",
    "tail", "horn", "tusk", "trunk", "wing", "beak", "claw", "fur", "skin",
    "species", "extinct", "migrat", "season", "herd", "flock", "interesting",
    "fact", "behaviour", "behavior", "heart", "pulse", "blood",
    "temperature", "gestation", "pregnan", "disease", "health", "anatomy",
    "organ", "sense", "vision", "hearing", "smell", "intelligen", "adapt",
    "evolution", "communicat", "this animal", "this species",
)
_FOLDED_TOPIC_TERMS = tuple(term.casefold() for term in TOPIC_TERMS)


def enabled() -> bool:
    """Whether the fallback may be used at all."""
    return Config.EXTERNAL_SOURCES_ENABLED


# --------------------------------------------------------------------------
# Is this question even about the species?
# --------------------------------------------------------------------------

def _names(animal: dict) -> list[str]:
    values = [
        animal.get("name_my"),
        animal.get("name_en"),
        animal.get("scientific_name"),
    ]
    values.extend(animal.get("aliases") or [])
    return [str(value).strip() for value in values if value]


def is_species_question(message: str, animal: dict) -> bool:
    """Whether a question the record cannot answer is still about this species.

    The record's own retrieval already refused this question, so the only
    thing left to decide is whether it was refused for being unanswerable or
    for being off-topic.  A question that names the species, that carries one
    of the intents the record is filed under, or that uses the vocabulary of
    animals is the first; everything else stays refused.
    """
    if rag.question_intents(message):
        return True
    normalized = normalize_mm(message).casefold()
    if re.search(r"\b(?:it|its)\b", normalized):
        return True
    if any(term in normalized for term in _FOLDED_TOPIC_TERMS):
        return True
    return any(
        normalize_mm(name).casefold() in normalized
        for name in _names(animal)
        if len(name) > 2
    )


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

_session_lock = threading.Lock()
_session = None


def session() -> requests.Session:
    """One shared connection pool, tuned for a reader rather than an import.

    ``species_sources`` retries four times with a growing backoff because an
    overnight import can afford to wait.  A member cannot: one retry is the
    most that fits inside a chat request.
    """
    global _session
    with _session_lock:
        if _session is None:
            value = requests.Session()
            retry = Retry(
                total=1,
                connect=1,
                read=1,
                backoff_factor=0.4,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET",),
            )
            value.mount("https://", HTTPAdapter(max_retries=retry))
            value.headers.update(
                {"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            _session = value
        return _session


def _api(endpoint: str, params: dict) -> dict:
    response = session().get(
        endpoint,
        params={"format": "json", "formatversion": "2", **params},
        timeout=Config.EXTERNAL_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _resolve(endpoint: str, title: str, langlink: str | None = None) -> dict | None:
    """The page one title actually names, following redirects, or None."""
    params = {
        "action": "query",
        "redirects": "1",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "titles": title,
    }
    if langlink:
        params["prop"] += "|langlinks"
        params["lllang"] = langlink
    pages = _api(endpoint, params).get("query", {}).get("pages", [])
    for page in pages:
        if page.get("missing") or not page.get("title"):
            continue
        links = page.get("langlinks") or []
        return {
            "title": page["title"],
            "langlink": links[0]["title"] if links else None,
        }
    return None


def _extract(endpoint: str, title: str) -> str:
    """The plaintext of one article.

    Asked for one title at a time on purpose: MediaWiki answers a batch of
    titles with the lead of a single page, which is how an article turns into
    an empty record.
    """
    data = _api(
        endpoint,
        {
            "action": "query",
            "redirects": "1",
            "prop": "extracts",
            "explaintext": "1",
            "exlimit": "1",
            "titles": title,
        },
    )
    for page in data.get("query", {}).get("pages", []):
        if not page.get("missing"):
            return page.get("extract") or ""
    return ""


# --------------------------------------------------------------------------
# What a fetched article becomes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Article:
    """One outside article, already split into retrievable passages."""

    lang: str
    title: str
    passages: tuple
    url_override: str | None = None
    label_override: str | None = None

    @property
    def url(self) -> str:
        if self.url_override:
            return self.url_override
        return LANGUAGES[self.lang][1] + quote(self.title.replace(" ", "_"))

    @property
    def label(self) -> str:
        if self.label_override:
            return self.label_override
        return LANGUAGES[self.lang][0]


@dataclass(frozen=True)
class Record:
    """Everything the outside sources hold about one species."""

    articles: tuple

    @property
    def passages(self) -> list:
        return [passage for article in self.articles for passage in article.passages]

    def sources(self) -> list[dict]:
        """The links shown under an answer these passages produced."""
        return [
            {
                "group": "answer",
                "label": article.label,
                "detail": f"ဤဖြေကြားချက်အတွက် အသုံးပြုသည့် ပြင်ပရင်းမြစ် — {article.title}",
                "url": article.url,
                "external": True,
            }
            for article in self.articles
        ]

    def sources_for(self, passages) -> list[dict]:
        """Only the article links whose text was actually sent to DeepSeek.

        A context budget can omit the tail of a multi-language record.  The
        source panel must never cite an article that was not in that request.
        Passage identity is stable within a cached ``Record``, so membership
        can be determined without adding provider metadata to the model text.
        """
        used = {id(passage) for passage in passages}
        included = tuple(
            article
            for article in self.articles
            if any(id(passage) in used for passage in article.passages)
        )
        return Record(included).sources()


def _passage(label, text, lang, intents=(), *, limit=SECTION_LIMIT, identity=False):
    text = species_sources.trim((text or "").strip(), limit)
    if len(text) < 40:
        return None
    return rag.Passage(
        f"{label} ({LANGUAGE_NAMES[lang]})", text, tuple(intents), identity
    )


def _article_passages(extract: str, lang: str) -> list:
    """Split one article into the passages a question can be matched against.

    An English article is filed by ``species_sources``' own heading map, which
    is what gives its sections the intents a Burmese question is read for.  A
    Burmese article keeps its own headings instead: its words are the ones a
    Burmese question shares, so lexical retrieval already reaches it.
    """
    lead, sections = species_sources.split_sections(extract)
    passages = []
    summary = _passage(
        LEAD_LABEL, lead, lang, LEAD_INTENTS, limit=LEAD_LIMIT, identity=True
    )
    if summary:
        passages.append(summary)

    if lang == "en":
        assigned = species_sources.assign_sections(sections)
        for field, label, intents in FIELD_PASSAGES:
            passage = _passage(label, assigned.get(field), lang, intents)
            if passage:
                passages.append(passage)
        return passages

    for section in sections:
        heading = section["heading"]
        if any(word in heading.casefold() for word in species_sources.SECTION_SKIP):
            continue
        passage = _passage(heading, section["body"], lang)
        if passage:
            passages.append(passage)
    return passages


def _titles(animal: dict) -> list[str]:
    """The article titles worth asking for, best first."""
    titles, seen = [], set()
    for value in (animal.get("scientific_name"), animal.get("name_en")):
        title = (value or "").strip()
        key = title.casefold()
        if title and key not in seen:
            seen.add(key)
            titles.append(title)
    return titles


def _source_label(url: str) -> str | None:
    """A curated publisher label for one HTTPS URL, or None if ineligible."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    for domain, label in SOURCE_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return label
    return None


_PRIMARY_POPULATION_DOMAINS = (
    "catsg.org",
    "iucnredlist.org",
    "iucn.org",
    "cites.org",
    "cms.int",
    "fao.org",
    "fws.gov",
    "nps.gov",
)
_RESEARCH_POPULATION_DOMAINS = (
    "animaldiversity.org",
    "birdlife.org",
    "cambridge.org",
    "link.springer.com",
    "ncbi.nlm.nih.gov",
    "onlinelibrary.wiley.com",
    "jstage.jst.go.jp",
    "asianjab.com",
)


def _population_source_rank(article: Article) -> int:
    """Put population authorities before summaries without exposing labels.

    The prompt deliberately receives source-neutral passage labels because the
    UI owns citations. Ordering here is therefore the model's conflict signal:
    assessments and official pages first, research next, established secondary
    publishers after that, and Wikipedia last.
    """
    hostname = (urlparse(article.url).hostname or "").casefold().rstrip(".")

    def belongs_to(domains):
        return any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in domains
        )

    if belongs_to(_PRIMARY_POPULATION_DOMAINS) or hostname.endswith(".gov"):
        return 0
    if belongs_to(_RESEARCH_POPULATION_DOMAINS):
        return 1
    if hostname == "wikipedia.org" or hostname.endswith(".wikipedia.org"):
        return 4
    return 2


def _has_population_number(text: str) -> bool:
    """Whether a population passage carries a count, not just a year/percent."""
    digit_map = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
    normalized = text.translate(digit_map)
    count_terms = (
        "population", "individual", "animals", "mature", "adult",
        "remaining", "remain", "estimated at", "number of", "count",
        "အကောင်ရေ", "ဦးရေ", "ကောင်",
    )
    for match in re.finditer(
        r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9])", normalized
    ):
        token = match.group(0).replace(",", "")
        if not token:
            continue
        value = float(token)
        # Publication/assessment years and percentages are metadata or trends,
        # not the number of animals requested by a count question.
        if token.isdigit() and len(token) == 4 and 1800 <= value <= 2100:
            continue
        tail = normalized[match.end():match.end() + 24].lstrip().casefold()
        if tail.startswith("%") or tail.startswith("percent"):
            continue
        if re.match(r"(?:million\s+)?years?\b", tail):
            continue
        window = normalized[max(0, match.start() - 100):match.end() + 100].casefold()
        if any(term in window for term in count_terms):
            return True
    return False


def _latest_population_question(message: str) -> bool:
    normalized = normalize_mm(message).casefold()
    return any(
        term in normalized
        for term in ("နောက်ဆုံး", "လက်ရှိ", "အခု", "latest", "current", "most recent")
    )


def _current_population_passage(text: str) -> bool:
    folded = text.casefold()
    return any(
        marker in folded
        for marker in (
            "current population", "current wild population", "current population size",
            "latest population", "most recent population", "as of",
            "လက်ရှိအကောင်ရေ", "လက်ရှိ အကောင်ရေ", "နောက်ဆုံးအကောင်ရေ",
            "နောက်ဆုံး အကောင်ရေ",
        )
    ) and _has_population_number(text)


class _SearchResults(HTMLParser):
    """The result links from DuckDuckGo's deliberately simple HTML page."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        values = dict(attrs)
        classes = values.get("class", "").split()
        if "result-link" in classes or "result__a" in classes:
            self.links.append(values.get("href", ""))


class _PageLinks(HTMLParser):
    """Links on a publisher's own search-results page."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def _result_url(href: str) -> str | None:
    """Unwrap one DuckDuckGo redirect and discard tracking/fragments."""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    candidate = unquote(query.get("uddg", [href])[0])
    target = urlparse(candidate)
    if not _source_label(candidate):
        return None
    return urlunparse((target.scheme, target.netloc, target.path, "", target.query, ""))


def _search_topic(message: str) -> str:
    normalized = normalize_mm(message).casefold()
    terms = [
        INTENT_SEARCH_TERMS[intent]
        for intent in sorted(rag.question_intents(message))
        if intent in INTENT_SEARCH_TERMS
    ]
    terms.extend(
        search
        for triggers, search in EXTRA_SEARCH_TERMS
        if any(trigger in normalized for trigger in triggers)
    )
    return " ".join(dict.fromkeys(terms)) or "animal species facts ecology"


def _discover_urls(animal: dict, message: str) -> list[str]:
    """Find relevant pages, then keep only curated public publishers."""
    identities = list(dict.fromkeys(
        str(value).strip() for value in
        (animal.get("scientific_name"), animal.get("name_en")) if value
    ))
    if not identities:
        return []
    topic = _search_topic(message)

    def search(identity):
        try:
            response = requests.get(
                SEARCH_URL,
                params={"q": f'"{identity}" {topic} -wikipedia'},
                headers={
                    "User-Agent": SEARCH_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=Config.EXTERNAL_TIMEOUT,
            )
            response.raise_for_status()
            parser = _SearchResults()
            parser.feed(response.text)
            return parser.links
        except (requests.RequestException, ValueError, TypeError):
            return []

    with ThreadPoolExecutor(max_workers=len(identities)) as pool:
        results = list(pool.map(search, identities))
    urls, publishers = [], set()
    for links in results:
        for href in links:
            url = _result_url(href)
            publisher = _source_label(url) if url else None
            if url and url not in urls and publisher not in publishers:
                urls.append(url)
                publishers.add(publisher)
            if len(urls) >= MAX_WEB_ARTICLES:
                return urls
    return urls


class _ReadablePage(HTMLParser):
    """Small dependency-free article text extractor for curated web pages."""

    BLOCKS = {"h1", "h2", "h3", "p", "li"}
    SKIP = {"script", "style", "noscript", "svg", "form", "nav", "footer"}

    def __init__(self):
        super().__init__()
        self.title = ""
        self._skip = 0
        self._preferred = 0
        self._capture = None
        self._buffer = []
        self._title_buffer = []
        self.all_blocks = []
        self.preferred_blocks = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag in {"main", "article"}:
            self._preferred += 1
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:title":
            self.title = values.get("content", "").strip() or self.title
        if not self._skip and tag in self.BLOCKS and self._capture is None:
            self._capture = tag
            self._buffer = []

    def handle_endtag(self, tag):
        if self._capture == tag:
            text = " ".join("".join(self._buffer).split())
            if len(text) >= 30:
                self.all_blocks.append(text)
                if self._preferred:
                    self.preferred_blocks.append(text)
            self._capture = None
            self._buffer = []
        if tag in {"main", "article"} and self._preferred:
            self._preferred -= 1
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        if self._capture is not None:
            self._buffer.append(data)


class _PageWithTitle(_ReadablePage):
    def __init__(self):
        super().__init__()
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "title":
            self._in_title = True
            self._title_buffer = []

    def handle_endtag(self, tag):
        if tag == "title":
            fallback = " ".join("".join(self._title_buffer).split())
            if not self.title:
                self.title = fallback
            self._in_title = False
        super().handle_endtag(tag)

    def handle_data(self, data):
        if self._in_title:
            self._title_buffer.append(data)
        super().handle_data(data)


def _blocks_as_passages(blocks, message: str) -> tuple:
    intents = tuple(sorted(rag.question_intents(message)))
    passages, current = [], []
    size = 0
    for block in blocks:
        if current and size + len(block) > SECTION_LIMIT:
            passages.append(
                rag.Passage("Website excerpt (English)", "\n".join(current), intents)
            )
            current, size = [], 0
        current.append(block)
        size += len(block)
        if len(passages) >= 3:
            break
    if current and len(passages) < 4:
        passages.append(
            rag.Passage("Website excerpt (English)", "\n".join(current), intents)
        )
    return tuple(passages)


def _fetch_web_article(url: str, message: str) -> Article | None:
    label = _source_label(url)
    if not label:
        return None
    with requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=Config.EXTERNAL_TIMEOUT,
        stream=True,
    ) as response:
        response.raise_for_status()
        if not _source_label(response.url):
            return None
        content_type = response.headers.get("Content-Type", "").casefold()
        if "html" not in content_type:
            return None
        chunks, size = [], 0
        for chunk in response.iter_content(32768):
            size += len(chunk)
            if size > MAX_WEB_BYTES:
                break
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        page = b"".join(chunks).decode(encoding, errors="replace")

    parser = _PageWithTitle()
    parser.feed(page)
    blocks = parser.preferred_blocks or parser.all_blocks
    passages = _blocks_as_passages(blocks, message)
    if sum(len(item.text) for item in passages) < MIN_ARTICLE_LENGTH:
        return None
    return Article(
        "en",
        parser.title or urlparse(url).hostname or label,
        passages,
        response.url,
        label,
    )


def _safe_fetch_web_article(url: str, message: str) -> Article | None:
    try:
        return _fetch_web_article(url, message)
    except (requests.RequestException, UnicodeError, ValueError, TypeError):
        return None


def _gbif_article(animal: dict, message: str) -> Article | None:
    """Stable non-Wikipedia taxonomy and contributed descriptions from GBIF."""
    name = animal.get("scientific_name") or animal.get("name_en")
    if not name:
        return None
    match = session().get(
        f"{GBIF_API}/species/match",
        params={"name": name},
        timeout=Config.EXTERNAL_TIMEOUT,
    )
    match.raise_for_status()
    taxon = match.json()
    key = taxon.get("usageKey")
    if not key or taxon.get("confidence", 0) < 70:
        return None

    facts = [
        f"Scientific name: {taxon.get('scientificName') or name}.",
        "Taxonomy: " + ", ".join(
            f"{rank} {taxon[rank]}"
            for rank in ("kingdom", "phylum", "class", "order", "family", "genus")
            if taxon.get(rank)
        ) + ".",
    ]
    descriptions = session().get(
        f"{GBIF_API}/species/{key}/descriptions",
        timeout=Config.EXTERNAL_TIMEOUT,
    )
    descriptions.raise_for_status()
    for item in descriptions.json().get("results", []):
        text = " ".join(str(item.get("description") or "").split())
        if len(text) >= 80 and (item.get("language") in (None, "", "eng")):
            source = item.get("source") or "GBIF-contributed description"
            facts.append(f"{source}: {text}")
        if len(facts) >= 5:
            break

    passages = _blocks_as_passages(facts, message)
    return Article(
        "en",
        taxon.get("canonicalName") or name,
        passages,
        f"https://www.gbif.org/species/{key}",
        "GBIF",
    )


def _wikipedia_articles(animal: dict) -> list[Article]:
    """Burmese and English Wikipedia articles when either one exists."""
    articles = []
    english = None
    for title in _titles(animal):
        page = _resolve(EN_WIKI, title, langlink="my")
        if page:
            english = page
            break

    burmese_title = (english or {}).get("langlink") or (animal.get("name_my") or "").strip()
    if burmese_title:
        page = _resolve(MY_WIKI, burmese_title)
        if page:
            extract = _extract(MY_WIKI, page["title"])
            if len(extract.strip()) >= MIN_ARTICLE_LENGTH:
                articles.append(
                    Article("my", page["title"], tuple(_article_passages(extract, "my")))
                )

    if english:
        extract = _extract(EN_WIKI, english["title"])
        if len(extract.strip()) >= MIN_ARTICLE_LENGTH:
            articles.append(
                Article("en", english["title"], tuple(_article_passages(extract, "en")))
            )
    return articles


def _discovered_articles(animal: dict, message: str) -> list[Article]:
    try:
        urls = _discover_urls(animal, message)
    except (requests.RequestException, ValueError, TypeError):
        return []
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        fetched = list(
            pool.map(lambda url: _safe_fetch_web_article(url, message), urls)
        )
    return [article for article in fetched if article]


def _saved_source_articles(animal: dict, message: str) -> list[Article]:
    """Read the record's already-reviewed public sources before web discovery.

    Animal records can carry field-level evidence that the local summary did
    not quote in full.  Reusing those URLs gives every species the same trusted
    fallback without allowing an arbitrary URL to be fetched: the normal HTTPS
    publisher allowlist still applies, and duplicate URLs are removed before
    any request is made.
    """
    urls = []
    for source in animal.get("sources") or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if url and _source_label(url) and url not in urls:
            urls.append(url)
        if len(urls) >= MAX_SAVED_SOURCE_ARTICLES:
            break
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        fetched = list(
            pool.map(lambda url: _safe_fetch_web_article(url, message), urls)
        )
    return [article for article in fetched if article]


def _journal_articles(animal: dict, message: str) -> list[Article]:
    """Read a publisher's searchable HTML article when web results lead to PDFs.

    The journal's public search page indexes its article HTML, while general
    search engines often return only the PDF download.  Only a page whose URL
    contains the complete scientific binomial is eligible for this species.
    """
    name = (animal.get("scientific_name") or "").strip()
    if "diet" not in rag.question_intents(message) or len(name.split()) < 2:
        return []
    try:
        response = requests.get(
            "https://www.asianjab.com/",
            params={"s": name},
            headers={"User-Agent": SEARCH_USER_AGENT},
            timeout=Config.EXTERNAL_TIMEOUT,
        )
        response.raise_for_status()
        parser = _PageLinks()
        parser.feed(response.text)
    except (requests.RequestException, ValueError, TypeError):
        return []

    binomial = [part.casefold() for part in name.split()[:2]]
    for href in parser.links:
        url = urljoin(response.url, href)
        path = urlparse(url).path.casefold()
        if (_source_label(url) == "Asian Journal of Agriculture and Biology"
                and all(part in path for part in binomial)
                and not path.endswith(".pdf")):
            article = _safe_fetch_web_article(url, message)
            if article:
                return [article]
    return []


def _safe_gbif_article(animal: dict, message: str) -> Article | None:
    try:
        return _gbif_article(animal, message)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _fetch(animal: dict, message: str = "") -> Record | None:
    """Look one species up across independent public sources in parallel."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        wikipedia_future = pool.submit(_wikipedia_articles, animal)
        saved_future = pool.submit(_saved_source_articles, animal, message)
        discovered_future = pool.submit(_discovered_articles, animal, message)
        gbif_future = pool.submit(_safe_gbif_article, animal, message)
        journal_future = pool.submit(_journal_articles, animal, message)

        try:
            articles = wikipedia_future.result()
        except (requests.RequestException, ValueError, KeyError, TypeError):
            articles = []
        articles.extend(saved_future.result())
        articles.extend(discovered_future.result())
        articles.extend(journal_future.result())
        gbif = gbif_future.result()
        if gbif:
            articles.append(gbif)

    unique, seen = [], set()
    for article in articles:
        if article.passages and article.url not in seen:
            unique.append(article)
            seen.add(article.url)
    return Record(tuple(unique)) if unique else None


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, "Record | None"]] = {}


def cache_key(animal: dict, message: str = "") -> str:
    species = str(
        animal.get("id") or animal.get("scientific_name") or animal.get("name_en")
    )
    return f"{species}:{_search_topic(message)}"


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def lookup(animal: dict, message: str = "") -> Record | None:
    """The outside record for one species, fetched once and then remembered.

    Every failure — no article, an unreachable host, a malformed answer — is
    the same answer to the caller: None, meaning the chat has nothing more to
    offer and should say so in its own words.
    """
    if not enabled():
        return None

    key = cache_key(animal, message)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

    try:
        record = _fetch(animal, message)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        record = None

    ttl = Config.EXTERNAL_CACHE_TTL if record else FAILURE_TTL
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, record)
    return record


# --------------------------------------------------------------------------
# Selecting the context for one question
# --------------------------------------------------------------------------

def context_for(message: str, record: Record) -> list:
    """The outside passages to answer this question from, within a budget.

    Retrieval is the record's own — the same scoring, the same thresholds — and
    what it picks goes first, so it is what survives when the budget runs out.
    Whatever is left of the article then follows.  A published record is read
    only for the part a question asked about, because the rest of it has been
    checked by hand and is known to be about something else; an outside article
    has had no such check, and a heading map cannot know that an "Ecology"
    section is where the feeding was written down.  Handing over the rest of a
    short article is what stops the fallback from reporting silence about
    something the article plainly says.
    """
    passages = record.passages
    if not passages:
        return []

    intents = rag.question_intents(message)
    passage_ranks = {
        id(passage): _population_source_rank(article)
        for article in record.articles
        for passage in article.passages
    }
    evidence_terms = tuple(
        term for intent in intents for term in EVIDENCE_TERMS.get(intent, ())
    )
    if evidence_terms:
        passages = [
            passage for passage in passages
            if _mentions_topic(passage.text, evidence_terms)
        ]
        if not passages:
            return []

    # A Wikipedia summary is useful when it is the only page with a number.
    # When another curated publisher supplies an actual count, the summary
    # must not replace the better-scoped estimate just because its prose
    # overlaps the question more closely.
    if "population" in intents:
        stronger_count_exists = any(
            passage_ranks.get(id(passage), 4) < 4
            and _has_population_number(passage.text)
            for passage in passages
        )
        if stronger_count_exists:
            passages = [
                passage for passage in passages
                if passage_ranks.get(id(passage), 4) < 4
            ]

        # A request for the latest count must not be answered with a historical
        # series merely because older estimates also occur in fetched pages.
        # If at least one passage explicitly identifies a current/latest count,
        # keep those passages and omit the historical estimates entirely.
        if _latest_population_question(message):
            current = [
                passage for passage in passages
                if _current_population_passage(passage.text)
            ]
            if current:
                passages = current

    selected, _ = rag.retrieve(message, passages)
    taken = {id(passage) for passage in selected}
    selected.sort(key=lambda passage: passage_ranks.get(id(passage), 3))
    remaining = [passage for passage in passages if id(passage) not in taken]
    remaining.sort(key=lambda passage: passage_ranks.get(id(passage), 3))
    ordered = selected + remaining

    budget, chosen = CONTEXT_LIMIT, []
    for passage in ordered:
        if budget <= 0:
            break
        chosen.append(passage)
        budget -= len(passage.text)
    return chosen
