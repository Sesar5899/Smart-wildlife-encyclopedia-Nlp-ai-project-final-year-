"""မြန်မာစာလုံး အသံထွက် သော့ချက် — a Soundex-style phonetic key for Burmese.

Burmese orthography preserves Pali/Sanskrit distinctions that modern speech
lost entirely.  Four different letters spell one sound, so four different
spellings of the same animal name are all "correct enough" to a reader and all
different to a database:

    ဆက်ရက်   ဇရက်   စရက်   ဆရက်      -> Acridotheres tristis

`phonetic_key` transcribes a string down to the distinctions Burmese speech
actually makes, collapsing everything else:

    * voicing and aspiration merge   (က ခ ဂ ဃ -> k,  စ ဆ ဇ ဈ သ -> s)
    * ယ / ရ merge to /j/, ဏ / န to /n/, လ / ဠ to /l/
    * ျ and ြ are one medial; ကျ ကြ ချ ဂျ all become the affricate /tɕ/
    * every stop coda (က် စ် တ် ပ် ...) becomes one glottal stop
    * every nasal coda (င် ဉ် ည် ဏ် န် မ် ံ) becomes one nasal
    * vowel length and the three tones are discarded

The `loose` variant additionally drops glottal codas, which is what lets
ဆက်ရက် and ဇရက် compare as identical rather than merely similar.
"""

from __future__ import annotations

import re

from .normalize import BASE, COMBINING, CONSONANTS, normalize_mm

# --------------------------------------------------------------------------
# Onset classes -- letters that share a phoneme map to the same ASCII symbol
# --------------------------------------------------------------------------

_ONSET = {}
for _letters, _sym in [
    ("ကခဂဃ", "k"),      # velar stops       /k kʰ g/
    ("င", "g"),            # velar nasal       /ŋ/
    ("စဆဇဈသဿ", "s"),  # sibilants + သ    /s sʰ z θ/
    ("ညဉ", "n"),          # palatal nasal     /ɲ/
    ("ဋဌဍဎတထဒဓ", "t"),# dentals           /t tʰ d/
    ("ဏန", "n"),          # alveolar nasal    /n/
    ("ပဖဗဘ", "p"),      # labial stops      /p pʰ b/
    ("မ", "m"),
    ("ယရ", "y"),          # both /j/ in modern Burmese
    ("လဠ", "l"),
    ("ဝ", "w"),
    ("ဟ", "h"),
    ("အ", ""),             # zero onset / glottal
    ("ၐၑ", "s"),
]:
    for _ch in _letters:
        _ONSET[_ch] = _sym

# Independent vowel letters carry their own nucleus.
_INDEPENDENT = {
    "ဣ": ("", "i"), "ဤ": ("", "i"),
    "ဥ": ("", "u"), "ဦ": ("", "u"),
    "ဧ": ("", "e"),
    "ဩ": ("", "o"), "ဪ": ("", "o"),
    "ဢ": ("", "a"),
}

# --------------------------------------------------------------------------
# Coda classes
# --------------------------------------------------------------------------

_STOP_CODA = set("ကခဂဃစဆဇဈဋဌဍဎတထဒဓပဖဗဘသလဠ")
_NASAL_CODA = set("ငဉညဏနမ")
_GLIDE_CODA = {"ယ": "e", "ဝ": "u"}      # နယ် -> /nɛ/, ကျွန်ုပ် style glides

_MEDIAL_Y = "ျြ"     # U+103B, U+103C -- one phoneme /j/
_MEDIAL_W = "ွ"       # U+103D
_MEDIAL_H = "ှ"       # U+103E

_VOWEL_MARKS = set("ါာိီုူေဲ")
_TONE_MARKS = set("့း")

_CLUSTER_RE = re.compile(
    r"([" + BASE + r"])((?:[" + COMBINING + r"])*)"
)


def _split_clusters(text: str):
    """Yield (base, marks) pairs, splitting stacked consonants apart."""
    for base, marks in _CLUSTER_RE.findall(text):
        stacked = ""
        idx = marks.find("္")
        if idx != -1 and idx + 1 < len(marks):
            stacked = marks[idx + 1]
            marks = marks[:idx] + marks[idx + 2:]
            yield base, marks + "်"        # base closes the current syllable
            yield stacked, ""
            continue
        yield base, marks


