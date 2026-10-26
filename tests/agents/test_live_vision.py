"""Live runs read evidence stills with the vision lane; sample runs never do (judge examples stay byte-stable).

Before: the runner built AgentGraph(deps) with no media_loader, so on every live run the Extractor went straight to
the caption fallback and never attempted the vision lane; no trace could show `vision_unavailable`.
"""

from __future__ import annotations

import json

import httpx
from agents_fixtures import ADYAR, as_row

from app.adapters.nightshift import NightshiftClient
from app.adapters.supabase import SupabaseClient
from app.agents import AgentDeps, MemoryStore
from app.agents.base import crime_from_row
from app.agents.extractor import Extractor
from app.config import Settings
from app.graph.runner import media_loader_for
from app.tracing import Tracer

MO = {"mo": {"approach": "two_wheeler_from_behind", "target": "lone_pedestrian_woman", "target_item": "gold_chain"},
      "visual_tags": [], "entities": {"plates": []}}
REFUSED = ("no_vision_model: request has image attachments but no configured vision-capable model admits them")


def live(**kw) -> Settings:
    return Settings(_env_file=None, sample_mode=False, supabase_url="http://sb.test",
                    supabase_service_role_key="k", **kw)


# ----- the loader --------------------------------------------------------------------------------------------


def test_no_loader_in_sample_mode_or_without_supabase():
    assert media_loader_for(Settings(_env_file=None, sample_mode=True, supabase_url="http://sb.test",
                                     supabase_service_role_key="k")) is None
    assert media_loader_for(Settings(_env_file=None, sample_mode=False, supabase_url="",
                                     supabase_service_role_key="")) is None


def test_live_loader_reads_the_private_evidence_bucket():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, req.headers.get("authorization")))
        return httpx.Response(200, content=b"\xff\xd8jpeg")

    load = media_loader_for(live(), client=SupabaseClient(live(), transport=httpx.MockTransport(handler)))
    assert load("CHN-VL-2026-001300/abc.jpg") == b"\xff\xd8jpeg"
    assert seen == [("GET", "/storage/v1/object/evidence/CHN-VL-2026-001300/abc.jpg", "Bearer k")]


# ----- the Extractor through the real Nightshift adapter -----------------------------------------------------


def run_extract(tmp_path, vision_reply, stills=2):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body["model"])
        if body["model"] == "nvidia/vl":
            return vision_reply(body)
        return httpx.Response(200, json={"id": "c1", "model": body["model"],
                                         "choices": [{"message": {"content": json.dumps(MO)}}]})

    s = Settings(_env_file=None, meterless_base_url="http://ns.test/v1", meterless_runtime_token="t",
                 lane_fast="nvidia/fast", lane_vision="nvidia/vl", sample_mode=False)
    tr = Tracer("r", tmp_path, echo=False)
    deps = AgentDeps(tracer=tr, zetaris=None, store=MemoryStore(),
                     nightshift=NightshiftClient(s, tr, transport=httpx.MockTransport(handler)))
    evidence = [{"evidence_id": f"EV-{i}", "kind": "cctv_still", "storage_path": f"c/{i}.jpg"} for i in range(stills)]
    case = crime_from_row(as_row({**ADYAR, "evidence": evidence}))
    f = Extractor(deps, media_loader=lambda p: b"\xff\xd8").extract_case(case)
    return f, [e for e in tr.read()], calls


def test_refused_vision_is_traced_unavailable_then_the_caption_is_used_once_per_run(tmp_path):
    f, events, calls = run_extract(tmp_path, lambda body: httpx.Response(502, json={"error": {"message": REFUSED}}))
    acts = [(e["action"], e["input_summary"]) for e in events if e["action"].startswith("vision")]
    assert acts[0] == ("vision_unavailable", "EV-0") and ("vision_fallback", "EV-0") in acts
    assert ("vision_fallback", "EV-1") in acts and ("vision_unavailable", "EV-1") not in acts  # remembered
    assert all(e["status"] == "degraded" for e in events if e["action"].startswith("vision"))
    assert "no_vision_model" in next(e["output_summary"] for e in events if e["action"] == "vision_unavailable")
    assert f["degraded"] == ["vision:EV-0", "vision:EV-1"]
    assert calls.count("nvidia/vl") == 1  # a refusal is an answer: not retried, and not re-asked for the next still


def test_a_working_vision_lane_reads_the_still(tmp_path):
    reply = {"tags": ["red motorcycle", "two riders"], "plate_read": "TN 09 B? 4471"}
    f, events, calls = run_extract(tmp_path, lambda body: httpx.Response(200, json={
        "id": "v1", "model": "nvidia/vl", "choices": [{"message": {"content": json.dumps(reply)}}]}), stills=1)
    assert "nvidia/vl" in calls and "red motorcycle" in f["visual_tags"] and "TN 09 B? 4471" in f["entities"]["plates"]
    assert not f["degraded"]
    assert not [e for e in events if e["action"] in ("vision_unavailable", "vision_fallback")]
    assert any(e["action"] == "model_call" and e["input_summary"].startswith("lane=vision") for e in events)


# ----- Nightshift cloud vision lane (chief, 2026-10-27): an empty response needs more room, not a refusal -------

EMPTY = "provider returned no content: upstream_empty_response"


def test_the_vision_call_asks_for_enough_room(tmp_path):
    seen = []

    def reply(body):
        seen.append(body.get("max_tokens"))
        return httpx.Response(200, json={"id": "v1", "model": "nvidia/vl",
                                         "choices": [{"message": {"content": json.dumps({"tags": ["red"]})}}]})
    run_extract(tmp_path, reply, stills=1)
    assert seen and seen[0] >= 1000  # max_tokens=20 came back 502 _empty_response on the live route


def test_an_empty_response_is_retried_once_with_more_room_then_reads_the_still(tmp_path):
    seen = []

    def reply(body):
        seen.append(body.get("max_tokens"))
        if len(seen) == 1:
            return httpx.Response(502, json={"error": {"message": EMPTY}})
        return httpx.Response(200, json={"id": "v2", "model": "nvidia/vl",
                                         "choices": [{"message": {"content": json.dumps({"tags": ["crowbar"]})}}]})
    f, events, calls = run_extract(tmp_path, reply, stills=1)
    assert len(seen) == 2 and seen[1] == 2 * seen[0]  # one retry (no identical transport retries), double room
    assert "crowbar" in f["visual_tags"] and not f["degraded"]
    assert not [e for e in events if e["action"] in ("vision_unavailable", "vision_fallback")]
    assert any(e["action"] == "model_empty_response" and e["status"] == "retry" for e in events)


def test_an_empty_response_twice_falls_back_without_marking_vision_down(tmp_path):
    f, events, calls = run_extract(tmp_path, lambda body: httpx.Response(502, json={"error": {"message": EMPTY}}),
                                   stills=2)
    assert calls.count("nvidia/vl") == 4  # 2 stills x (call + one retry): not a refusal, so still 2 asks
    assert [e["action"] for e in events if e["action"].startswith("vision_")].count("vision_failed") == 2
    assert not [e for e in events if e["action"] == "vision_unavailable"]
