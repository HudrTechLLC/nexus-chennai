"""Hard-contradiction check for the Skeptic (WS2-13 follow-up; pre-registered in
engg/docs/eval/SKEPTIC_CONTRADICTION_PREREG.md).

The planted false-link test (#370, #392) showed that the model critique notices a stated contradiction but
never drops the pair. This module is the deterministic rule. If two crimes state DIFFERENT values for one
distinctive descriptor, the pair is a hard contradiction. Unless new evidence reconciles it, the Skeptic drops
the pair. The descriptors are:
- the offender count;
- the offender age band, with no overlap;
- the helmet;
- the offender's vehicle: colour, make or partial plate.

"Different" is deliberately narrow. Missing or unknown values never contradict. Free text is compared by its
content words, so less detail is not a contradiction: "Bajaj Pulsar" is compatible with "Bajaj Pulsar 150",
and "black with red stripe" with "black helmet with red stripe". When a crime describes several offenders, a
field contradicts only if NO pair of entries is compatible.

Reconciliation: physical or identity evidence outranks witness descriptions. A forensic match or a known
offender returning (the `offender_return` factor) reconciles the pair, provided the Skeptic's own re-check
confirmed it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# Factors whose Skeptic-confirmed value reconciles a contradiction between witness descriptions.
RECONCILING_FACTORS = ("forensic", "offender_return")
RECONCILE_MIN = 0.5  # a reconciling factor must be confirmed at >= this value (not struck)

UNKNOWN = {"", "unknown", "not seen", "not known", "unclear", "unidentified", "n/a", "na", "none recorded", "nil",
           "not noted", "not stated"}
NEGATED = {"no helmet", "without helmet", "without a helmet", "no", "none", "bare head", "bareheaded"}
FILLER = {"a", "an", "the", "with", "and", "helmet", "helmets", "colour", "color", "coloured", "colored", "of",
          "in", "on", "type", "model", "bike", "motorcycle", "scooter", "two", "wheeler", "two-wheeler", "vehicle"}
COLOUR_ALIASES = {"gray": "grey", "silver grey": "silver", "maroon red": "maroon", "golden": "gold", "navy": "blue",
                  "navy blue": "blue", "dark blue": "blue", "light blue": "blue", "sky blue": "blue",
                  "dark red": "red", "wine": "maroon", "off white": "white", "off-white": "white"}


def _norm(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip().lower())


def _known(x: Any) -> bool:
    return _norm(x) not in UNKNOWN


def _words(x: Any) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", _norm(x)) if w not in FILLER)


def _negated(x: Any) -> bool:
    n = _norm(x)
    return n in NEGATED or n.startswith(("no ", "without "))


def text_compatible(x: Any, y: Any) -> bool:
    """True unless both are stated and say different things. Less detail is compatible."""
    if not _known(x) or not _known(y):
        return True
    if _negated(x) or _negated(y):
        return _negated(x) == _negated(y)
    wx, wy = _words(x), _words(y)
    if not wx or not wy:
        return True
    return wx <= wy or wy <= wx


def colour_compatible(x: Any, y: Any) -> bool:
    if not _known(x) or not _known(y):
        return True
    cx, cy = COLOUR_ALIASES.get(_norm(x), _norm(x)), COLOUR_ALIASES.get(_norm(y), _norm(y))
    return text_compatible(cx, cy)


def band(x: Any) -> tuple[int, int] | None:
    nums = [int(n) for n in re.findall(r"\d+", str(x or ""))]
    if not nums:
        return None
    return (nums[0], nums[-1]) if nums[0] <= nums[-1] else (nums[-1], nums[0])


def age_compatible(x: Any, y: Any) -> bool:
    bx, by = band(x), band(y)
    if bx is None or by is None:
        return True
    return not (bx[1] < by[0] or by[1] < bx[0])


def count_compatible(x: Any, y: Any) -> bool:
    if not isinstance(x, int) or not isinstance(y, int) or isinstance(x, bool) or isinstance(y, bool):
        return True
    return x <= 0 or y <= 0 or x == y


def plate_compatible(x: Any, y: Any) -> bool:
    """Partial plates ('?' = unread), right-aligned. Two or more positions read in both, and any of them
    differing, is a conflict."""
    a = re.sub(r"[^A-Z0-9?]", "", str(x or "").upper())
    b = re.sub(r"[^A-Z0-9?]", "", str(y or "").upper())
    if not a or not b:
        return True
    n = min(len(a), len(b))
    known = [(p, q) for p, q in zip(a[-n:], b[-n:]) if p != "?" and q != "?"]
    return len(known) < 2 or all(p == q for p, q in known)


# ---------------------------------------------------------------------------------------------------------


def _offenders(c: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [o for o in (c.get("offenders_described") or []) if isinstance(o, Mapping)]


def _vehicles(c: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [v for v in (c.get("vehicles") or [])
            if isinstance(v, Mapping) and (v.get("role") or "used_by_offender") == "used_by_offender"]


def _field_conflict(xs: Sequence[Mapping[str, Any]], ys: Sequence[Mapping[str, Any]], key: str, ok) -> tuple[Any, Any] | None:
    """A conflict only if both sides state the field and no pair of entries is compatible."""
    xv = [x.get(key) for x in xs if x.get(key) is not None]
    yv = [y.get(key) for y in ys if y.get(key) is not None]
    if not xv or not yv:
        return None
    if any(ok(p, q) for p in xv for q in yv):
        return None
    return xv[0], yv[0]


def contradictions(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Hard contradictions between two crimes' stated descriptors. Empty list = none."""
    out: list[dict[str, Any]] = []
    oa, ob = _offenders(a), _offenders(b)
    for kind, key, ok in (("offender_count", "count", count_compatible),
                          ("offender_age", "age_band", age_compatible),
                          ("helmet", "helmet", text_compatible)):
        hit = _field_conflict(oa, ob, key, ok)
        if hit:
            out.append({"kind": kind, "field": key, "a": hit[0], "b": hit[1]})
    va, vb = _vehicles(a), _vehicles(b)
    for key, ok in (("colour", colour_compatible), ("make_model", text_compatible), ("plate", plate_compatible)):
        hit = _field_conflict(va, vb, key, ok)
        if hit:
            out.append({"kind": "vehicle_identity", "field": key, "a": hit[0], "b": hit[1]})
    return out


def reconciled_by(rechecked: Mapping[str, float | None], struck: Iterable[str]) -> list[str]:
    """Reconciling factors the Skeptic itself confirmed (re-checked value >= RECONCILE_MIN, not struck)."""
    gone = set(struck)
    return [f for f in RECONCILING_FACTORS
            if f not in gone and (rechecked.get(f) or 0) >= RECONCILE_MIN]


def describe(items: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(f"{i['kind']} ({i['field']}): '{i['a']}' vs '{i['b']}'" for i in items)
