"""The stored dossier text reads as one document: chunk notes merged in code, every citation kept (no model)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.agents.series import merge_dossier_text

LIVE = json.loads((Path(__file__).parent / "fixtures" / "dossier_red_pulsar.json").read_text(encoding="utf-8"))
CITE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_./:-]*)\]")


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur is not None and line.strip():
            out[cur].append(line)
    return out


def test_every_citation_survives_the_merge():
    merged = merge_dossier_text(LIVE["text"])
    assert set(CITE.findall(LIVE["text"])) <= set(CITE.findall(merged))
    assert set(LIVE["cited_ids"]) <= set(CITE.findall(merged))


def test_headings_are_not_repeated_and_no_section_is_empty():
    merged = merge_dossier_text(LIVE["text"])
    heads = [line for line in merged.splitlines() if line.startswith("#") or line.startswith("**")]
    assert len(heads) == len(set(heads))
    assert not any(line.startswith("**") for line in merged.splitlines())  # the chunks' bold pseudo-headings go
    assert all(lines for lines in sections(merged).values())
    assert merged.startswith("# Series dossier SER-B687C36CFC\nRead 30 of 30 records.")


def test_the_timeline_is_in_date_order_and_holds_every_dated_line():
    merged = merge_dossier_text(LIVE["text"])
    tl = sections(merged)["Timeline"]
    months = "jan feb mar apr may jun jul aug sep oct nov dec".split()

    def key(line):
        m = re.match(r"- (\d{1,2}) ([A-Za-z]{3})", line)
        return (months.index(m.group(2).lower()), int(m.group(1)))

    assert [key(x) for x in tl] == sorted(key(x) for x in tl)
    assert tl[0].startswith("- 14 Sep") and any(x.startswith("- 19 Oct") for x in tl)
    assert not any(re.match(r"- \d{1,2} [A-Za-z]{3}", x) for s, ls in sections(merged).items() if s != "Timeline"
                   for x in ls)


def test_mo_lines_fill_the_mo_section_and_duplicates_union_their_citations():
    merged = merge_dossier_text(LIVE["text"])
    mo = sections(merged)["Consistent MO"]
    assert mo and "no recurring MO terms" not in merged
    helmet = [x for x in merged.splitlines() if x.startswith("- Helmet make/model")]
    assert len(helmet) == 1 and {"CHN-VL-2026-000877", "ST-020522", "ST-017554"} <= set(CITE.findall(helmet[0]))


def test_merge_is_idempotent_and_leaves_plain_text_alone():
    merged = merge_dossier_text(LIVE["text"])
    assert merge_dossier_text(merged) == merged
    assert merge_dossier_text("") == ""
    assert merge_dossier_text("# Series dossier X\nno chunks") == "# Series dossier X\nno chunks"


def test_the_series_analyst_stores_the_merged_text(monkeypatch):
    """dossier() returns merged text; cited_ids (the engine's checked list) are unchanged."""
    from types import SimpleNamespace

    from app.agents import series as mod

    fake = SimpleNamespace(dossier=lambda sid, recs, **k: {"text": LIVE["text"], "cited_ids": LIVE["cited_ids"],
                                                         "chunks": 3, "tokens_projected": 1, "tokens_actual": 1})
    analyst = mod.SeriesAnalyst(SimpleNamespace(engines=SimpleNamespace(markovian=fake),
                                                tracer=SimpleNamespace(emit=lambda *a, **k: None)))
    monkeypatch.setattr(analyst, "records", lambda ids: [{"id": "CHN-X", "kind": "crime", "text": "t"}])
    out = analyst.dossier("SER-B687C36CFC", ["CHN-X"], use_model=False)
    assert out["text"] == merge_dossier_text(LIVE["text"]) and out["cited_ids"] == LIVE["cited_ids"]
