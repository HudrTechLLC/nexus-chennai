"""New source onboarding, worker side (WS1-23).

The console writes `onboarding_runs` (0007_15) and, for an upload, the file to the private `onboarding` bucket. The
worker, which can reach Zetaris and Nightshift, does the rest, one run at a time:

  uploaded  -> profiling -> proposed     stage the CSV in the Zetaris file store, register it as onboard_<key>_raw,
                                         profile it THROUGH Zetaris, ask the fast lane (Nemotron Lightning) for a
                                         column mapping onto the unified crime fields (traced, with a receipt),
                                         validate it strictly (or fall back to rules, labelled), run DQ checks
  approved  -> registering -> registered register the mapped view onboard_<key> in the nexus container, count it and
                                         re-run DQ on the approved mapping
  any step  -> failed (with the reason)

The registered view is NOT part of v_crime_unified and nothing links it ("registered, not linked"). All SQL comes
from adapters/zetaris_onboard.py's fixed templates over generated names; CSV headers are checked before any use.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

from .adapters import zetaris_onboard as zo
from .agents.base import parse_model_json
from .config import REPO_ROOT, Settings, load_city
from .graph.store import SupabaseStore
from .tracing import Tracer, new_run_id

AGENT = "Onboarder"
SAMPLE_FILE = REPO_ROOT / "data" / "onboarding" / "sample_new_station.csv"
MAX_BYTES = 2 * 1024 * 1024
CONTAINER = os.environ.get("ZETARIS_DRIVER_CONTAINER", "zetaris-driver-1")
LANE = "fast"

StageFn = Callable[[str, bytes], None]


# =====================
# Small helpers
# =====================


def read_headers(data: bytes) -> list[str]:
    if len(data) > MAX_BYTES:
        raise zo.OnboardRejected("the file is larger than 2 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise zo.OnboardRejected("the file is not UTF-8 text") from exc
    first = next(csv.reader(io.StringIO(text)), None)
    if not first:
        raise zo.OnboardRejected("the file is empty")
    return zo.check_headers(first)


def station_for(settings: Settings, run: dict[str, Any]) -> tuple[str, str]:
    """(station_id, station_name) for a run: the city pack's sample station, or one derived from the source key."""
    if run.get("use_sample"):
        spec = yaml.safe_load((REPO_ROOT / "cities" / settings.city / "onboarding_sample.yaml").read_text(encoding="utf-8"))
        return spec["station"]["id"], spec["station"]["name"]
    key = zo.check_key(run["source_key"])
    return f"PS-{key.upper().replace('_', '-')}"[:40], run.get("label") or key


