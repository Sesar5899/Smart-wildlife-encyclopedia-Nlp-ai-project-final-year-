"""မြန်မာ ယူနီကုဒ် ပုံမှန်ပြုပြင်ခြင်း — canonicalisation of Burmese text.

Unicode 5.1 Myanmar only.  Zawgyi input is explicitly out of scope: the
project treats every incoming string as Unicode, which keeps the pipeline
deterministic and removes the risk of a Zawgyi heuristic mis-firing on
legitimate Unicode and mangling it.

Three jobs, in order:

1. Repair the invisible junk that survives copy/paste — zero-width joiners,
   BOMs, non-breaking spaces.
2. Repair the confusables that no amount of care prevents: Myanmar digit
   zero (၀ U+1040) typed where the letter wa (ဝ U+101D) belongs, and the
   reverse.  The two are indistinguishable in almost every Myanmar font.
3. Re-order the combining marks inside every syllable into canonical order,
   so two visually identical strings typed in a different keystroke order
   compare equal byte-for-byte.

Everything here is deterministic and dependency-free.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# Code-point groups
# --------------------------------------------------------------------------

CONSONANTS = "က-အဿ"
INDEPENDENT_VOWELS = "ဢ-ဧဩဪ"
BASE = CONSONANTS + INDEPENDENT_VOWELS

MEDIALS = "ျ-ှ"          # U+103B..U+103E  ya ra wa ha
VOWEL_SIGNS = "ါ-ဲ"      # U+102B..U+1032
TONE_MARKS = "ံ-း"        # U+1036..U+1038
ASAT = "်"                  # U+103A
VIRAMA = "္"                # U+1039

COMBINING = MEDIALS + VOWEL_SIGNS + TONE_MARKS + ASAT + VIRAMA

MYANMAR_RANGE = re.compile(r"[က-႟ꩠ-ꩿꧠ-꧿]")

DIGITS_MM = "၀၁၂၃၄၅၆၇၈၉"
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate(DIGITS_MM)}

# Invisible characters that survive copy/paste and break exact matching.
INVISIBLE = re.compile(r"[​‌‍⁠﻿­]")
WHITESPACE = re.compile(r"[\s 　]+")


def contains_myanmar(text: str) -> bool:
    """True if the string contains at least one Myanmar-script character."""
    return bool(text) and bool(MYANMAR_RANGE.search(text))


# --------------------------------------------------------------------------
# Canonical mark ordering
# --------------------------------------------------------------------------

# Canonical order of the combining marks inside one syllable cluster.
_ORDER = {
    VIRAMA: 1,
    "ျ": 3, "ြ": 4, "ွ": 5, "ှ": 6,   # medials ya ra wa ha
    "ေ": 7,
    "ိ": 8, "ီ": 8,
    "ု": 9, "ူ": 9,
    "ါ": 10, "ာ": 10,
    "ဲ": 11,
    "ံ": 12,
    "့": 13,
    "း": 14,
}
_VOWEL_SET = set("ါာိီုူေဲ")

_CLUSTER_RE = re.compile(
    r"([" + BASE + r"])((?:[" + COMBINING + r"]|" + VIRAMA + r"[" + BASE + r"])*)"
)


def _order_marks(marks: str) -> str:
    """Sort one cluster's combining marks into canonical order.

    U+103A (asat) is positional rather than fixed-weight: it trails a vowel
    in the -aw rhyme (ကျော်) but immediately follows a bare consonant in a
    killed final (ကက်).  Its weight is therefore read off the cluster's own
    contents.
    """
    if len(marks) < 2:
        return marks
    asat_weight = 15 if _VOWEL_SET & set(marks) else 2
    stacked = ""
    if marks.startswith(VIRAMA) and len(marks) > 1:
        stacked, marks = marks[:2], marks[2:]
    keyed = sorted(
        enumerate(marks),
        key=lambda p: (asat_weight if p[1] == ASAT else _ORDER.get(p[1], 20), p[0]),
    )
    return stacked + "".join(ch for _, ch in keyed)


def _canonicalise_clusters(text: str) -> str:
    return _CLUSTER_RE.sub(lambda m: m.group(1) + _order_marks(m.group(2)), text)


# --------------------------------------------------------------------------
# Confusable repair
# --------------------------------------------------------------------------

# Myanmar digit zero (၀) is routinely typed where the letter wa (ဝ) belongs
# and vice versa — they are visually identical in most fonts.  Inside a word
# we always want the letter; a standalone run of digits stays numeric.
_DIGIT_WA = re.compile(
    r"(?<=[" + BASE + COMBINING + r"])၀|၀(?=[" + COMBINING + BASE + r"])"
)

# The reverse: letter wa sitting inside an otherwise numeric run.
_WA_DIGIT = re.compile(r"(?<=[" + DIGITS_MM + r"])ဝ|ဝ(?=[" + DIGITS_MM + r"])")

# Abbreviations that expand to their spelled-out form so the index sees one shape.
_EXPANSIONS = {
    "၎": "၎င်း",
}


def normalize_mm(text: str, *, fold_spaces: bool = True) -> str:
    """Return `text` in canonical Myanmar Unicode.

    Strips invisibles, repairs the ဝ/၀ confusion, expands abbreviations and
    re-orders combining marks.  Safe on non-Myanmar input: Latin text passes
    through with only whitespace folding applied.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = INVISIBLE.sub("", text)

    text = _DIGIT_WA.sub("ဝ", text)
    text = _WA_DIGIT.sub("၀", text)

    for src, dst in _EXPANSIONS.items():
        text = text.replace(src, dst)

    text = _canonicalise_clusters(text)

    if fold_spaces:
        text = WHITESPACE.sub(" ", text)
    return text.strip()


def arabic_digits(text: str) -> str:
    """Rewrite Myanmar digits as ASCII, for numeric comparison and sorting."""
    return text.translate(_DIGIT_MAP)
