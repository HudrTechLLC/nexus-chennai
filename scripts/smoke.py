"""P0 exit check: PASS/FAIL/SKIP for Supabase, Zetaris REST, each Nightshift lane and sample mode.

    python scripts/smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from app.adapters.nightshift import NightshiftClient  # noqa: E402
from app.adapters.supabase import SupabaseClient  # noqa: E402
from app.adapters.zetaris import ZetarisClient  # noqa: E402
from app.config import Settings, get_settings, load_city  # noqa: E402

results: list[tuple[str, str, str]] = []


def check(name: str, fn) -> None:
    try:
        verdict, detail = fn()
    except Exception as exc:  # report, never crash
        verdict, detail = "FAIL", f"{type(exc).__name__}: {exc}"
    results.append((verdict, name, detail))


def main() -> int:
    s = get_settings()

    check("city pack", lambda: ("PASS", load_city(s.city)["name"]))

    def supabase():
        sb = SupabaseClient(s)
        if not sb.configured:
            return "SKIP", "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set"
        return ("PASS", "auth health 200") if sb.health() else ("FAIL", "auth health not 200")

    check("supabase", supabase)

    def zetaris_live():
        if not s.zetaris_api_key:
            return "SKIP", "ZETARIS_API_KEY not set"
        live = Settings(**{**s.model_dump(), "sample_mode": False})
        r = ZetarisClient(live).named("q_ping", agent="smoke")
        ok = r.rows and str(r.rows[0][0]) == "1"
        return ("PASS" if ok else "FAIL"), f"SELECT 1 -> {r.rows} query_id={r.query_id} {r.ms} ms"

    check("zetaris REST", zetaris_live)

    if not s.meterless_runtime_token:
        results.append(("SKIP", "nightshift", "METERLESS_RUNTIME_TOKEN not set"))
    else:
        live = Settings(**{**s.model_dump(), "sample_mode": False})
        n = NightshiftClient(live)
        check("nightshift models", lambda: ("PASS", ", ".join(n.list_models()) or "(none listed)"))
        for lane in live.lanes:
            if lane == "embed":
                continue

            def one(lane=lane):
                r = n.chat(lane, [{"role": "user", "content": "Reply with the single word OK."}], agent="smoke", max_tokens=1024)
                return "PASS", f"pinned={r.model} routed={r.routed_model} receipt={r.receipt_id}"

            check(f"nightshift lane {lane}", one)

    def sample():
        ss = Settings(**{**s.model_dump(), "sample_mode": True, "zetaris_api_key": "", "zetaris_api_key_file": ""})
        r = ZetarisClient(ss).named("q_ping", agent="smoke")
        return ("PASS" if r.source == "sample" else "FAIL"), f"q_ping via {r.source}"

    check("sample mode (zetaris)", sample)

    width = max(len(n) for _, n, _ in results)
    for verdict, name, detail in results:
        print(f"{verdict:4}  {name.ljust(width)}  {detail}")
    return 1 if any(v == "FAIL" for v, _, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
