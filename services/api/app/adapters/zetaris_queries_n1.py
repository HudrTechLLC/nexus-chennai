"""Named queries owned by the data lane (nexus-1), merged into NAMED_QUERIES by adapters/zetaris.py.

Lightning SQL runs on Zetaris against the registered sources (sb.* = Supabase via the read-only
role; nexus.* = semantic views once 10_views.sql lands). The DuckDB twin (sample mode) comes from
nexus-2's TWINS when present, so both forms declare the same output columns.

Output conventions (shared with the twins):
- timestamps are ISO 8601 strings in city time, e.g. 2026-10-14T19:40:00+05:30
- jsonb columns arrive as JSON strings; nested lists are JSON strings ("[]" when empty)
- list parameters are comma-joined strings (render() binds scalars only)
"""

from __future__ import annotations

from typing import Any

from ..config import REPO_ROOT, get_settings, load_city


def _city_time() -> tuple[str, str]:
    """(IANA zone, UTC offset) from the city pack; nothing city-specific in code (D-004)."""
    import yaml

    city = get_settings().city
    tz = load_city(city)["timezone"]
    gen = REPO_ROOT / "cities" / city / "generator" / "config.yaml"
    offset = yaml.safe_load(gen.read_text(encoding="utf-8"))["utc_offset"] if gen.is_file() else "+00:00"
    return tz, offset


def _ts(col: str, tz: str, offset: str) -> str:
    # cast-to-string keeps ':' out of the SQL text (render() treats ':name' as a parameter)
    return f"concat(replace(cast(from_utc_timestamp({col}, '{tz}') AS STRING), ' ', 'T'), '{offset}')"


CASE_COLUMNS = (
    "crime_id", "source", "source_row_id", "station_id", "fir_no", "category", "sub_type", "sections",
    "occurred_from", "occurred_to", "reported_at", "lat", "lon", "address", "ward_no", "h3_r9", "h3_r8",
    "geohash7", "week", "severity", "property", "weapon", "offenders_described", "victims", "status",
    "narrative", "synthetic", "vehicles", "statements", "evidence", "forensics", "features",
)
FEATURES_COLUMNS = ("crime_id", "extractor_version", "model", "receipt_id", "mo", "visual_tags", "entities",
                    "confidence", "reviewed_by_officer")


def _q_case(tz: str, off: str) -> str:
    t = lambda c: _ts(c, tz, off)  # noqa: E731
    return (
        "SELECT c.crime_id, c.source, c.source_row_id, c.station_id, c.fir_no, c.category, c.sub_type, c.sections, "
        f"{t('c.occurred_from')} AS occurred_from, {t('c.occurred_to')} AS occurred_to, "
        f"{t('c.reported_at')} AS reported_at, c.lat, c.lon, c.address, c.ward_no, c.h3_r9, c.h3_r8, c.geohash7, "
        "c.week, c.severity, c.property, c.weapon, c.offenders_described, c.victims, c.status, c.narrative, "
        "c.synthetic, coalesce(v.vehicles, '[]') AS vehicles, coalesce(s.statements, '[]') AS statements, "
        "coalesce(e.evidence, '[]') AS evidence, coalesce(f.forensics, '[]') AS forensics, cf.features "
        "FROM sb.crimes c "
        "LEFT JOIN (SELECT crime_id, to_json(collect_list(named_struct('role', role, 'type', vehicle_type, "
        "'plate', plate_pattern, 'make_model', make_model, 'colour', colour))) AS vehicles "
        "FROM sb.crime_vehicles WHERE crime_id = :crime_id GROUP BY crime_id) v ON v.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('statement_id', statement_id, "
        f"'witness_ref', witness_ref, 'mode', mode, 'text', text, 'recorded_at', {t('recorded_at')})))) AS statements "
        "FROM sb.statements WHERE crime_id = :crime_id GROUP BY crime_id) s ON s.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('evidence_id', evidence_id, "
        f"'kind', kind, 'storage_path', storage_path, 'captured_at', {t('captured_at')}, 'camera_id', camera_id, "
        "'vision', vision)))) AS evidence FROM sb.evidence_media WHERE crime_id = :crime_id GROUP BY crime_id) e "
        "ON e.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('forensic_id', forensic_id, "
        "'kind', kind, 'match_code', match_code)))) AS forensics FROM sb.forensics WHERE crime_id = :crime_id "
        "GROUP BY crime_id) f ON f.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(named_struct('extractor_version', extractor_version, 'model', model, "
        "'receipt_id', receipt_id, 'mo', mo, 'visual_tags', visual_tags, 'entities', entities, 'confidence', confidence, "
        "'reviewed_by_officer', reviewed_by_officer)) AS features FROM sb.crime_features_v "
        "WHERE crime_id = :crime_id) cf ON cf.crime_id = c.crime_id "
        "WHERE c.crime_id = :crime_id"
    )


Q_FEATURES = (
    "SELECT crime_id, extractor_version, model, receipt_id, mo, visual_tags, entities, confidence, "
    "reviewed_by_officer FROM sb.crime_features_v "
    "WHERE array_contains(split(:ids, ','), crime_id)"
)


def _twin(name: str, columns: tuple[str, ...]) -> str:
    """The DuckDB twin from nexus-2 when available; otherwise a stub that fails the width check loudly."""
    try:
        from .zetaris_queries_n2 import TWINS  # type: ignore[attr-defined]
    except ImportError:
        TWINS = {}
    sample, cols = TWINS.get(name, (None, None))
    if sample is None:
        return "SELECT 'no sample twin yet' AS note"
    if tuple(cols) != columns:
        raise ValueError(f"{name}: twin columns {cols} differ from the contract {columns}")
    return sample


def specs() -> dict[str, dict[str, Any]]:
    tz, off = _city_time()
    return {
        "q_case": {"name": "q_case", "lightning": _q_case(tz, off), "sample": _twin("q_case", CASE_COLUMNS),
                   "description": "One crime with vehicles, statements, evidence, forensics and features (D3.1)",
                   "columns": CASE_COLUMNS},
        "q_features": {"name": "q_features", "lightning": Q_FEATURES,
                       "sample": _twin("q_features", FEATURES_COLUMNS),
                       "description": "Extracted MO features for a comma-joined list of crime ids (D3.2)",
                       "columns": FEATURES_COLUMNS},
    }
