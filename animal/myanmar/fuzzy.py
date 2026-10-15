"""စာလုံးပေါင်း မှားယွင်းမှု ခံနိုင်ရည်ရှိသော ရှာဖွေမှု — spelling-tolerant matching.

Scoring runs in tiers, cheapest and most certain first:

    1.00  normalised text is identical
    0.99  full phonetic keys are identical      (ဇရက် vs စရက်)
    0.97  loose phonetic keys are identical     (ဆက်ရက် vs ဇရက်)
    <     edit-distance ratio over the phonetic keys, whichever variant scores
          higher, plus a graphemic ratio so Latin names degrade sensibly too

Falls back to a pure-Python Levenshtein when rapidfuzz is unavailable, so the
package has no hard third-party dependency.
"""

from __future__ import annotations

from .normalize import contains_myanmar, normalize_mm
from .phonetic import phonetic_key

try:                                              # pragma: no cover
    from rapidfuzz.distance import Levenshtein as _Lev
    from rapidfuzz.fuzz import partial_ratio as _partial

    def _ratio(a: str, b: str) -> float:
        return _Lev.normalized_similarity(a, b)

    def _partial_ratio(a: str, b: str) -> float:
        return _partial(a, b) / 100.0

except ImportError:                               # pragma: no cover
    def _distance(a: str, b: str) -> int:
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]

    def _ratio(a: str, b: str) -> float:
        if not a and not b:
            return 1.0
        return 1.0 - _distance(a, b) / max(len(a), len(b))

    def _partial_ratio(a: str, b: str) -> float:
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        if not short:
            return 0.0
        window = len(short)
        best = 0.0
        for i in range(max(1, len(long) - window + 1)):
            best = max(best, _ratio(short, long[i:i + window]))
        return best


class Key:
    """Pre-computed match keys for one candidate string.

    Building these once at index time keeps query-time work to string
    comparisons only.
    """

    __slots__ = ("raw", "text", "strict", "loose")

    def __init__(self, raw: str):
        self.raw = raw
        self.text = normalize_mm(raw).lower()
        self.strict = phonetic_key(self.text)
        self.loose = phonetic_key(self.text, loose=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Key({self.raw!r}, {self.strict!r})"


def _as_key(value) -> Key:
    return value if isinstance(value, Key) else Key(value)


def similarity(query, candidate, *, partial: bool = False) -> float:
    """Score how likely `query` and `candidate` are the same Burmese word.

    Returns 0.0-1.0.  Set `partial=True` to score a short query against a
    longer candidate (matching a name inside a sentence) without penalising
    the length difference.
    """
    q, c = _as_key(query), _as_key(candidate)

    if not q.strict or not c.strict:
        return 1.0 if q.text == c.text and q.text else 0.0
    if q.text == c.text:
        return 1.0
    if q.strict == c.strict:
        return 0.99
    if q.loose == c.loose:
        return 0.97

    cmp = _partial_ratio if partial else _ratio
    score = max(cmp(q.strict, c.strict), cmp(q.loose, c.loose) * 0.99)

    # Graphemic agreement is a weak signal on its own but rescues Latin names
    # and long Burmese compounds that the phonetic pass over-collapses.
    score = max(score, cmp(q.text, c.text) * 0.95)
    return round(min(score, 0.98), 4)


def rank(query, candidates, *, threshold: float = 0.72, partial: bool = False):
    """Score every candidate, returning (candidate, score) sorted best-first."""
    q = _as_key(query)
    scored = []
    for cand in candidates:
        s = similarity(q, cand, partial=partial)
        if s >= threshold:
            scored.append((cand, s))
    scored.sort(key=lambda p: -p[1])
    return scored


def best_match(query, candidates, *, threshold: float = 0.72, partial: bool = False):
    """Return the single best (candidate, score) above `threshold`, or None."""
    hits = rank(query, candidates, threshold=threshold, partial=partial)
    return hits[0] if hits else None
