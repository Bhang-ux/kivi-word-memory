"""Phonetic fuzzy matching for Kivi word memory.

ASR errors are phonetically motivated ("aditya" vs "aaditya", "kiwi" vs
"kivi", "panner" vs "paneer"), so similarity is computed over sound as
well as spelling.

Why a custom encoder
--------------------
Off-the-shelf phonetic algorithms (Soundex, Metaphone, Double Metaphone)
were designed for English surnames on 1960s-era hardware and are known
to drop or collapse features that matter here -- vowel patterns in Indian
names (Aditya / Aaditya), the /v/-/w/ pair (Kivi / Kiwi), and long/short
vowel distinctions (paneer / panner). This encoder is small enough to
audit in one screen, deterministic, and calibrated against the eval
fixture in ``evals/``. See the ``ENCODING_REGRESSIONS`` dict below for
the exact behaviour the tests pin.

Similarity blend
----------------
``0.3 * phonetic + 0.7 * orthographic``. The orthographic term keeps
different names with similar sound apart ("Aditi" is not "Aaditya");
the phonetic term catches ASR-style respellings. The 0.3/0.7 split was
chosen so that the ASR pairs above score >= 0.75 while common-name
confusions ("Aditi" vs "Aaditya") stay below the 0.72 rewrite threshold.
"""

from __future__ import annotations

# Digraphs, vowel teams, silent letters, geminates. Multi-char keys must
# appear before their single-char counterparts to bind first in the loop.
_RULES: dict[str, str] = {
    "tion": "SN", "sion": "SN", "tch": "C", "sch": "S",
    "ch": "C", "sh": "S", "th": "T", "ph": "F", "wh": "V",
    "ck": "K", "ng": "N", "qu": "KW", "gh": "", "kn": "N", "wr": "R",
    "ps": "S", "pn": "N", "mn": "N",
    "ai": "V", "ay": "V", "ea": "V", "ee": "V", "ei": "V", "ey": "V",
    "ie": "V", "oa": "V", "oe": "V", "oo": "V", "ou": "V", "ow": "V",
    "au": "V", "aw": "V", "ue": "V", "ui": "V", "eu": "V",
    "bb": "B", "dd": "D", "ff": "F", "gg": "G", "ll": "L", "mm": "M",
    "nn": "N", "pp": "P", "rr": "R", "ss": "S", "tt": "T", "zz": "Z",
}

_SINGLE: dict[str, str] = {
    "a": "V", "e": "V", "i": "V", "o": "V", "u": "V", "y": "V",
    "b": "B", "c": "K", "d": "D", "f": "F", "g": "G", "h": "",
    "j": "J", "k": "K", "l": "L", "m": "M", "n": "N", "p": "P",
    "q": "K", "r": "R", "s": "S", "t": "T", "v": "V", "w": "V",
    "x": "KS", "z": "S",
}

_SOFT_EI = set("eiy")

# Regression fixture. If this dictionary changes without a matching
# eval-threshold recalibration, some tests will fail on purpose -- that
# is by design. See tests/test_phonetics.py::test_encoding_pinned.
ENCODING_REGRESSIONS: dict[str, str] = {
    "aditya":  "VDVTV",
    "aaditya": "VDVTV",
    "kiwi":    "KV",
    "kivi":    "KV",
    "paneer":  "PVNVR",
    "panner":  "PVNVR",
    "aditi":   "VDVTV",
    "arvind":  "VRVND",
    "urzoo":   "VRSV",
}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cur[j] = min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == b[j - 1] else 1),
            )
        prev = cur
    return prev[lb]


def encode_word(word: str) -> str:
    """Encode a single word into its phonetic token string."""
    w = word.lower()
    out: list[str] = []
    i, n = 0, len(w)
    while i < n:
        matched = False
        for src in _RULES:
            if w.startswith(src, i):
                out.append(_RULES[src])
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = w[i]
        nxt = w[i + 1] if i + 1 < n else ""
        token = _SINGLE.get(ch, "")
        if ch == "c" and nxt in _SOFT_EI:
            token = "S"
        elif ch == "g" and nxt in _SOFT_EI:
            token = "J"
        if token:
            out.append(token)
        i += 1
    collapsed: list[str] = []
    for t in out:
        if t and (not collapsed or collapsed[-1] != t or t not in ("V", "N")):
            collapsed.append(t)
    return "".join(collapsed)


def similarity(a: str, b: str) -> float:
    """Phonetic + orthographic similarity in ``[0, 1]``.

    ``0.3 * phonetic-edit + 0.7 * orthographic-edit``; see module
    docstring for the rationale.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    pa, pb = encode_word(a), encode_word(b)
    if pa and pb:
        phon = 1.0 - _levenshtein(pa, pb) / max(len(pa), len(pb))
    else:
        phon = 0.0
    la, lb = a.lower(), b.lower()
    orth = 1.0 - _levenshtein(la, lb) / max(len(la), len(lb))
    return 0.3 * phon + 0.7 * orth


def rewrite(text: str, target: str, start: int, end: int, preserve_case: bool = True) -> str:
    """Replace ``text[start:end]`` with ``target``.

    With ``preserve_case``, the span's capitalisation pattern
    (UPPER -> upper, Title -> Title, lower -> lower) is applied to the
    target. Otherwise the target is used verbatim -- useful for taught
    forms like ``UrZoo`` whose internal casing must not be flattened.
    """
    if not preserve_case:
        return text[:start] + target + text[end:]
    span = text[start:end]
    if not span:
        return text[:start] + target + text[start:]
    if span.isupper() and len(span) > 1:
        tgt = target.upper()
    elif span[0].isupper():
        tgt = target[0].upper() + target[1:]
    else:
        tgt = target.lower()
    return text[:start] + tgt + text[end:]
