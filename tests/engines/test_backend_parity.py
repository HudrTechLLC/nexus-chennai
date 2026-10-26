"""The sample backend (Python port) and the sidecar backend (Meterless TypeScript references)
must agree: same World Model ids and state, same H-MEM relevance and deltas, same dossier.
Runs once, in the sidecar parametrisation, and compares against a fresh sample run."""

import pytest

from app.engines import hmem, markovian, world_model

from .conftest import CLOCK

ENTITIES = [
    {"type": "crime", "key": "ADY-1182-2026", "attrs": {"crime_type": "chain snatching"},
     "edges": [{"type": "used_vehicle", "to": {"type": "vehicle", "key": "TN 09 AB 1234", "attrs": {"colour": "red"}}},
               {"type": "involves", "to": {"type": "person", "key": "José Kumar"}},
               {"type": "seen_at", "to": {"type": "place", "key": "8961892B0DFFFFF"}}]},
    {"type": "crime", "key": "VEL-0877-2026",
     "edges": [{"type": "used_vehicle", "to": {"type": "vehicle", "key": "tn09ab1234"}},
               {"type": "involves", "to": {"type": "person", "key": "Jose Kumar"}},
               {"type": "involves", "to": {"type": "phone", "key": "+91 98400 12345"}}]},
]
PAIRS = [
    ({"a": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "motorcycle"},
      "b": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "car"}}, "reject", "different_offenders"),
    ({"a": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"},
      "b": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"}}, "approve", "same_offender"),
]
PROBES = [
    {"a": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "motorcycle"},
     "b": {"crime_type": "chain snatching", "area": "Adyar", "time_band": "night", "vehicle": "car"}},
    {"a": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"},
     "b": {"crime_type": "two-wheeler theft", "area": "Guindy", "vehicle": "red Pulsar"}},
]
RECORDS = [{"id": f"R-{i:03d}", "kind": ["fir", "tip", "statement"][i % 3], "date": f"2026-0{1 + i % 9}-1{i % 10}",
            "text": f"Case {i}. Two men on a red Pulsar snatched a chain near the temple. Rider wore a black helmet.",
            "mo_tags": ["red pulsar", "pillion snatch"], "status": "open" if i % 5 else "closed"} for i in range(90)]


def _run(tmp_path, backend, monkeypatch):
    monkeypatch.setenv("ENGINES_BACKEND", backend)
    world_model.reset()
    ids = world_model.ingest(ENTITIES, source="Extractor")
    state = world_model.store().state_canonical()
    ctx = world_model.context(["ADY-1182-2026", "VEL-0877-2026"])
    hmem.configure(tmp_path / f"mem-{backend}", clock=CLOCK)
    for i, (pair, decision, reason) in enumerate(PAIRS):
        hmem.record_decision(f"LA-{i}", decision, reason, None, pair)
    deltas = [hmem.adjust(p) for p in PROBES]
    d = markovian.dossier("SER-1", RECORDS, config=markovian.resolve_config(chunk_size=2400, carryover_tokens=256))
    return ids, state, ctx, deltas, d


def test_sample_and_sidecar_backends_agree(engine_backend, tmp_path, monkeypatch):
    if engine_backend != "sidecar":
        pytest.skip("parity runs once, in the sidecar parametrisation")
    side = _run(tmp_path, "sidecar", monkeypatch)
    sample = _run(tmp_path, "sample", monkeypatch)
    ids_side, state_side, ctx_side, deltas_side, d_side = side
    ids_sample, state_sample, ctx_sample, deltas_sample, d_sample = sample

    assert ids_side == ids_sample
    assert state_side == state_sample
    assert ctx_side["selection"] == ctx_sample["selection"]
    for a, b in zip(deltas_side, deltas_sample):
        assert a["memory_ids"] == b["memory_ids"]
        assert a["raw_delta"] == pytest.approx(b["raw_delta"], abs=1e-4)
        assert a["delta"] == b["delta"] != 0.0
    assert d_side["text"] == d_sample["text"]
    assert d_side["chunks"] == d_sample["chunks"] > 3
    assert [c["record_ids"] for c in d_side["chunk_log"]] == [c["record_ids"] for c in d_sample["chunk_log"]]
    assert d_side["tokens_projected"] == d_sample["tokens_projected"]
    assert d_side["tokens_actual"] == d_sample["tokens_actual"]
