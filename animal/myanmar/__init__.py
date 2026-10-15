"""မြန်မာစာ ကိုင်တွယ်မှု အထုပ် — Myanmar text handling toolkit (Unicode only).

Public surface:
    normalize_mm(text)     -> canonical Unicode Myanmar string
    phonetic_key(text)     -> ASCII phonetic transcription (spelling-insensitive)
    syllables(text)        -> list of Burmese syllable clusters
    similarity(a, b)       -> 0.0-1.0 fuzzy score tolerant of spelling errors
"""

from .normalize import (
    arabic_digits,
    contains_myanmar,
    normalize_mm,
)
from .phonetic import phonetic_key, syllable_keys, syllables
from .fuzzy import Key, best_match, rank, similarity

__all__ = [
    "normalize_mm",
    "arabic_digits",
    "contains_myanmar",
    "phonetic_key",
    "syllables",
    "syllable_keys",
    "Key",
    "similarity",
    "best_match",
    "rank",
]