def docker_stage(key: str, data: bytes) -> None:
    """Copy the file to <STAGE_ROOT>/<key>/source.csv in the Zetaris driver (docker cp, as stage_files.py does)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / zo.check_key(key)
        folder.mkdir()
        (folder / "source.csv").write_bytes(data)
        subprocess.run(["docker", "cp", f"{folder}{os.sep}.", f"{CONTAINER}:{zo.STAGE_ROOT}/{key}"], check=True,
                       capture_output=True)
        subprocess.run(["docker", "exec", "-u", "0", CONTAINER, "chmod", "-R", "a+rX", zo.STAGE_ROOT], check=True,
                       capture_output=True)


# =====================
# Mapping: model, validated; rules as a labelled fallback
# =====================

MAP_PROMPT = (
    "You map the columns of a police station's crime export onto a unified crime schema.\n"
    "Unified fields (use exactly these names, or null to ignore a column): {fields}.\n"
    "Required: {required}.\n"
    "Transforms (put these in \"transform\", never in \"unified_field\"): none, trim_upper, date_dmy (dd/mm/yyyy), "
    "datetime_dmy_hm (dd/mm/yyyy HH:MM), latlong_lat. A single column holding both coordinates ('13.19, 80.18') "
    "gets unified_field \"lat\" and transform \"latlong_lat\"; lon is then derived from it, so do not map lon too.\n"
    "Columns with up to 5 example values:\n{columns}\n"
    'Reply with JSON only: {{"mapping": [{{"source_col": "...", "unified_field": "..." or null, "transform": "...", '
    '"confidence": 0.0-1.0, "reason": "one short line"}}]}} with every column exactly once.'
)


def validate_mapping(raw: Any, columns: list[str]) -> list[dict[str, Any]]:
    """The model's mapping, checked: every column once, allowlisted fields and transforms, a 0-1 confidence, a short
    reason. A combined lat/long column mapped to lat with latlong_lat gets its lon twin added. Raises on anything else."""
    items = raw.get("mapping") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("no mapping list")
    by_col: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict) or it.get("source_col") not in columns or it["source_col"] in by_col:
            raise ValueError(f"bad or repeated column: {str(it)[:80]}")
        field = it.get("unified_field") or None
        t = it.get("transform") or "none"
        if field in ("latlong_lat", "latlong_lon"):  # the one confusion the fast lane makes: transform in the field slot
            field, t = "lat", "latlong_lat"
        if field is not None and field not in zo.FIELDS:
            raise ValueError(f"unknown field {field!r}")
        if t not in zo.TRANSFORMS:
            raise ValueError(f"unknown transform {t!r}")
        conf = float(it.get("confidence", 0))
        if not 0 <= conf <= 1:
            raise ValueError("confidence out of range")
        by_col[it["source_col"]] = {"source_col": it["source_col"], "unified_field": field, "transform": t,
                                    "confidence": round(conf, 2), "reason": str(it.get("reason") or "")[:300]}
    if not by_col:
        raise ValueError("the mapping is empty")
    # A column the model left out is ignored, and says so (approve still requires every required field).
    for c in columns:
        by_col.setdefault(c, {"source_col": c, "unified_field": None, "transform": "none", "confidence": 0.0,
                              "reason": "not mapped by the model: ignored"})
    return [by_col[c] for c in columns]


def lat_lon_split(mapping: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A 'lat, lon' column feeds two fields. The mapping table keys on the column, so the lon side is carried as
    the view's derived column: callers pass this expanded list to the SQL templates."""
    out = list(mapping)
    for m in mapping:
        if m.get("transform") == "latlong_lat" and m.get("unified_field") == "lat" and \
                not any(x.get("unified_field") == "lon" for x in mapping):
            out.append({**m, "unified_field": "lon", "transform": "latlong_lon"})
    return out


RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("fir",), "fir_no", "none"),
    (("lat/long", "latlong", "lat-long", "lat, long", "coordinates", "lat long"), "lat", "latlong_lat"),
    (("date of occ", "occurrence", "occurred", "date"), "occurred_from", "date_dmy"),
    (("crime head", "category", "head", "offence"), "category", "none"),
    (("section",), "sections_raw", "none"),
    (("place", "address", "location"), "address", "none"),
    (("brief", "facts", "narrative", "description"), "narrative", "none"),
    (("status",), "status", "none"),
    (("latitude",), "lat", "none"),
    (("longitude",), "lon", "none"),
]


def rules_mapping(columns: list[str]) -> list[dict[str, Any]]:
    used: set[str] = set()
    out = []
    for c in columns:
        low = c.lower()
        hit = next(((f, t) for keys, f, t in RULES if f not in used and any(k in low for k in keys)), None)
        if hit:
            used.add(hit[0])
        out.append({"source_col": c, "unified_field": hit[0] if hit else None, "transform": hit[1] if hit else "none",
                    "confidence": 0.5 if hit else 0.0, "reason": "header keyword rule (model mapping unavailable)"})
    return out


# =====================
# The worker step
# =====================


