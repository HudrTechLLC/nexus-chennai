# Judge inputs (synthetic)

Each file is a `POST /run` body (spec Part H). Run one with:

    python run.py --once input_examples/example_1.json
    # or, with the API running:
    curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d @input_examples/example_1.json

`sample_mode: true` runs the same agent graph over the bundled `data/sample/` (Zetaris named queries run on
DuckDB twins) and replays model output recorded from live Nightshift calls. Nothing here is a canned answer:
scores, Skeptic strikes and alerts are computed by the agents on each run. The matching real outputs are
in `output_examples/`.

| File | Input | Shows |
|---|---|---|
| example_1.json | case CHN-AD-2026-001182 | Red Pulsar Duo: 3 cross-station links (2 high) on MO, space-time, suspect description and vehicle (partial plate + ANPR, re-checked by the Skeptic); a 4-case series "Red two-wheeler chain snatchings · 3 stations" |
| example_2.json | case CHN-KU-2025-000078 | Grille Cutters: 7 links (6 cross-station) on space-time, suspect description and the weapon/tool factor; an 8-case series "Night house breaks · 6 stations" |
| example_3.json | batch of 3 cases | Night Cab (fake cab, knife, white Swift Dzire): a batch run, 2 cross-station links with vehicle and weapon/tool factors, 1 weak pair dropped |

## Live runs (not needed for judging)

With Zetaris and Nightshift running and `.env` set, drop `"sample_mode": true` to run against live services.
For live API and worker runs, set `ENGINES_PERSIST=supabase` so World Model and H-MEM state is written to the
`wm_*` / `hmem_*` tables the police console reads. Leave it empty (the default) for tests and sample mode:
there the engines keep their state in memory.
