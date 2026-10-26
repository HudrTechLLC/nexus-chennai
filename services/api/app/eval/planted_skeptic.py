"""Planted false-link test for the Skeptic (pre-registered: engg/docs/eval/PLANTED_SKEPTIC_PREREG.md).

Paired design. Each case is a true series pair from the sample ground truth (data/sample/_truth/pairs.csv) that
the Linker alerts on. Its NEAR-MISS twin is the same pair with exactly ONE planted false fact in crime B (a different
vehicle colour, vehicle make, offender count, offender age band or helmet, or a time that makes the same offenders
impossible). The fact is rewritten everywhere it appears in B (structured fields, visual tags, MO fields, narrative
and statements), so B stays internally consistent and only conflicts with A.

What is measured: `Skeptic.review` called directly, round 1, on the pair as the Linker scored it (the Skeptic only
ever sees pairs above threshold, so pairs are fed to its function rather than through the graph). The Skeptic's code
re-check re-reads the same planted rows, so it cannot strike anything by construction; every rejection comes from the
model critique. H-MEM and the World Model are off (engines=None), each pair gets its own Linker rationale and critique
call (one pair per call), the pair support comes from the Planner's deterministic default plan.

    python -m app.eval.planted_skeptic prepare --out engg/docs/eval/planted_skeptic_cases.json   # code only
    python -m app.eval.planted_skeptic run --cases engg/docs/eval/planted_skeptic_cases.json \
        --expect-sha <sha256 from the prereg> --out output_examples/planted_skeptic.json        # live Ultra

Data: sample mode (DuckDB twins of the Zetaris views). No Supabase, no alerts, no notifications, no fixtures recorded.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT, Settings, get_settings
from ..scoring.factors import distance_km

# =====================
# Population
# =====================

TRUTH = REPO_ROOT / "data" / "sample" / "_truth" / "pairs.csv"
# Never used (chief, 2026-10-27): the hero pair, C802 (LA-2026-C802D4F2E02B = AD-001182 + AD-001231), the held cases,
# plus every crime id that appears in the judge inputs or outputs (read from the files at run time).
PROTECTED = frozenset({"CHN-AD-2026-001182", "CHN-VL-2026-000877", "CHN-AD-2026-001231",
                       "CHN-CM-2025-000450", "CHN-TU-2025-000437"})
_CRIME_ID = re.compile(r"CHN-[A-Z]{2}-\d{4}-\d{6}")
# vehicle_identity = a DIFFERENT vehicle: its colour or its make (alternating) AND its partial plate digits differ, in
# every place B states them and in B's ANPR trail reads (nexus-5 review: a colour-only plant leaves the same plate).
PLANT_KINDS = ("vehicle_identity", "offender_count", "offender_age", "helmet", "simultaneous")
VEHICLE_VARIANTS = ("colour", "make")
SERIES = REPO_ROOT / "data" / "sample" / "_truth" / "series.json"
MIN_KM_SIMULTANEOUS = 5.0


def judge_ids(root: Path = REPO_ROOT) -> set[str]:
    ids: set[str] = set()
    for f in [*root.glob("input_examples/*.json"), *root.glob("output_examples/example_*.json")]:
        ids |= set(_CRIME_ID.findall(f.read_text(encoding="utf-8")))
    return ids


def excluded_ids(root: Path = REPO_ROOT) -> set[str]:
    return set(PROTECTED) | judge_ids(root)


def eligible_pairs(truth: Path = TRUTH, excluded: set[str] | None = None) -> list[tuple[str, str, str]]:
    """(crime_a, crime_b, group_id) for every ground-truth SERIES pair with neither crime excluded, in file order."""
    ex = excluded_ids() if excluded is None else excluded
    with truth.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [(r["crime_a"], r["crime_b"], r["group_id"]) for r in rows
            if r["label"] == "series" and r["crime_a"] not in ex and r["crime_b"] not in ex]


# =====================
# Plants
# =====================

COLOUR_SWAP = {"red": "blue", "silver": "black", "maroon": "white", "grey": "yellow", "black": "silver",
               "white": "maroon", "blue": "red", "yellow": "grey"}
MAKE_SWAP = {"Bajaj Pulsar 150": "Hero Splendor Plus", "TVS Apache": "Royal Enfield Classic",
             "Honda Shine": "Hero HF Deluxe", "Honda Activa": "Suzuki Access", "Yamaha FZ": "Bajaj Platina"}
# 2 -> 1, not 2 -> 4: four people on one two-wheeler would make B implausible on its own (not a near-miss).
COUNT_SWAP = {1: 2, 2: 1, 3: 1, 4: 2}
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}
AGE_SWAP = {"18-20": "40-50", "20-30": "50-60", "30-40": "60-70", "40-50": "18-20", "50-60": "20-30"}
# helmet value -> (new value, [(old text form, new text form), ...]); text forms cover narrative/statements/tags.
HELMET_SWAP = {
    "black with red stripe": ("plain yellow", [("black helmet with red stripe", "plain yellow helmet")]),
    "grey with sticker": ("blue full-face", [("grey helmet with sticker", "blue full-face helmet")]),
    "no helmet": ("white full-face", [("no helmet", "a white full-face helmet")]),
    "white full-face": ("black with green stripe", [("white full-face helmet", "black helmet with green stripe")]),
}
PLURAL_TO_SINGULAR = {"men": "man", "persons": "person", "people": "person", "youths": "youth", "riders": "rider",
                      "boys": "boy", "offenders": "offender"}
_SKIP_KEYS = frozenset({"crime_id", "source_row_id", "statement_id", "fir_no", "h3_r9", "h3_r8", "geohash7",
                        "sections", "station_id", "evidence_id", "storage_path", "receipt_id", "model", "plates",
                        "plate", "witness_ref"})


def _case_preserving(new: str) -> Callable[[re.Match], str]:
    def sub(m: re.Match) -> str:
        old = m.group(0)
        if old.isupper():
            return new.upper()
        if old[:1].isupper():
            return new[:1].upper() + new[1:]
        return new.lower() if old.islower() else new
    return sub


def _token(text: str) -> str:
    """A phrase as a regex that also matches its snake_case tag form, on word boundaries (underscore counts)."""
    words = [re.escape(w) for w in text.split()]
    return r"(?<![A-Za-z0-9])" + r"[ _]".join(words) + r"(?![A-Za-z0-9])"


def _sub_strings(obj: Any, rules: list[tuple[str, str]], key: str | None = None) -> Any:
    """Apply (regex, replacement-phrase) rules to every string in obj, skipping id-like keys. Tag forms keep `_`."""
    if key in _SKIP_KEYS:
        return obj
    if isinstance(obj, dict):
        return {k: _sub_strings(v, rules, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sub_strings(v, rules, key) for v in obj]
    if isinstance(obj, str):
        s = obj
        for pat, new in rules:
            def rep(m: re.Match, new: str = new) -> str:
                out = _case_preserving(new)(m)
                return out.replace(" ", "_") if "_" in m.group(0) and " " not in m.group(0) else out
            s = re.sub(pat, rep, s, flags=re.IGNORECASE)
        return s
    return obj


def _count_text(obj: Any, old: int, new: int, key: str | None = None) -> Any:
    """'two unknown persons' -> 'one unknown person', 'I saw two men' -> 'I saw one man', tag 'two_unknown_persons'."""
    if key in _SKIP_KEYS:
        return obj
    if isinstance(obj, dict):
        return {k: _count_text(v, old, new, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_count_text(v, old, new, key) for v in obj]
    if not isinstance(obj, str):
        return obj
    nouns = "|".join(PLURAL_TO_SINGULAR) if new == 1 else "|".join(PLURAL_TO_SINGULAR.values())
    pat = (r"(?<![A-Za-z0-9])(" + NUMBER_WORDS[old] + r")([ _])((?:unknown[ _])?)(" + nouns + r")(?![A-Za-z0-9])")

    def rep(m: re.Match) -> str:
        noun = m.group(4).lower()
        if new == 1:
            noun = PLURAL_TO_SINGULAR.get(noun, noun)
        elif old == 1:
            noun = {v: k for k, v in PLURAL_TO_SINGULAR.items()}.get(noun, noun)
        word = _case_preserving(NUMBER_WORDS[new])(re.match(r".*", m.group(1)))
        return f"{word}{m.group(2)}{m.group(3)}{noun}"
    return re.sub(pat, rep, obj, flags=re.IGNORECASE)


_ID_KEYS = frozenset({"crime_id", "source_row_id", "statement_id", "fir_no", "read_id", "camera_id", "evidence_id",
                      "storage_path", "receipt_id", "witness_ref", "h3_r9", "h3_r8", "geohash7"})


def _sub_digits(obj: Any, old: str, new: str, key: str | None = None) -> Any:
    """The plate's last digits, everywhere B states them (plate fields included); never inside ids."""
    if key in _ID_KEYS:
        return obj
    if isinstance(obj, dict):
        return {k: _sub_digits(v, old, new, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sub_digits(v, old, new, key) for v in obj]
    if isinstance(obj, str):
        return re.sub(r"(?<![0-9])" + re.escape(old) + r"(?![0-9])", new, obj)
    return obj


def plate_digits(v: Mapping[str, Any] | None) -> str | None:
    m = re.search(r"(\d{4})$", str((v or {}).get("plate") or ""))
    return m.group(1) if m else None


def new_digits(d: str) -> str:
    return f"{(int(d) + 5317) % 10000:04d}"


def truth_features() -> dict[str, dict[str, Any]]:
    """Features for crimes with none stored: the generator's ground-truth MO for their series (no extraction, no
    model call). Marked source=generator_truth in the case file; visual tags are empty."""
    out: dict[str, dict[str, Any]] = {}
    for ser in json.loads(SERIES.read_text(encoding="utf-8")):
        mo = dict((ser.get("true_mo") or {}).get("mo") or {})
        for cid in ser.get("crime_ids") or []:
            out[cid] = {"crime_id": cid, "mo": mo, "visual_tags": [], "entities": {"persons": [], "phones": [],
                                                                                  "plates": []},
                        "extractor_version": "generator_truth"}
    return out


def _vehicle(c: Mapping[str, Any]) -> Mapping[str, Any] | None:
    vs = [v for v in c.get("vehicles") or [] if isinstance(v, Mapping)]
    return vs[0] if vs else None


def _offender(c: Mapping[str, Any]) -> Mapping[str, Any] | None:
    ds = [d for d in c.get("offenders_described") or [] if isinstance(d, Mapping)]
    return ds[0] if ds else None


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(str(ts).replace(" ", "T"))


@dataclass(frozen=True)
class Plant:
    kind: str
    crime_id: str           # the crime the plant rewrites (always the pair's crime B)
    old: Any
    new: Any
    detail: str             # one line for the case file: what a reader should see as false

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "crime_id": self.crime_id, "old": self.old, "new": self.new, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Plant:
        return cls(d["kind"], d["crime_id"], d["old"], d["new"], d["detail"])


def choose_plant(kind: str, a: Mapping[str, Any], b: Mapping[str, Any], fa: Mapping[str, Any] | None,
                 variant: str = "colour") -> Plant | None:
    """The plant of `kind` for pair (a, b), or None when it doesn't apply (the fact must be shared by A and B)."""
    va, vb, oa, ob = _vehicle(a), _vehicle(b), _offender(a), _offender(b)
    bid = b["crime_id"]
    if kind == "vehicle_identity" and va and vb:
        # Plates must agree: both read the same digits (they are planted too) or neither has a plate. One plate missing,
        # or two different plates, is not a clean single-fact near-miss.
        da, db = plate_digits(va), plate_digits(vb)
        if da != db or bool(va.get("plate")) != bool(vb.get("plate")) or (va.get("plate") and not da):
            return None
        nd = new_digits(db) if db else None
        tail = (lambda d: f", plate ending {d}") if db else (lambda d: "")
        if variant == "colour" and va.get("colour") and va.get("colour") == vb.get("colour") \
                and COLOUR_SWAP.get(str(vb["colour"]).lower()):
            new = COLOUR_SWAP[str(vb["colour"]).lower()]
            return Plant(kind, bid, {"colour": vb["colour"], "plate_digits": db}, {"colour": new, "plate_digits": nd},
                         f"B's vehicle is {new}{tail(nd)}; A's is {vb['colour']}{tail(db)}")
        if variant == "make" and va.get("make_model") and va.get("make_model") == vb.get("make_model") \
                and MAKE_SWAP.get(vb["make_model"]):
            new = MAKE_SWAP[vb["make_model"]]
            return Plant(kind, bid, {"make_model": vb["make_model"], "plate_digits": db},
                         {"make_model": new, "plate_digits": nd},
                         f"B's vehicle is a {new}{tail(nd)}; A's a {vb['make_model']}{tail(db)}")
        return None
    if kind == "offender_count" and oa and ob and oa.get("count") and oa.get("count") == ob.get("count"):
        new = COUNT_SWAP.get(int(ob["count"]))
        return new and Plant(kind, bid, int(ob["count"]), new, f"B had {new} offenders, A had {ob['count']}")
    if kind == "offender_age" and oa and ob and oa.get("age_band") and oa.get("age_band") == ob.get("age_band"):
        new = AGE_SWAP.get(ob["age_band"])
        return new and Plant(kind, bid, ob["age_band"], new, f"B's offenders aged {new}, A's {ob['age_band']}")
    if kind == "helmet" and oa and ob and oa.get("helmet") and oa.get("helmet") == ob.get("helmet"):
        new = HELMET_SWAP.get(ob["helmet"])
        return new and Plant(kind, bid, ob["helmet"], new[0], f"B's rider wore {new[0]}, A's {ob['helmet']}")
    if kind == "simultaneous":
        km = distance_km(a, b)
        if km is None or km < MIN_KM_SIMULTANEOUS or not a.get("occurred_from") or not b.get("occurred_from"):
            return None
        t = (_parse(a["occurred_from"]) + timedelta(minutes=2)).isoformat()
        band = (fa or {}).get("mo", {}).get("time_band") if fa else None
        return Plant(kind, bid, b["occurred_from"], {"occurred_from": t, "time_band": band},
                     f"B happened 2 min after A, {km:.1f} km away: the same offenders cannot do both")
    return None


def apply_plant(plant: Plant, crime: dict[str, Any], features: dict[str, Any] | None
                ) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """B's crime row and features with the planted fact rewritten everywhere it appears. Pure."""
    c, f = copy.deepcopy(crime), copy.deepcopy(features)
    k = plant.kind
    if k == "vehicle_identity":
        if "colour" in plant.old:
            # Only the colour word right before a vehicle word: "red Bajaj Pulsar", "red_motorcycle". Never the
            # helmet's "black with red stripe" (that would be a second planted fact).
            make = (_vehicle(c) or {}).get("make_model") or ""
            nouns = ["motorcycle", "bike", "scooter", "two-wheeler", "two wheeler", "vehicle", "car",
                     *([make] if make else [])]
            after = "|".join(r"[ _]".join(re.escape(w) for w in n.split()) for n in nouns)
            old_c, new_c = plant.old["colour"], plant.new["colour"]
            rules = [(r"(?<![A-Za-z0-9])" + re.escape(old_c) + r"(?=[ _](?:" + after + r")(?![A-Za-z0-9]))", new_c)]
            c, f = _sub_strings(c, rules), _sub_strings(f, rules)
            for v in c.get("vehicles") or []:
                if isinstance(v, dict) and v.get("colour") == old_c:
                    v["colour"] = new_c
        else:
            old_m, new_m = plant.old["make_model"], plant.new["make_model"]
            old_words, new_words = old_m.split(), new_m.split()
            rules = [(_token(old_m), new_m),
                     # the model name alone ("it looked like a pulsar") -> the new model name
                     (_token(" ".join(old_words[1:])), " ".join(new_words[1:]))]
            c, f = _sub_strings(c, rules), _sub_strings(f, rules)
            for v in c.get("vehicles") or []:
                if isinstance(v, dict) and v.get("make_model") in (old_m, new_m):
                    v["make_model"] = new_m
        if plant.old.get("plate_digits"):
            c = _sub_digits(c, plant.old["plate_digits"], plant.new["plate_digits"])
            f = _sub_digits(f, plant.old["plate_digits"], plant.new["plate_digits"])
    elif k == "offender_count":
        c, f = _count_text(c, plant.old, plant.new), _count_text(f, plant.old, plant.new)
        for d in c.get("offenders_described") or []:
            if isinstance(d, dict) and d.get("count") == plant.old:
                d["count"] = plant.new
        for mo in [(f or {}).get("mo"), (c.get("features") or {}).get("mo")]:
            if isinstance(mo, dict) and mo.get("offender_count") == plant.old:
                mo["offender_count"] = plant.new
    elif k == "offender_age":
        lo_o, hi_o = plant.old.split("-")
        lo_n, hi_n = plant.new.split("-")
        # The offenders' range phrase only ("aged about 20 to 30"); a victim is "aged about 45" and must not change.
        rules = [(r"aged about " + lo_o + r" to " + hi_o + r"(?![0-9])", f"aged about {lo_n} to {hi_n}")]
        c, f = _sub_strings(c, rules), _sub_strings(f, rules)
        for d in c.get("offenders_described") or []:
            if isinstance(d, dict) and d.get("age_band") == plant.old:
                d["age_band"] = plant.new
    elif k == "helmet":
        new_value, forms = HELMET_SWAP[plant.old]
        # The structured field first: the text rule for "no helmet" would otherwise rewrite the field's own value.
        for d in c.get("offenders_described") or []:
            if isinstance(d, dict) and d.get("helmet") == plant.old:
                d["helmet"] = new_value
        rules = [(_token(o), n) for o, n in forms]
        protected = [d.get("helmet") for d in c.get("offenders_described") or [] if isinstance(d, dict)]
        c, f = _sub_strings(c, rules), _sub_strings(f, rules)
        for d, h in zip([d for d in c.get("offenders_described") or [] if isinstance(d, dict)], protected):
            d["helmet"] = h
    elif k == "simultaneous":
        old_t, new_t = _parse(plant.old), _parse(plant.new["occurred_from"])
        delta = new_t - old_t
        for key in ("occurred_from", "occurred_to", "reported_at"):
            if c.get(key):
                c[key] = (_parse(c[key]) + delta).isoformat()
        for st in c.get("statements") or []:
            if isinstance(st, dict) and st.get("recorded_at"):
                st["recorded_at"] = (_parse(st["recorded_at"]) + delta).isoformat()
        iso = new_t.isocalendar()
        c["week"] = f"{iso[0]}-W{iso[1]:02d}"
        old_date, new_date = old_t.strftime("%d-%m-%Y"), new_t.strftime("%d-%m-%Y")
        old_hm, new_hm = old_t.strftime("%H:%M"), new_t.strftime("%H:%M")
        rules = [(re.escape(old_date), new_date), (r"(?<![0-9])" + re.escape(old_hm) + r"(?![0-9])", new_hm)]
        c = _sub_strings(c, rules)
        band = plant.new.get("time_band")
        for mo in [(f or {}).get("mo"), (c.get("features") or {}).get("mo")]:
            if isinstance(mo, dict) and band:
                mo["time_band"] = band
    else:
        raise ValueError(f"unknown plant kind {k}")
    if isinstance(c.get("features"), dict) and f is not None:
        c["features"] = {**c["features"], **{kk: f[kk] for kk in ("mo", "visual_tags", "entities") if kk in f}}
    return c, f


# =====================
# Overlay: every read of B returns the planted rows (Linker inputs and the Skeptic's own re-query alike)
# =====================


class _Rows:
    def __init__(self, res: Any, rows: list[dict[str, Any]]) -> None:
        self.name, self.query_id, self._rows = res.name, res.query_id, rows

    def dicts(self) -> list[dict[str, Any]]:
        return self._rows


class PlantedZetaris:
    """Wraps the sample ZetarisClient: q_case / q_cases / q_features rows for the planted crime come back planted."""

    CASE_QUERIES = ("q_case", "q_cases")

    def __init__(self, inner: Any, plant: Plant | None, truth: Mapping[str, dict[str, Any]] | None = None) -> None:
        self.inner, self.plant = inner, plant
        self.truth = truth_features() if truth is None else truth

    def named(self, name: str, *, agent: str, **params: Any) -> Any:
        res = self.inner.named(name, agent=agent, **params)
        if name not in (*self.CASE_QUERIES, "q_features", "q_vehicle_trail"):
            return res
        from ..agents.base import crime_from_row, features_from_row, rows_as_dicts

        rows = rows_as_dicts(res)
        if name == "q_features":  # crimes with no stored features get their series' generator-truth MO
            have = {r.get("crime_id") for r in rows}
            rows += [dict(self.truth[i]) for i in str(params.get("ids") or "").split(",")
                     if i and i not in have and i in self.truth]
        if self.plant is None:
            return _Rows(res, rows)
        out = []
        for row in rows:
            if row.get("crime_id") != self.plant.crime_id:
                out.append(row)
            elif name == "q_vehicle_trail":  # B's ANPR reads show B's (planted) plate
                if self.plant.kind == "vehicle_identity" and self.plant.old.get("plate_digits"):
                    row = _sub_digits(row, self.plant.old["plate_digits"], self.plant.new["plate_digits"])
                out.append(row)
            elif name == "q_features":
                _, f = apply_plant(self.plant, {"crime_id": self.plant.crime_id}, features_from_row(row))
                out.append({**row, **(f or {})})
            else:
                c, _ = apply_plant(self.plant, crime_from_row(row), None)
                out.append({**row, **c})
        return _Rows(res, out)

    def close(self) -> None:
        self.inner.close()


# =====================
# Scoring and review
# =====================


def _deps(settings: Settings, run_id: str, plant: Plant | None, nightshift: Any = None) -> Any:
    from ..adapters.zetaris import ZetarisClient
    from ..agents import AgentDeps, MemoryStore
    from ..tracing import Tracer

    tracer = Tracer(run_id, settings.logs_dir, echo=False)
    z = PlantedZetaris(ZetarisClient(settings, tracer), plant)
    return AgentDeps(tracer=tracer, zetaris=z, nightshift=nightshift, engines=None, store=MemoryStore())


def score_pair(deps: Any, a_id: str, b_id: str) -> Any:
    """The Linker's ScoredPair for (a, b), support from the Planner's default plan. Code only, no model call."""
    from ..agents.base import crime_from_row, features_from_row
    from ..agents.linker import Candidate, Linker
    from ..agents.planner import Plan, Planner, default_plan

    def load(cid: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        rows, _ = deps.query("q_case", agent="Eval", crime_id=cid)
        feats, _ = deps.query("q_features", agent="Eval", ids=cid)
        return crime_from_row(rows[0]), (features_from_row(feats[0]) if feats else None)

    a, fa = load(a_id)
    b, fb = load(b_id)
    support = Planner(deps).execute(Plan(default_plan(a, fa), 1, "default", ["planted-skeptic eval"]))
    pairs = Linker(deps).score(a, fa, [Candidate(b, fb)], support)
    return pairs[0], (a, fa, b, fb)


PLANTS_PER_BASE = 3


def prepare(settings: Settings) -> dict[str, Any]:
    """The pre-registered case list. Deterministic, code only.

    Base pairs (TWINS, unaltered): ground-truth series pairs that the Linker alerts on, chosen per series in file order
    so that no crime is used twice (the widest set of distinct crimes). Each twin gets PLANTS_PER_BASE near-misses,
    each with one different planted fact; kinds follow a fixed rotation over the kinds that apply to the pair and are
    never retried, and the vehicle plant alternates colour / make. Planted pairs the Linker already stops never reach
    the Skeptic: they are listed (`reaches_skeptic: false`) and not run."""
    pool = eligible_pairs()
    truth = truth_features()
    bases, skipped, used = [], [], set()
    slot = vehicle_n = 0
    for a_id, b_id, group in pool:
        if a_id in used or b_id in used:
            skipped.append({"a": a_id, "b": b_id, "group": group, "why": "a crime is already used by another twin"})
            continue
        base, (a, fa, b, fb) = score_pair(_deps(settings, "planted-prep", None), a_id, b_id)
        if fa is None or fb is None:
            skipped.append({"a": a_id, "b": b_id, "group": group, "why": "no features (stored or generator truth)"})
            continue
        if not base.score.alert:
            skipped.append({"a": a_id, "b": b_id, "group": group,
                            "why": f"base pair does not alert (score {base.score.score})"})
            continue
        applicable = [k for k in PLANT_KINDS
                      if any(choose_plant(k, a, b, fa, v) for v in VEHICLE_VARIANTS)]
        if len(applicable) < PLANTS_PER_BASE:
            skipped.append({"a": a_id, "b": b_id, "group": group, "why": f"only {applicable} apply"})
            continue
        used |= {a_id, b_id}
        case_id = f"PS-{len(bases) + 1:02d}"
        near = []
        for n in range(PLANTS_PER_BASE):
            kind = applicable[(slot + n) % len(applicable)]
            plant = None
            if kind == "vehicle_identity":
                for k in range(len(VEHICLE_VARIANTS)):  # alternate; fall back to the other variant only if n/a
                    plant = choose_plant(kind, a, b, fa, VEHICLE_VARIANTS[(vehicle_n + k) % len(VEHICLE_VARIANTS)])
                    if plant:
                        break
                vehicle_n += 1
            else:
                plant = choose_plant(kind, a, b, fa)
            planted, _ = score_pair(_deps(settings, "planted-prep", plant), a_id, b_id)
            near.append({"near_miss_id": f"{case_id}{'abc'[n]}", "plant": plant.to_dict(),
                         "planted_score": planted.score.score, "planted_band": planted.score.band,
                         "reaches_skeptic": bool(planted.score.alert), "expected": "reject (drop)"})
        slot += PLANTS_PER_BASE
        src = {cid: ("stored" if cid not in truth or (f or {}).get("extractor_version") != "generator_truth"
                     else "generator_truth") for cid, f in ((a_id, fa), (b_id, fb))}
        bases.append({"case_id": case_id, "a": a_id, "b": b_id, "group": group, "category": b.get("sub_type"),
                      "features_source": src, "twin_score": base.score.score, "twin_band": base.score.band,
                      "twin_expected": "approve", "near_misses": near})
    return {"version": 3, "population": "data/sample/_truth/pairs.csv label=series; protected and judge crimes "
                                         "excluded; one twin per crime (no crime reused); features stored, else the "
                                         "series' generator-truth MO",
            "excluded": sorted(excluded_ids()), "plant_kinds": list(PLANT_KINDS),
            "vehicle_variants": list(VEHICLE_VARIANTS), "plants_per_base": PLANTS_PER_BASE,
            "cases": bases, "skipped": skipped}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guard(settings: Settings) -> None:
    """Step 2 safety: sample data, live Nightshift, nothing written anywhere shared."""
    bad = [k for k in ("NEXUS_RECORD_FIXTURES", "ENGINES_PERSIST", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                       "SUPABASE_SERVICE_ROLE_KEY_FILE", "ZETARIS_API_KEY", "ZETARIS_API_KEY_FILE") if os.environ.get(k)]
    if bad:
        sys.exit(f"refusing to run: unset {bad} (sample data, memory store, no fixture recording)")
    # The RESOLVED settings too: .env and *_FILE paths load keys the environment check above cannot see, and with a
    # Zetaris key set, sample mode queries live Zetaris (nexus-5 review).
    loaded = [k for k in ("zetaris_api_key", "supabase_url", "supabase_service_role_key") if getattr(settings, k, "")]
    if loaded:
        sys.exit(f"refusing to run: settings resolve {loaded} (from .env or a *_FILE); clear them")
    if not settings.sample_mode:
        sys.exit("refusing to run: SAMPLE_MODE must be true (DuckDB twins, no Zetaris load)")
    if os.environ.get("NEXUS_STORE", "memory") != "memory" or (settings.nexus_store or "memory") != "memory":
        sys.exit("refusing to run: NEXUS_STORE must be memory")
    if not (settings.meterless_runtime_token or "").strip():
        sys.exit("refusing to run: no Nightshift token (the critique must be a live call, not a replay)")


def review_case(settings: Settings, case: Mapping[str, Any], near: Mapping[str, Any] | None, run_id: str
                ) -> dict[str, Any]:
    """One arm: the twin (near=None) or one near-miss. Its own trace, so only its own model calls are reported."""
    from ..adapters.nightshift import NightshiftClient
    from ..agents.linker import Linker, factor_payload
    from ..agents.skeptic import Skeptic

    arm_id = near["near_miss_id"] if near else case["case_id"]
    plant = Plant.from_dict(near["plant"]) if near else None
    deps = _deps(settings, f"{run_id}-{arm_id}", plant)
    deps.nightshift = NightshiftClient(settings, deps.tracer, record_fixtures=False)
    sp, _ = score_pair(deps, case["a"], case["b"])
    out: dict[str, Any] = {"case_id": case["case_id"], "id": arm_id, "arm": "planted" if near else "twin",
                           "plant_kind": near["plant"]["kind"] if near else None,
                           "features_source": features_source(case),
                           "score": sp.score.score, "band": sp.score.band, "alert": sp.score.alert}
    if not sp.score.alert:  # cannot happen for a pre-registered arm; recorded, never silently skipped
        out.update(verdict="not_alerting")
        return out
    Linker(deps).explain([sp])
    res = Skeptic(deps).review([sp], round_no=1, critique=True)[0]
    calls = [e for e in deps.tracer.read() if e["action"] == "model_call"]
    out.update(verdict=res.verdict, critique=res.critique, model_critique=res.model_critique, struck=res.struck,
               rationale=sp.rationale, payload_b=factor_payload(sp)["b"],
               model_calls=[{"purpose": e["input_summary"], "model": e.get("model"), "routed": e.get("routed_model"),
                             "receipt": e.get("receipt_id"), "status": e["status"]} for e in calls])
    deps.zetaris.close()
    deps.nightshift.close()
    return out


def features_source(case: Mapping[str, Any]) -> str:
    """'stored' or 'generator_truth' for a twin's pair (both crimes share one source; 'mixed' if they ever don't)."""
    src = set((case.get("features_source") or {}).values())
    return src.pop() if len(src) == 1 else "mixed"


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Every metric overall and split by features_source (pre-registered, nexus-5): generator-truth MO matches
    perfectly across a series, so a planted fact stands alone against a perfect match there; stored (extracted) MO
    is noisier. The split shows whether the headline rate is carried by one source."""
    out = _metrics(results)
    out["by_features_source"] = {src: _metrics([r for r in results if r.get("features_source") == src])
                                 for src in sorted({r.get("features_source") for r in results if r.get("features_source")})}
    return out


def _metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Primary: near-misses DROPPED while their twin was APPROVED, over arms where both critiques were applied."""
    twins = {r["case_id"]: r for r in results if r["arm"] == "twin"}
    near = [r for r in results if r["arm"] == "planted"]
    unavailable = [r["id"] for r in results if r.get("model_critique") != "applied"]
    clean = [(p, twins[p["case_id"]]) for p in near if p.get("model_critique") == "applied"
             and (twins.get(p["case_id"]) or {}).get("model_critique") == "applied"]
    n = len(clean)
    hit = sum(p["verdict"] == "drop" and t["verdict"] == "approve" for p, t in clean)
    by_kind: dict[str, dict[str, int]] = {}
    for p, t in clean:
        k = by_kind.setdefault(p["plant_kind"], {"n": 0, "dropped_twin_approved": 0, "dropped": 0, "sent_back": 0})
        k["n"] += 1
        k["dropped_twin_approved"] += int(p["verdict"] == "drop" and t["verdict"] == "approve")
        k["dropped"] += int(p["verdict"] == "drop")
        k["sent_back"] += int(p["verdict"] == "send_back")
    tw = [t for t in twins.values() if t.get("model_critique") == "applied"]
    return {"near_misses_scored": n, "unavailable": unavailable,
            "primary_dropped_while_twin_approved": hit, "primary_rate": None if not n else round(hit / n, 3),
            "planted_dropped": sum(p["verdict"] == "drop" for p, _ in clean),
            "planted_dropped_or_sent_back": sum(p["verdict"] in ("drop", "send_back") for p, _ in clean),
            "twins_scored": len(tw), "twins_approved": sum(t["verdict"] == "approve" for t in tw),
            "twins_sent_back": sum(t["verdict"] == "send_back" for t in tw),
            "twins_dropped": sum(t["verdict"] == "drop" for t in tw), "by_plant_kind": by_kind}


def run(settings: Settings, cases_path: Path, expect_sha: str, out_path: Path) -> dict[str, Any]:
    _guard(settings)
    sha = sha256_of(cases_path)
    if sha != expect_sha:
        sys.exit(f"refusing to run: case file sha256 {sha} != pre-registered {expect_sha}")
    spec = json.loads(cases_path.read_text(encoding="utf-8"))
    from ..tracing import new_run_id

    run_id = new_run_id("planted")
    results = []
    for case in spec["cases"]:  # one pass, fixed order: the twin, then its near-misses; no per-case re-runs
        for near in [None, *[n for n in case["near_misses"] if n["reaches_skeptic"]]]:
            results.append(review_case(settings, case, near, run_id))
            print(json.dumps({k: results[-1].get(k) for k in ("id", "arm", "plant_kind", "score", "verdict",
                                                              "model_critique")}), flush=True)
    import subprocess

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()

    report = {"prereg": "engg/docs/eval/PLANTED_SKEPTIC_PREREG.md", "cases_sha256": sha, "run_id": run_id,
              "code_sha": git("rev-parse", "HEAD"), "code_dirty": bool(git("status", "--porcelain", "services/api")),
              "lane_reason": settings.lanes.get("reason"), "summary": summarise(results),
              "stopped_by_linker": [n for c in spec["cases"] for n in c["near_misses"] if not n["reaches_skeptic"]],
              "results": results}
    out_path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.eval.planted_skeptic")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--cases", type=Path, required=True)
    r.add_argument("--expect-sha", required=True)
    r.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    settings = get_settings()
    if args.cmd == "prepare":
        if not settings.sample_mode:
            sys.exit("prepare runs on the sample data: set SAMPLE_MODE=true")
        spec = prepare(settings)
        # LF on every OS: the pre-registration pins this file's sha256.
        args.out.write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        nm = [n for c in spec["cases"] for n in c["near_misses"]]
        print(f"{len(spec['cases'])} twins, {len(nm)} near-misses ({sum(not n['reaches_skeptic'] for n in nm)} "
              f"stopped by the Linker), {len(spec['skipped'])} skipped; sha256 {sha256_of(args.out)}")
        return 0
    report = run(settings, args.cases, args.expect_sha, args.out)
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