class Onboarder:
    def __init__(self, settings: Settings, sb: Any, zetaris: Any, nightshift: Any, logs_dir: Path,
                 stage: StageFn = docker_stage) -> None:
        self.settings, self.sb, self.zetaris, self.nightshift = settings, sb, zetaris, nightshift
        self.logs_dir, self.stage = logs_dir, stage
        self.tz = load_city(settings.city)["timezone"]

    def process(self) -> int:
        """One uploaded run and one approved run per pass. Nothing to do -> no Zetaris or model call at all."""
        done = 0
        for status, step in (("uploaded", self._propose), ("approved", self._register)):
            rows = self.sb.select("onboarding_runs", {"select": "*", "status": f"eq.{status}",
                                                      "order": "created_at.asc", "limit": "1"})
            for run in rows:
                self._with_run(run, step)
                done += 1
        return done

    def _with_run(self, run: dict[str, Any], step: Callable[[dict[str, Any], Tracer], None]) -> None:
        rid = new_run_id("onboard")
        tracer = Tracer(rid, self.logs_dir, echo=False)
        store = SupabaseStore(self.sb, tracer)
        store.start_run(rid, "batch", f"logs/trace-{rid}.jsonl", subject=f"onboarding:{run['source_key']}")
        old = (getattr(self.zetaris, "tracer", None), getattr(self.nightshift, "tracer", None))
        self.zetaris.tracer = tracer
        if self.nightshift is not None:
            self.nightshift.tracer = tracer
        outcome = "success"
        try:
            step(run, tracer)
        except Exception as exc:  # the run fails with a reason the admin can read; nothing else is affected
            outcome = "error"
            msg = str(exc) if isinstance(exc, zo.OnboardRejected) else f"{type(exc).__name__}: {str(exc)[:300]}"
            tracer.emit(AGENT, "onboarding_failed", input_summary=run["source_key"], output_summary=msg[:300],
                        status="error")
            self.sb.update("onboarding_runs", {"run_id": f"eq.{run['run_id']}"},
                           {"status": "failed", "error": msg[:500], "trace_run_id": rid})
        finally:
            self.zetaris.tracer = old[0]
            if self.nightshift is not None:
                self.nightshift.tracer = old[1]
            store.finish_run(rid, outcome, kind="batch")

    # ----- uploaded -> proposed ---------------------------------------------------

    def _propose(self, run: dict[str, Any], tracer: Tracer) -> None:
        key = zo.check_key(run["source_key"])
        match = {"run_id": f"eq.{run['run_id']}"}
        self.sb.update("onboarding_runs", match, {"status": "profiling", "trace_run_id": tracer.run_id, "error": None})
        data = SAMPLE_FILE.read_bytes() if run.get("use_sample") else self.sb.download("onboarding", run["file_path"])
        headers = read_headers(data)  # reject bad headers before anything reaches Zetaris
        station_id, station_name = station_for(self.settings, run)
        self.stage(key, data)
        tracer.emit(AGENT, "staged", input_summary=key, output_summary=f"{len(data)} bytes, {len(headers)} columns")
        try:
            self.zetaris.onboard("create_raw", key, agent=AGENT)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
        columns = zo.check_headers([r[0] for r in self.zetaris.onboard("describe_raw", key, agent=AGENT).rows])
        if [c.lower() for c in columns] != [h.lower() for h in headers]:
            raise zo.OnboardRejected("Zetaris read different columns than the file header")
        prof = self.zetaris.onboard("profile", key, columns, agent=AGENT).rows[0]
        ex_rows = self.zetaris.onboard("examples", key, columns, agent=AGENT).rows
        n = int(prof[0])
        profile = [{"column": c, "type": "string", "non_null": int(prof[1 + 2 * i]), "distinct": int(prof[2 + 2 * i]),
                    "examples": [str(r[i]) for r in ex_rows if r[i] not in (None, "")][:5]}
                   for i, c in enumerate(columns)]
        mapping, source = self._map(profile, tracer)
        dq = self._dq(key, mapping, station_id)
        self.sb.delete("onboarding_mappings", {"run_id": f"eq.{run['run_id']}"})
        self.sb.insert("onboarding_mappings", [{"run_id": run["run_id"], "source_col": m["source_col"],
                                                "proposed_field": m["unified_field"], "unified_field": m["unified_field"],
                                                "transform": m["transform"], "confidence": m["confidence"],
                                                "reason": m["reason"]} for m in mapping])
        self.sb.update("onboarding_runs", match, {"status": "proposed", "row_count": n, "profile": profile, "dq": dq,
                                                  "mapping_source": source, "station_name": station_name})
        dq_note = ",".join(f"{d['rule']}={d['count']}" for d in dq)
        tracer.emit(AGENT, "proposed", input_summary=key,
                    output_summary=f"rows={n} columns={len(columns)} mapping={source} dq={dq_note}")

    def _map(self, profile: list[dict[str, Any]], tracer: Tracer) -> tuple[list[dict[str, Any]], str]:
        columns = [p["column"] for p in profile]
        prompt = MAP_PROMPT.format(fields=", ".join(zo.FIELDS), required=", ".join(zo.REQUIRED),
                                   columns="\n".join(f"- {p['column']}: {json.dumps(p['examples'][:5], ensure_ascii=False)}"
                                                     for p in profile))
        if self.nightshift is None:
            return rules_mapping(columns), "rules"
        try:
            res = self.nightshift.chat(LANE, [{"role": "user", "content": prompt}], agent=AGENT,
                                       purpose="onboarding column mapping", max_tokens=1500,
                                       chat_template_kwargs={"enable_thinking": False})
            return validate_mapping(parse_model_json(res.content), columns), "model"
        except Exception as exc:
            tracer.emit(AGENT, "mapping_fallback", output_summary=f"{type(exc).__name__}: {str(exc)[:200]}",
                        status="degraded")
            return rules_mapping(columns), "rules"

    def _dq(self, key: str, mapping: list[dict[str, Any]], station_id: str) -> list[dict[str, Any]]:
        full = lat_lon_split(mapping)
        tz = self.tz
        try:
            zo.mapped_select(key, full, station_id, tz)
        except zo.OnboardRejected as exc:
            return [{"rule": "mapping_incomplete", "severity": "warn", "count": 1, "sample_rows": [str(exc)]}]
        bounds = tuple(load_city(self.settings.city)["map"]["bounds"])
        counts = self.zetaris.onboard("dq", key, full, station_id, tz, bounds, agent=AGENT).rows[0]
        samples = self.zetaris.onboard("dq_samples", key, full, station_id, tz, bounds, agent=AGENT).rows
        dups = self.zetaris.onboard("likely_duplicates", key, full, station_id, tz, agent=AGENT).rows
        by_rule = {"bad_date": int(counts[1] or 0), "out_of_city": int(counts[2] or 0),
                   "missing_required": int(counts[3] or 0), "repeated_fir_no": int(counts[4] or 0),
                   "ends_before_start": int(counts[5] or 0), "occurred_after_reported": int(counts[6] or 0),
                   "likely_duplicate_of_existing": len({r[0] for r in dups})}
        sev = {"bad_date": "warn", "out_of_city": "warn", "missing_required": "warn", "repeated_fir_no": "warn",
               "ends_before_start": "warn", "occurred_after_reported": "warn", "likely_duplicate_of_existing": "info"}
        out = []
        for rule, count in by_rule.items():
            if rule == "likely_duplicate_of_existing":
                rows = [f"{r[0]} ~ {r[1]}" for r in dups][:10]
            elif rule == "repeated_fir_no":
                rows = []
            else:
                rows = [str(r[0]) for r in samples if r[1] == rule][:10]
            item = {"rule": rule, "severity": sev[rule], "count": count, "sample_rows": rows}
            if rule == "likely_duplicate_of_existing":
                item["detail"] = "same place (about 275 m) and time; category not compared (the export uses its own crime heads)"
            out.append(item)
        return out

    # ----- approved -> registered ---------------------------------------------------

    def _register(self, run: dict[str, Any], tracer: Tracer) -> None:
        key = zo.check_key(run["source_key"])
        match = {"run_id": f"eq.{run['run_id']}"}
        self.sb.update("onboarding_runs", match, {"status": "registering", "trace_run_id": tracer.run_id})
        rows = self.sb.select("onboarding_mappings", {"select": "source_col,unified_field,transform",
                                                      "run_id": f"eq.{run['run_id']}", "order": "source_col.asc"})
        station_id, _ = station_for(self.settings, run)
        mapping = lat_lon_split([{**r, "source_col": zo.check_header(r["source_col"])} for r in rows])
        self.zetaris.onboard("create_view", key, mapping, station_id, self.tz, agent=AGENT)
        n = int(self.zetaris.onboard("count_view", key, agent=AGENT).rows[0][0])
        dq = self._dq(key, [r for r in mapping if r["transform"] != "latlong_lon"], station_id)
        self.sb.update("onboarding_runs", match, {"status": "registered", "view_name": zo.ident(key), "row_count": n,
                                                  "dq": dq, "error": None})
        tracer.emit(AGENT, "registered", input_summary=zo.ident(key),
                    output_summary=f"rows={n} (registered, not linked: not part of v_crime_unified)")
