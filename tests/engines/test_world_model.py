"""Spec E4 World Model: idempotent re-ingest, writers converge, provenance kept, bounded context."""

import pytest

from app.engines import world_model
from app.engines.world_model.core import decide, entity_id_from_name, normalize_name

CASE = [
    {"type": "crime", "key": "ADY-1182-2026", "attrs": {"crime_type": "chain snatching", "station": "Adyar"},
     "edges": [{"type": "used_vehicle", "to": {"type": "vehicle", "key": "TN 09 AB 1234"}},
               {"type": "seen_at", "to": {"type": "place", "key": "8961892b0dfffff"}},
               {"type": "involves", "to": {"type": "person", "key": "Karthik S"}}]},
]


def test_reingesting_the_same_case_changes_nothing():
    first = world_model.ingest(CASE, source="Extractor")
    before = world_model.store().state_canonical()
    again = world_model.ingest(CASE, source="Extractor")
    assert again == first
    assert world_model.store().state_canonical() == before


def test_two_agents_writing_the_same_plate_converge_on_one_entity():
    (a,) = world_model.ingest([{"type": "vehicle", "key": "TN 09 AB 1234", "attrs": {"colour": "red"}}], "Extractor")
    (b,) = world_model.ingest([{"type": "vehicle", "key": "tn09-ab-1234", "attrs": {"make": "Pulsar"}}], "Linker")
    assert a == b == "vehicle:plate:TN09AB1234"
    vehicles = [e for e in world_model.store().entities.values() if e.type == "vehicle"]  # one store read
    assert len(vehicles) == 1
    assert vehicles[0].attrs == {"colour": "red", "make": "Pulsar"}


def test_near_identical_plates_stay_distinct():
    ids = world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}, {"type": "vehicle", "key": "TN09AB1235"}], "x")
    assert ids[0] != ids[1]


def test_canonical_reconstruction_keeps_provenance():
    world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}], "Extractor")
    world_model.ingest([{"type": "vehicle", "key": "TN 09 AB 1234"}], "Linker")
    world_model.ingest([{"type": "vehicle", "key": "TN 09 AB 1234"}], "Linker")  # repeat adds nothing
    ent = world_model.store().entities["vehicle:plate:TN09AB1234"]
    assert [p["source"] for p in ent.provenance] == ["Extractor", "Linker"]
    assert ent.aliases == ["TN09AB1234", "TN 09 AB 1234"]


def test_people_resolve_through_name_similarity_bands():
    ids = world_model.ingest([{"type": "person", "key": "Karthik Selvam"},
                              {"type": "person", "key": "Karthik Selvan"},  # 0.93 -> auto-merge
                              {"type": "person", "key": "Murugan R"}], "Extractor")
    assert ids[0] == ids[1] != ids[2]
    assert decide(0.85) == "auto-merge" and decide(0.82) == "review" and decide(0.81) == "new"


def test_stable_ids_follow_reference_normalisation():
    assert normalize_name("José  García") == "jose garcia"
    assert entity_id_from_name("person", "José García") == entity_id_from_name("person", "jose garcia")
    assert entity_id_from_name("org", "Acme Corp") != entity_id_from_name("org", "Acme Corporation")


def test_context_returns_shared_entities_first_with_reasons_and_respects_budget():
    shared_bike = {"type": "vehicle", "key": "TN09AB1234"}
    world_model.ingest([
        {"type": "crime", "key": "C-1", "edges": [{"type": "used_vehicle", "to": shared_bike},
                                                   {"type": "seen_at", "to": {"type": "place", "key": "h-a"}}]},
        {"type": "crime", "key": "C-2", "edges": [{"type": "used_vehicle", "to": shared_bike},
                                                   {"type": "seen_at", "to": {"type": "place", "key": "h-b"}}]},
    ], "Extractor")
    ctx = world_model.context(["C-1", "C-2", "C-404"])
    sel = ctx["selection"]
    assert [s["reason"] for s in sel[:3]] == ["requested crime", "requested crime", "shared by 2 requested crimes"]
    assert sel[2]["id"] == "vehicle:plate:TN09AB1234"
    assert ctx["missing"] == ["C-404"]
    chosen = {s["id"] for s in sel}
    assert all(r["from"] in chosen and r["to"] in chosen for r in ctx["relations"])
    small = world_model.context(["C-1", "C-2"], budget=3)
    assert len(small["entities"]) == 3 and small["truncated"] is True


def test_write_without_provenance_is_rejected():
    with pytest.raises(ValueError):
        world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}], source="")


def test_sidecar_namespaces_do_not_share_state(engine_backend, monkeypatch):
    if engine_backend != "sidecar":
        pytest.skip("sidecar namespaces only")
    world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}], "Extractor")
    monkeypatch.setenv("ENGINES_SIDECAR_NS", "other-client-" + engine_backend + str(id(monkeypatch)))
    assert world_model.store().entities == {}