def _is_killed(marks: str) -> bool:
    """A pure coda: carries the asat but no vowel of its own.

    Excludes the -aw rhyme (ကျော်), where the asat trails a vowel sign and is
    a tone marker rather than a consonant killer.
    """
    return "်" in marks and not (_VOWEL_MARKS & set(marks))


def _nucleus(marks: str) -> str:
    """Map a cluster's vowel signs to one of a i u e o."""
    m = set(marks)
    has_e = "ေ" in m
    has_a = bool(m & {"ာ", "ါ"})
    if has_e and has_a:
        return "o"                       # ော / ေါ  -> /ɔ/
    if "ိ" in m and "ု" in m:
        return "o"                       # ို        -> /o/
    if has_e or "ဲ" in m:
        return "e"
    if m & {"ိ", "ီ"}:
        return "i"
    if m & {"ု", "ူ"}:
        return "u"
    if has_a:
        return "a"
    return "a"                            # inherent vowel


def _onset(base: str, marks: str) -> str:
    sym = _ONSET.get(base)
    if sym is None:
        return ""

    m = set(marks)
    # ရှ / သျှ realise as /ʃ/, which speakers group with the s-class.
    if _MEDIAL_H in m and sym in ("y", "s"):
        sym = "s"
    if m & set(_MEDIAL_Y):
        # ကျ ကြ ချ ဂျ ဂြ all collapse to the affricate /tɕ/.
        sym = "c" if sym in ("k", "") else sym + "y"
    if _MEDIAL_W in m:
        sym += "w"
    return sym


def syllable_keys(text: str) -> list[str]:
    """Transcribe `text` into a list of per-syllable phonetic keys."""
    text = normalize_mm(text, fold_spaces=False)
    clusters = list(_split_clusters(text))

    out: list[str] = []
    i = 0
    n = len(clusters)
    while i < n:
        base, marks = clusters[i]

        if base in _INDEPENDENT:
            onset, vowel = _INDEPENDENT[base]
            if marks and (_VOWEL_MARKS & set(marks)):
                vowel = _nucleus(marks)
        elif base in _ONSET:
            if _is_killed(marks):
                # Orphan coda with nothing to attach to: treat as its own beat.
                onset, vowel = _ONSET[base], ""
                out.append(onset)
                i += 1
                continue
            onset = _onset(base, marks)
            vowel = _nucleus(marks)
        else:
            i += 1
            continue

        coda = "n" if "ံ" in marks else ""

        # A following killed cluster is this syllable's coda.
        if not coda and i + 1 < n:
            nb, nm = clusters[i + 1]
            if _is_killed(nm):
                if nb in _GLIDE_CODA:
                    vowel = _GLIDE_CODA[nb]
                elif nb in _NASAL_CODA:
                    coda = "n"
                elif nb in _STOP_CODA:
                    coda = "q"
                i += 1

        out.append(onset + vowel + coda)
        i += 1
    return out


_LATIN = re.compile(r"[A-Za-z]+")


def phonetic_key(text: str, *, loose: bool = False) -> str:
    """Return the phonetic transcription of `text`.

    Latin runs (scientific and English names) are lower-cased and kept as-is so
    one index can serve both scripts.  With `loose=True`, glottal codas are
    dropped -- the single most volatile feature of casual Burmese spelling.
    """
    if not text:
        return ""

    parts: list[str] = []
    for chunk in re.split(r"([A-Za-z0-9]+)", text):
        if not chunk:
            continue
        if _LATIN.fullmatch(chunk) or chunk.isdigit():
            parts.append(chunk.lower())
        else:
            parts.extend(syllable_keys(chunk))

    key = "".join(parts)
    if loose:
        key = key.replace("q", "")
    return key


def syllables(text: str) -> list[str]:
    """Split Burmese text into syllable clusters, preserving the original script.

    Burmese is written without word separators, so this is the unit that
    n-gram entity extraction slides over.
    """
    text = normalize_mm(text, fold_spaces=False)
    clusters = list(_split_clusters(text))

    out: list[str] = []
    i = 0
    n = len(clusters)
    while i < n:
        base, marks = clusters[i]
        if base not in _ONSET and base not in _INDEPENDENT:
            i += 1
            continue
        piece = base + marks
        if not _is_killed(marks) and i + 1 < n:
            nb, nm = clusters[i + 1]
            if _is_killed(nm):
                piece += nb + nm
                i += 1
        out.append(piece)
        i += 1
    return out
