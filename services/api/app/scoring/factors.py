"""The nine F2 factor functions. Pure code: no model calls, no I/O (rule R7).

Every function takes plain dicts that use the spec D3 field names and returns
`float | None`:

- a value in [0, 1] when both sides had data to compare;
- `None` when there was nothing to compare. A `None` factor drops out of the
  renormalisation in `combine.score_pair`, while `0.0` means the data disagreed.

Turning Zetaris rows into these dicts is the agents' job, not this module's.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _as_set(v: Any) -> set[str]:
    if v is None:
        return set()
    if isinstance(v, str):
        return {v.strip().lower()} if v.strip() else set()
    if isinstance(v, Iterable):
        return {str(x).strip().lower() for x in v if x is not None and str(x).strip()}
    return {str(v).strip().lower()}


def _tokens(v: Any) -> set[str]:
    """Word tokens of a string or list of strings ("black helmet red stripe" -> 4 tokens)."""
    out: set[str] = set()
    for item in _as_set(v):
        out.update(t for t in re.split(r"[^a-z0-9]+", item) if t)
    return out


def jaccard(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def time_band(ts: datetime) -> str:
    """Time-of-day band used by the MO features (night / morning / afternoon / evening)."""
    h = ts.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    return "night"


def _location(crime: Mapping[str, Any]) -> tuple[float, float] | None:
    loc = crime.get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def distance_km(a: Mapping[str, Any], b: Mapping[str, Any]) -> float | None:
    la, lb = _location(a), _location(b)
    if la is None or lb is None:
        return None
    return haversine_km(la[0], la[1], lb[0], lb[1])


def days_apart(a: Mapping[str, Any], b: Mapping[str, Any]) -> float | None:
    ta, tb = parse_ts(a.get("occurred_from")), parse_ts(b.get("occurred_from"))
    if ta is None or tb is None:
        return None
    return abs((ta - tb).total_seconds()) / 86400.0


# ---------------------------------------------------------------------------
# mo_similarity (0.25): weighted Jaccard over MO fields + cosine over MO text
# ---------------------------------------------------------------------------

# Relative importance of MO fields inside the factor (D3.2 `mo`).
MO_FIELD_WEIGHTS: Mapping[str, float] = {
    "approach": 3.0,
    "target": 2.0,
    "target_item": 2.0,
    "offender_count": 1.5,
    "escape": 1.5,
    "violence": 1.0,
    "time_band": 1.0,
    "place_type": 1.0,
    "disguise": 1.0,
    "verbal": 0.5,
}
MO_JACCARD_SHARE = 0.7  # the rest is the cosine over the MO text vector


def _mo_text_vector(features: Mapping[str, Any]) -> Counter[str]:
    mo = features.get("mo") or {}
    vec: Counter[str] = Counter()
    for key in MO_FIELD_WEIGHTS:
        for tok in _tokens(mo.get(key)):
            vec[tok] += 1
    for tok in _tokens(features.get("visual_tags")):
        vec[tok] += 1
    return vec


def cosine(a: Counter[str], b: Counter[str]) -> float | None:
    if not a or not b:
        return None
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb)


def mo_similarity(features_a: Mapping[str, Any] | None, features_b: Mapping[str, Any] | None) -> float | None:
    """Similarity of two extracted MO records (D3.2)."""
    if not features_a or not features_b:
        return None
    mo_a, mo_b = features_a.get("mo") or {}, features_b.get("mo") or {}
    num = den = 0.0
    for key, w in MO_FIELD_WEIGHTS.items():
        va, vb = mo_a.get(key), mo_b.get(key)
        if va is None or vb is None:
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
            sim = 1.0 if va == vb else 0.0
        else:
            sim = jaccard(_as_set(va), _as_set(vb))
            if sim is None:
                continue
        num += w * sim
        den += w
    jac = num / den if den else None
    cos = cosine(_mo_text_vector(features_a), _mo_text_vector(features_b))
    if jac is None and cos is None:
        return None
    if jac is None:
        return _clip(cos)  # type: ignore[arg-type]
    if cos is None:
        return _clip(jac)
    return _clip(MO_JACCARD_SHARE * jac + (1 - MO_JACCARD_SHARE) * cos)


# ---------------------------------------------------------------------------
# space_time (0.15): exp(-d/3 km) * exp(-days/14), boosted for same time band
# ---------------------------------------------------------------------------

SPACE_SCALE_KM = 3.0
TIME_SCALE_DAYS = 14.0
SAME_BAND_BOOST = 1.2  # multiplier when both fall in the same time-of-day band; clipped to 1


def space_time(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> float | None:
    d = distance_km(crime_a, crime_b)
    days = days_apart(crime_a, crime_b)
    if d is None or days is None:
        return None
    value = math.exp(-d / SPACE_SCALE_KM) * math.exp(-days / TIME_SCALE_DAYS)
    ta, tb = parse_ts(crime_a.get("occurred_from")), parse_ts(crime_b.get("occurred_from"))
    if ta and tb and time_band(ta) == time_band(tb):
        value *= SAME_BAND_BOOST
    return _clip(value)


# ---------------------------------------------------------------------------
# vehicle (0.15): plate pattern match, or ANPR sighting near both scenes
# ---------------------------------------------------------------------------

PLATE_FULL = 1.0
PLATE_PARTIAL_MIN = 0.6
PLATE_PARTIAL_MAX = 0.9
ANPR_BOTH_SCENES = 0.85
DESCRIPTION_ONLY_CAP = 0.5  # same type/colour/make without any plate: weak evidence


def normalise_plate(p: str | None) -> str:
    """Upper-case, drop spaces and dashes; `?` stays as the unknown-character wildcard."""
    if not p:
        return ""
    return re.sub(r"[^A-Z0-9?]", "", str(p).upper())


def plate_match(a: str | None, b: str | None) -> float | None:
    """1.0 for the same full plate; 0.6-0.9 for a compatible partial; 0.0 on a conflict.

    Plates of different length are compared right-aligned (the trailing digits are the
    part witnesses and ANPR read most reliably). The partial score grows with the share
    of characters that are known on both sides and agree.
    """
    pa, pb = normalise_plate(a), normalise_plate(b)
    if not pa or not pb:
        return None
    n = max(len(pa), len(pb))
    pa, pb = pa.rjust(n, "?"), pb.rjust(n, "?")
    known = 0
    for ca, cb in zip(pa, pb):
        if ca == "?" or cb == "?":
            continue
        if ca != cb:
            return 0.0
        known += 1
    if known == 0:
        return None
    if known == n:
        return PLATE_FULL
    return PLATE_PARTIAL_MIN + (PLATE_PARTIAL_MAX - PLATE_PARTIAL_MIN) * (known / n)


def _vehicle_description_match(va: Mapping[str, Any], vb: Mapping[str, Any]) -> float | None:
    parts = []
    for key in ("type", "colour", "make_model"):
        x, y = va.get(key), vb.get(key)
        if x and y:
            parts.append(1.0 if str(x).strip().lower() == str(y).strip().lower() else 0.0)
    if not parts:
        return None
    return DESCRIPTION_ONLY_CAP * sum(parts) / len(parts)


def vehicle(
    crime_a: Mapping[str, Any],
    crime_b: Mapping[str, Any],
    anpr_sightings: Sequence[Mapping[str, Any]] | None = None,
) -> float | None:
    """Best plate match between the two crimes' offender vehicles (D3.1 `vehicles`).

    `anpr_sightings` are rows from `q_vehicle_trail`, each with `plate_text` and the
    `crime_id` whose scene it was read near. A plate read near both scenes scores
    ANPR_BOTH_SCENES (or the plate score, if higher).
    """
    vas = [v for v in crime_a.get("vehicles") or [] if v.get("role", "used_by_offender") == "used_by_offender"]
    vbs = [v for v in crime_b.get("vehicles") or [] if v.get("role", "used_by_offender") == "used_by_offender"]
    best: float | None = None
    for va in vas:
        for vb in vbs:
            s = plate_match(va.get("plate"), vb.get("plate"))
            if s is None:
                s = _vehicle_description_match(va, vb)
            if s is not None:
                best = s if best is None else max(best, s)

    if anpr_sightings:
        ida, idb = crime_a.get("crime_id"), crime_b.get("crime_id")
        near: dict[str, set[str]] = {}
        for row in anpr_sightings:
            plate = normalise_plate(row.get("plate_text"))
            if plate and row.get("crime_id"):
                near.setdefault(plate, set()).add(row["crime_id"])
        if any({ida, idb} <= cids for cids in near.values()):
            best = ANPR_BOTH_SCENES if best is None else max(best, ANPR_BOTH_SCENES)
    return best


# ---------------------------------------------------------------------------
# suspect_description (0.12): count, helmet/clothing, build, age band (LNK-13)
# ---------------------------------------------------------------------------

# The ONLY keys this factor reads. Protected attributes (religion, caste, community,
# ...) are never read, whatever the input contains (LNK-13).
SUSPECT_ALLOWED_KEYS: tuple[str, ...] = ("count", "helmet", "clothing", "build", "age_band")


def _age_band_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    try:
        la, ha = (int(x) for x in a.split("-"))
        lb, hb = (int(x) for x in b.split("-"))
    except ValueError:
        return 0.0
    # Overlapping or touching bands ("20-30" vs "30-40") count as half a match.
    return 0.5 if la <= hb + 1 and lb <= ha + 1 else 0.0


def _one_description(da: Mapping[str, Any], db: Mapping[str, Any]) -> float | None:
    sims: list[float] = []
    for key in SUSPECT_ALLOWED_KEYS:
        x, y = da.get(key), db.get(key)
        if x is None or y is None:
            continue
        if key == "count":
            sims.append(1.0 if int(x) == int(y) else 0.0)
        elif key == "age_band":
            sims.append(_age_band_sim(str(x), str(y)))
        elif key == "build":
            sims.append(1.0 if str(x).strip().lower() == str(y).strip().lower() else 0.0)
        else:  # helmet, clothing: token overlap
            j = jaccard(_tokens(x), _tokens(y))
            if j is not None:
                sims.append(j)
    return sum(sims) / len(sims) if sims else None


def suspect_description(
    described_a: Sequence[Mapping[str, Any]] | None,
    described_b: Sequence[Mapping[str, Any]] | None,
) -> float | None:
    """Best match between `offenders_described` entries (from statements and CCTV only)."""
    best: float | None = None
    for da in described_a or []:
        for db in described_b or []:
            s = _one_description(da, db)
            if s is not None:
                best = s if best is None else max(best, s)
    return best


# ---------------------------------------------------------------------------
# weapon_tool (0.08): same weapon or tool class
# ---------------------------------------------------------------------------

WEAPON_CLASSES: Mapping[str, tuple[str, ...]] = {
    "knife": ("knife", "blade", "sickle", "aruval", "machete", "dagger"),
    "cutter": ("cutter", "grille", "hacksaw", "plier", "crowbar", "rod", "screwdriver"),
    "ligature": ("ligature", "rope", "wire", "cord", "dupatta"),
    "fake_cab": ("fake cab", "cab", "taxi", "auto"),
    "firearm": ("gun", "pistol", "revolver", "firearm", "country-made"),
    "blunt": ("stick", "bat", "stone", "brick", "club"),
    "chemical": ("chilli", "chili", "acid", "spray", "pepper"),
}


def weapon_class(weapon: Any) -> str | None:
    if weapon is None:
        return None
    if isinstance(weapon, Mapping):
        if weapon.get("class"):
            return str(weapon["class"]).lower()
        weapon = " ".join(str(v) for v in weapon.values() if v)
    text = str(weapon).lower()
    if not text.strip():
        return None
    for cls, words in WEAPON_CLASSES.items():
        if cls in text or any(w in text for w in words):
            return cls
    return "other:" + text.strip()


def weapon_tool(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> float | None:
    """1.0 for the same weapon/tool class, 0.0 for different classes, None if either is unrecorded."""
    ca, cb = weapon_class(crime_a.get("weapon")), weapon_class(crime_b.get("weapon"))
    if ca is None or cb is None:
        return None
    return 1.0 if ca == cb else 0.0


# ---------------------------------------------------------------------------
# target_profile (0.05): same target type
# ---------------------------------------------------------------------------

def target_profile(features_a: Mapping[str, Any] | None, features_b: Mapping[str, Any] | None) -> float | None:
    """Same target type (0.7) and same target item (0.3), from the MO features."""
    if not features_a or not features_b:
        return None
    mo_a, mo_b = features_a.get("mo") or {}, features_b.get("mo") or {}
    parts: list[tuple[float, float]] = []
    for key, w in (("target", 0.7), ("target_item", 0.3)):
        x, y = mo_a.get(key), mo_b.get(key)
        if x and y:
            parts.append((w, 1.0 if str(x).lower() == str(y).lower() else 0.0))
    if not parts:
        return None
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


# ---------------------------------------------------------------------------
# forensic (0.08): fingerprint / ballistics / DNA match code
# ---------------------------------------------------------------------------

def forensic(codes_a: Iterable[str] | None, codes_b: Iterable[str] | None) -> float | None:
    """1.0 when both cases share a forensic match code, 0.0 when both have codes and none match."""
    sa, sb = _as_set(codes_a), _as_set(codes_b)
    if not sa or not sb:
        return None
    return 1.0 if sa & sb else 0.0


# ---------------------------------------------------------------------------
# corroboration (0.07): clean tips, 112 calls or news mentioning both incidents
# ---------------------------------------------------------------------------

CORROBORATION_SCALE = 2.0  # 1 item -> 0.39, 2 -> 0.63, 3 -> 0.78


def corroboration(items: Sequence[Mapping[str, Any]] | None, crime_a_id: str, crime_b_id: str) -> float | None:
    """Share of evidence that ties both incidents together.

    `items` are rows from `q_tip_corroboration`, `q_calls_near` and `q_news`, each with a
    `crime_ids` list. Only items that mention both crimes count. Tips must already be
    Tip-Guard clean. This is a positive-only factor: finding nothing is absence of
    evidence, not evidence against, so it returns None rather than 0.
    """
    n = sum(1 for it in items or [] if {crime_a_id, crime_b_id} <= set(it.get("crime_ids") or []))
    if n == 0:
        return None
    return _clip(1 - math.exp(-n / CORROBORATION_SCALE))


# ---------------------------------------------------------------------------
# offender_return (0.05): a released / history-sheeted person with this MO near both
# ---------------------------------------------------------------------------

def offender_return(
    persons_a: Iterable[Mapping[str, Any]] | None,
    persons_b: Iterable[Mapping[str, Any]] | None,
) -> float | None:
    """Rows from `q_offender_return` for each crime (`person_ref`, optional `mo_overlap` 0-1).

    A person returned for both crimes gives their MO overlap (1.0 if not given).
    Positive-only, like corroboration: no shared person returns None.
    """
    by_ref_a = {p["person_ref"]: p for p in persons_a or [] if p.get("person_ref")}
    by_ref_b = {p["person_ref"]: p for p in persons_b or [] if p.get("person_ref")}
    shared = by_ref_a.keys() & by_ref_b.keys()
    if not shared:
        return None
    best = 0.0
    for ref in shared:
        ov = [p.get("mo_overlap") for p in (by_ref_a[ref], by_ref_b[ref]) if p.get("mo_overlap") is not None]
        best = max(best, min(ov) if ov else 1.0)
    return _clip(best)
