---
tags: [nexus, testcases]
---

# WS5-08 · Final fresh-clone validation (L3): checklist

This is the step-by-step run for **Tue 27 Oct, morning**, before the 12:00 IST freeze. It covers every item in the Disqualification Checklist ([RULES_CHECK](../hackathon/RULES_CHECK.md)) and SPEC [L3](../SPEC.md#deliverables). Each step gives the exact command and the result that counts as **PASS**. Write the results to `engg/docs/validation/WS5-08-2026-10-27.md` (one line per step: PASS/FAIL + evidence) and add a row to [validation/README](README.md).
Related: [README](README.md) · [Results](WS5-08-2026-10-27.md) · [RULES_CHECK](../hackathon/RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md) · [EVIDENCE](../submission/EVIDENCE.md) · [00-INDEX](../00-INDEX.md)

**Conventions**
- Commands are bash (Git Bash on Windows). Run them from the fresh clone's root unless the step says otherwise.
- `<run_id>` comes from the `run_id` field of the `/run` response.
- **Do not stop or start Zetaris, Nightshift or Docker containers yourself.** nexus-chief owns that slot (LANES §3.7). Steps that need them stopped say **[chief]**.
- A step that FAILs is reported to nexus-chief at once. Don't fix things inside the validation clone.

## 0 · Preconditions

| # | Command | PASS when |
|---|---|---|
| 0.1 | `git ls-remote https://github.com/HudrTechLLC/nexus-chennai.git main` | Prints the commit being validated. Write it down; every later step refers to it |
| 0.2 | Free RAM ≥ 4 GB for the docker build (Task Manager or `systeminfo \| findstr /C:"Available Physical Memory"`) | Enough headroom. If not, ask the chief before step 3 |

## 1 · Fresh clone, no secrets

| # | Command | PASS when |
|---|---|---|
| 1.1 | `D=$(mktemp -d) && cd "$D" && git clone -q https://github.com/HudrTechLLC/nexus-chennai.git && cd nexus-chennai && git log --oneline -1` | Clones; HEAD = the 0.1 commit |
| 1.2 | `ls .env 2>&1` | `No such file or directory` |
| 1.3 | `ls input_examples/example_*.json output_examples/` | 3 inputs and their real outputs (WS2-16) |
| 1.4 | `ls data/sample/sb data/sample/model_fixtures \| head` and `cat data/sample/MANIFEST.json` | Sample bundle present, `synthetic: true`, fixtures recorded from live Nightshift (WS1-11, WS2-16) |

## 2 · Secrets and repo hygiene (the CI `secrets` job, run by hand)

| # | Command | PASS when |
|---|---|---|
| 2.1 | `git ls-files \| grep -E '(^\|/)\.env$\|\.pem$\|\.key$'` | No output |
| 2.2 | `git grep -nE '(nvapi-[A-Za-z0-9_-]{20,}\|sk-[A-Za-z0-9]{20,}\|sb_secret_[A-Za-z0-9]{10,}\|eyJhbGciOi[A-Za-z0-9_-]{30,}\|BEGIN [A-Z ]*PRIVATE KEY)' -- . ':!engg/docs/SPEC.md'` | No output |
| 2.3 | `git ls-files \| grep -iE '\.pdf$\|\.dump$\|\.sql\.gz$'` | No output (the organiser PDFs stay local and gitignored) |
| 2.4 | `git ls-files -z \| xargs -0 du -k 2>/dev/null \| sort -rn \| head -5` | No tracked file over ~10 MB ("repo light") |
| 2.5 | `grep -rnE 'password\|passwd' README.md engg/docs/submission/*.md \| grep -v '<password>'` | No real credential. Demo accounts go in the form only |

## 3 · Docker judge path (the commands judges run)

| # | Command | PASS when |
|---|---|---|
| 3.1 | `docker build -t oah-submission .` | Builds from the repo root with no build args |
| 3.2 | `docker run -d --name nexus -p 8000:8000 -e SAMPLE_MODE=true oah-submission` | Container starts with **no `.env` and no credentials** |
| 3.3 | `for i in $(seq 1 30); do curl -fsS localhost:8000/health && break; sleep 2; done` | JSON with `"status":"ok"`, `"sample_mode":true`; `zetaris.state` = `sample`; nightshift has **no** `Illegal header value` error, and lanes list the D-017 ids |
| 3.4 | `for n in 1 2 3; do curl -s -o out_$n.json -w "ex$n HTTP %{http_code} %{time_total}s\n" -X POST localhost:8000/run -H "Content-Type: application/json" -d @input_examples/example_$n.json; done` | Every line says `HTTP 200`, each well under the 300 s deadline |
| 3.5 | `python -c "import json;[print(n, (d:=json.load(open(f'out_{n}.json')))['status'], d['output']['summary']) for n in (1,2,3)]"` | All `success`. Each matches `output_examples/example_N.json` on status, summary and every alert's pair/band/score (nexus-7 @ `de8e666`: ex 1 has 3 links, 2 high incl. Adyar ↔ Velachery 0.7887; ex 3 has a Skeptic drop) |
| 3.6 | `docker cp nexus:/repo/logs ./logs-docker && ls logs-docker/trace-*.jsonl \| wc -l` | One trace file per `/run` (≥ 3) |
| 3.7 | `docker rm -f nexus` | Container removed |

### 3b · Fully offline run (Tuesday morning, not the night before: RAM)

**Already passing in CI** as job `judge-offline` (#285, `b407bd8`; runs on every push to main, outputs uploaded as artifact `judge-offline-outputs`). On Tuesday, confirm the job is green on the commit being submitted; the manual steps below are the fallback.

Proves the judge path has **zero** dependency on Supabase, Zetaris or Nightshift: the container has no network at all. With `--network none` Docker ignores `-p`, so the host can't reach the API. Post the examples from **inside** the container with `docker exec`.

| # | Command | PASS when |
|---|---|---|
| 3.8 | Image from the fresh clone (1.1 / 3.1): `docker run -d --name nexus-off --network none -e SAMPLE_MODE=true oah-submission` | Container starts. `docker inspect -f '{{.HostConfig.NetworkMode}}' nexus-off` prints `none` |
| 3.9 | `for n in 1 2 3; do docker cp input_examples/example_$n.json nexus-off:/tmp/ex$n.json; done` | Copied |
| 3.10 | Wait for the API inside the container: `for i in $(seq 1 30); do docker exec nexus-off python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')" 2>/dev/null && break; sleep 2; done` then post each example: `for n in 1 2 3; do docker exec nexus-off python -c "import json,urllib.request as u; r=u.urlopen(u.Request('http://127.0.0.1:8000/run', data=open('/tmp/ex$n.json','rb').read(), headers={'Content-Type':'application/json'}), timeout=600); d=json.load(r); print($n, r.status, d['status'], d['output']['summary'][:100])"; done` | Each prints `200`, `success` and the same summary as in 3.5 |
| 3.11 | `docker logs nexus-off 2>&1 \| grep -ciE 'connection refused\|name resolution\|getaddrinfo\|timed out'` then `docker rm -f nexus-off` | `0`: no attempt to reach the network on the judge path. Container removed |

If 3.8–3.11 pass, add to the README Run / Sample mode section: **"The judge path runs fully offline: the sample-mode container answers all three examples with `--network none`."** with the commit validated. Don't add that line before it passes.

## 4 · Traces show how the agent got there

Run this check on **each** trace from step 3.6 (`for f in logs-docker/trace-*.jsonl; do …; done`):

```bash
python - "$f" <<'EOF'
import json, sys, collections
ev = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
agents = collections.Counter(e["agent_name"] for e in ev)
handoffs = [e["target_agent"] for e in ev if e.get("target_agent")]
queries = [q for e in ev for q in (e.get("zetaris_query_ids") or [])]
engines = collections.Counter(e["engine"] for e in ev if e.get("engine"))
models = [e for e in ev if e.get("model")]
critique = [e["action"] for e in ev if e["action"] in ("send_back", "drop", "plan") or (e.get("retry_count") or 0) > 0]
print("agents   ", dict(agents))
print("handoffs ", len(handoffs), handoffs[:6])
print("zetaris  ", len(queries), "query ids")
print("engines  ", dict(engines))
print("models   ", collections.Counter((e["model"], e["status"]) for e in models).most_common(3))
print("critique ", collections.Counter(critique))
print("errors   ", collections.Counter((e["action"], e["output_summary"][:60]) for e in ev if e["status"] == "error").most_common(5))
EOF
```

| # | Check | PASS when |
|---|---|---|
| 4.1 | ≥ 2 named agents | `agents` lists at least Extractor, Planner, Linker, Skeptic, Alert writer |
| 4.2 | Handoffs | `handoffs` > 0 (e.g. Extractor → Zetaris → Skeptic → Alert writer) |
| 4.3 | Critique / retry | At least one example shows a Skeptic `send_back` or `drop` (a `plan` round alone is not enough). Never expect or claim a `strike_factor`: none has occurred in any run |
| 4.4 | Zetaris queries | `zetaris` > 0 query ids. In sample mode the `zetaris_query` lines say `via=sample` |
| 4.5 | Engine activity | `engines` includes `hmem` (and `world_model` / `scout_intent` where used) |
| 4.6 | Model per request | Every `models` entry names a pinned `nvidia/…` id. In sample mode with fixtures, the status is `replayed`, **not** `error`. Without fixtures, it's `error` + "no recorded fixture", which is a FAIL for this step |
| 4.7 | No unexpected errors | `errors` has no `not a registered named query` and no `IO Error … news/articles.jsonl`. On a live run, `q_news` reads live rows (news feed registered, WS1-16); a `400 TABLE_OR_VIEW_NOT_FOUND` is a FAIL |
| 4.8 | Trace also on stdout/stderr | `docker logs nexus` (before 3.7) shows trace lines. Locally, `run.py --once` sends them to stderr |

## 5 · No hardcoded outputs: outputs differ across inputs

| # | Command | PASS when |
|---|---|---|
| 5.1 | `python -c "import json;print([sorted(tuple(a['crimes']) for a in json.load(open(f'out_{n}.json'))['output']['alerts']) for n in (1,2,3)])"` | Three different alert sets |
| 5.2 | `curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"input":{"kind":"case","crime_id":"CHN-KU-2025-000082"}}'` (run before 3.7, or on the venv server in 6.3) | A different, real result for a case that isn't an example, so outputs aren't keyed to example ids |
| 5.3 | `curl -s -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"input":{"kind":"case"}}' -w "\n%{http_code}\n"` | `422` (bad input is refused, never answered with a made-up result) |
| 5.4 | `git grep -nE 'example_[123]' services/api/app` | No output: no example-specific branch in product code |

## 6 · Sample mode with `.env` removed and Zetaris + Nightshift stopped (venv path)

| # | Command | PASS when |
|---|---|---|
| 6.1 | **[chief]** stop Zetaris and Nightshift. Then: `curl -s -m 3 localhost:8888 ; curl -s -m 3 127.0.0.1:8088/v1/models` | Both fail to connect |
| 6.2 | `python -m venv .venv && .venv/Scripts/pip install -q -r requirements.txt` (macOS/Linux: `.venv/bin/pip`) | Installs with no errors (≈ 3 min; includes `tzdata`) |
| 6.3 | `rm -f .env; for n in 1 2 3; do SAMPLE_MODE=true .venv/Scripts/python run.py --once input_examples/example_$n.json 2>err_$n.txt \| python -c "import json,sys;d=json.load(sys.stdin);print($n,d['status'],d['output']['summary'])"; done` | stdout is pure JSON (the parse works) and all `success`. Results match step 3.5 |
| 6.4 | `SAMPLE_MODE=true .venv/Scripts/python run.py` in one shell, then `curl -s localhost:8000/health` | `/health` answers within ~5 s; every adapter is `sample` |
| 6.5 | Run the step 4 script on the new `logs/trace-*.jsonl` | Same PASS rules as section 4 (models `replayed`) |
| 6.6 | **[chief]** restart Zetaris and Nightshift | Both back up (`/health` with `.env` shows them `live`) |

## 7 · Live run (with `.env`), the L3 steps 1–3

| # | Command | PASS when |
|---|---|---|
| 7.1 | `cp .env.example .env`, then fill values **by file path** (`*_FILE` settings), never pasted | `.env` holds no secret values, only paths and placeholders |
| 7.2 | `docker compose up -d` (or `python run.py`), then `curl -s localhost:8000/health` | zetaris `live`, nightshift `live` with the lanes listed |
| 7.3 | POST example 1 to `/run`, then the step 4 script on its trace | Model events `ok` with a non-null `routed_model` and a `receipt_id`; `zetaris_query` lines say `via=zetaris` |
| 7.4 | `docker compose down` | Stack stopped |

## 8 · Engine tests (the Meterless requirement)

| # | Command | PASS when |
|---|---|---|
| 8.1 | `pip install -q -r services/api/requirements-dev.txt && pytest tests/engines -q` | All pass |
| 8.2 | `cd engines-ts && npm ci && npm run install:references && cd .. && node engines-ts/scripts/run-conformance.mjs` | World Model 8/8, H-MEM 13/13, Markovian 8/8 (`logs/conformance_*.txt`) |
| 8.3 | `cat logs/feature_scout_intent.txt` | Held-out route accuracy ≥ 0.9, injections all quarantined |
| 8.4 | CI on the validated commit: `gh run list --commit <sha>` (or the PR checks page) | `api`, `engines`, `judge-path`, `web`, `secrets` all green |

## 9 · README sections (Submission Requirements + Disqualification Checklist)

| # | Command | PASS when |
|---|---|---|
| 9.1 | `grep -nE '^## (Setup\|Run\|Sample mode vs live\|Agents\|Examples\|Limitations\|Sponsor technology\|Third-party code and pre-existing work\|Licences\|AI and model usage\|Responsible AI\|Traces and logs\|Tests\|Evaluation\|Live app)' README.md \| wc -l` | 15 |
| 9.2 | `grep -n 'hackathon.genai.works/resources' README.md` | The Participant Setup Guide link is present (Zetaris + Nightshift setup) |
| 9.3 | `grep -nE 'Python (3\.11\|3\.13)\|PowerShell\|tzdata' README.md \| head` | Dependencies and Windows notes present |
| 9.4 | `grep -n 'PENDING' README.md` | **No output at submission.** Video link, examples and eval filled in, or the sentence removed |
| 9.5 | `grep -rniE 'tamper-proof\|cannot forge\|strikes? (a\|any\|the) factor' README.md engg/docs/submission/*.md \| grep -viE 'not (read this as )?tamper-proof\|never\|none has'` | No output: no tamper-proof claim (the README states the evidence limit) and no claim of a Skeptic factor strike |
| 9.6 | Follow README "Setup → Option B" literally, as a new reader would | Every command works as written. Note any that needed a fix |

## 10 · Video, deck and links (manual)

| # | Check | PASS when |
|---|---|---|
| 10.1 | Open the GitHub repo URL in a **private window, logged out** | Public, and the README renders |
| 10.2 | Open the video link (YouTube unlisted + Drive backup) in a private window | Plays logged out; 1–4 min |
| 10.3 | Frame-by-frame scan of the video and every deck screenshot | No Nightshift Providers/Console tab, no terminal env output, no Supabase dashboard, no token, no `.env` |
| 10.4 | Compare the video narration with [VIDEO_SCRIPT](../submission/VIDEO_SCRIPT.md)'s "facts to re-check" table | Every spoken number matches the screen |
| 10.5 | `grep -rn 'PENDING:' engg/docs/submission/` | Only items the team chose to leave; none pasted into the form |
| 10.6 | Demo console logins (the 5 `@nexus.demo` accounts) | Before submission, decide with Ravee whether to rotate the demo passwords to stronger ones for judges. Credentials go only in the submission form, never in the repo |

## Result

All of sections 1–9 PASS, plus 10 once the video exists, means WS5-08 is done. Record the commit, the date, and PASS/FAIL per step in `WS5-08-2026-10-27.md`.
