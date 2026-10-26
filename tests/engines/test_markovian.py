"""Spec E4 Markovian: chunk count matches the budget, carryover capped, only real ids cited, savings logged."""

import json
import math

import pytest

from app.engines import markovian
from app.engines.markovian.core import ConfigValidationError, estimate_tokens, resolve_config


def _records(n):
    kinds = ["fir", "statement", "tip", "diary"]
    return [{"id": f"R-{i:03d}", "kind": kinds[i % 4], "date": f"2026-0{1 + i % 9}-{10 + i % 18:02d}",
             "text": f"Record {i}: two men on a red Pulsar snatched a gold chain near the bus stop. "
                     f"The pillion rider wore a black helmet and the rider had a scar on his left hand. "
                     f"Witness {i} saw them turn towards the main road.",
             "mo_tags": ["red pulsar", "pillion snatch", "evening"]} for i in range(n)]


def test_chunk_count_matches_the_budget():
    recs = _records(240)
    cfg = markovian.DEFAULT_CONFIG
    d = markovian.dossier("SER-1", recs)
    total_tokens = sum(estimate_tokens(markovian.record_line(r) + "\n") for r in recs)
    assert d["chunks"] == d["chunks_planned"] == len(markovian.plan_chunks(recs, cfg))
    assert d["chunks"] >= math.ceil(total_tokens / cfg.input_budget)
    assert all(c["input_tokens"] <= cfg.input_budget for c in d["chunk_log"])
    assert d["status"] == "completed" and d["unread_ids"] == []


def test_max_chunks_is_respected_and_unread_records_reported():
    cfg = resolve_config(chunk_size=4000, max_chunks=3, carryover_tokens=400)
    d = markovian.dossier("SER-2", _records(240), config=cfg)
    assert d["chunks"] == 3 < d["chunks_planned"]
    assert d["status"] == "max-chunks" and d["unread_ids"]
    read = {i for c in d["chunk_log"] for i in c["record_ids"]}
    assert read.isdisjoint(d["unread_ids"]) and len(read) + len(d["unread_ids"]) == 240


def test_carryover_stays_within_the_size_cap():
    cfg = resolve_config(chunk_size=3000, max_chunks=32, carryover_tokens=128)
    d = markovian.dossier("SER-3", _records(150), config=cfg)
    assert d["chunks"] > 5
    assert all(c["carryover_tokens"] <= 128 for c in d["chunk_log"])


def test_dossier_cites_only_record_ids_that_exist():
    recs = _records(40)
    d = markovian.dossier("SER-4", recs)
    assert d["cited_ids"] and set(d["cited_ids"]) <= {r["id"] for r in recs}
    assert "## Timeline" in d["text"] and "## Consistent MO" in d["text"] and "pulsar" in d["text"]


def test_hallucinated_citations_are_removed():
    def lying_generator(prompt, batch, carryover, step):
        return (f"- [{batch[0]['id']}] real.\n- [FIR-9999] invented.\n"
                f"[TASK_COMPLETE]\n[STATE_CHECKPOINT]\nCOMPLETED: read {len(batch)} of {len(batch)} records")

    d = markovian.dossier("SER-5", _records(3), generator=lying_generator)
    assert "FIR-9999" not in d["text"] and d["dropped_citations"] == ["FIR-9999"]
    assert d["cited_ids"] == ["R-000"]


def test_projected_vs_actual_savings_are_logged(tracer):
    d = markovian.dossier("SER-6", _records(200))
    assert d["token_label"] == "estimated"
    assert d["tokens_projected"] > d["tokens_actual"] > 0
    assert d["tokens_saved"] == d["tokens_projected"] - d["tokens_actual"]
    lines = (tracer.path.parent / "markovian_runs.jsonl").read_text(encoding="utf-8").splitlines()
    (line,) = [json.loads(x) for x in lines]
    assert line["series_id"] == "SER-6" and line["tokens_projected"] == d["tokens_projected"]
    (ev,) = [e for e in tracer.read() if e["engine"] == "markovian"]
    assert f"projected {d['tokens_projected']} vs actual {d['tokens_actual']}" in ev["output_summary"]


def test_invalid_config_is_rejected_not_truncated():
    with pytest.raises(ConfigValidationError):
        resolve_config(chunk_size=1000, carryover_tokens=800)
    with pytest.raises(ConfigValidationError):
        resolve_config(max_chunks=33)
