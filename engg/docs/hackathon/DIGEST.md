---
tags: [nexus, research]
---

# Hackathon digest

Copied from [SPEC O5](../SPEC.md#claude-code) on 2026-10-26. **Official Rules win** over this digest and the spec; the official PDFs were saved locally on 2026-10-26 and checked in [RULES_CHECK](RULES_CHECK.md); log any conflict in [DECISIONS](../DECISIONS.md).
Related: [RULES_CHECK](RULES_CHECK.md) · [DELIVERABLES](../DELIVERABLES.md) · [00-INDEX](../00-INDEX.md)




**Event:** Open Agent Hackathon 2026, organised by GenAI Works on HackOS. Build window 22 Oct 2026 00:00 UTC → **27 Oct 2026 23:45 UTC (28 Oct 05:15 IST), hard deadline**. Judging from 28 Oct; results 6 Nov 16:00 UTC. Teams 1–5; roster locks when the first submission is created. One primary track per submission.

**Tracks:** 1 Solving Fragmented Intelligence (ours): "demonstrate a clever ability to discover and work across fragmented data sources". 2 The Agent That Can Explain Why. 3 Reasoning Architecture. Bonus Wildcard \[Tinkerer\].

**Required sponsor technology (missing any = not eligible):**
- Zetaris as the data layer (local Docker install from Zetaris Cloud, or AWS).
- At least one Meterless Engine (H-MEM, Markovian, World Model or Scout Intent) **in a working feature, with a passing test**.
- Meterless Nightshift as the app's primary AI provider (OpenAI-compatible; NVIDIA key lives only in Nightshift's Providers tab).
- NVIDIA wherever it contributes. **DGX Spark award ($4,699)**: a Nemotron model through Nightshift in a working feature, and show which model handled each request (`meterless/auto` can route elsewhere, so pin and log).
- Cursor is optional (official rules). Some older documents call it "required"; the Official Rules updated 24 Oct say optional. We do not use it and say so.

**Scoring (100):** Impact 30 · Technical 20 · Innovation 15 · Demo 15 · Product & UX 10 · Sponsor Tech 10. Ties → Impact, then earlier submission.

**Judges reward:** agents that do real work; critique, retries, branching, recovery; shared state; reliable execution; clear logs; usable output; sponsor tech that is load-bearing. **Judges discount:** UI polish without depth; single agent presented as many; fixed A→B→C pipelines; hardcoded demo paths; broad concepts with weak implementation; unsupported claims; sponsor tech bolted on.

**Required submission components:** 1. Demo video, 1–4 minutes: problem, main workflow, how the agent solves the track, key features, and how Zetaris and Meterless are integrated (agent querying Zetaris, the feature the engine powers, one real request through Nightshift). 2. Slide deck covering 8 points: problem and target users; solution; agent workflow / architecture; technical stack; how Zetaris and Meterless were used; what was unique about the sponsor tech use; product visuals; future enhancements. 3. Public GitHub repo with README (setup, usage, dependencies). 4. Sponsor technology explanation: Zetaris integration; which Meterless engines, what each does and the test; how the app connects to Nightshift; where NVIDIA contributes; what was unique. (The form also has a Cursor field.) 5. Pre-existing components declared in the form.

**Strongly recommended:** programmatic entry (`run.py`, `POST /run`), Docker, JSONL traces in `logs/` and stdout, ≥3 sample inputs and real outputs, `SAMPLE_MODE=true` that works with Zetaris and Nightshift stopped and no credentials, timeouts and capped loops, `.env.example`, `metadata.json` naming sponsor use.

**Disqualifiers:** late submission; can't be run or evaluated; hardcoded outputs or no real agent logic; no evidence of how the agent reached output; missing Zetaris / Meterless Engine / Nightshift; committed secrets; unauthorised personal or confidential data; undeclared pre-existing work; misrepresentation; team can't explain its code; duplicate accounts.

**Data rules:** public data with licences or clearly labelled synthetic data; no real personal data; Zetaris can't read laptop files (use S3); keep the repo light.

**Help:** #help desk on HackOS (`hackathon.genai.works/messages`), sponsor Help channels (Help Zetaris, Help Meterless, Help NVIDIA), mentor office hours, rules questions to hackathons@genai.works.

### Resource links

| Resource | Link |
| --- | --- |
| Event platform (HackOS) | https://hackathon.genai.works |
| Resource Center (login) | https://hackathon.genai.works/resources |
| Help desk channel (login) | https://hackathon.genai.works/messages |
| Rules questions | hackathons@genai.works |
| Official docs to save locally | Official Rules · Submission Requirements · Technical Execution Requirements · Disqualification Checklist · Strong / Weak Submission Examples · AI Usage Policy · Demo Video Guide · Submission Form Preview · Participant Setup Guide · Meterless README, Engines Index, World Model, H-MEM, Markovian (all in the Resource Center) |
| Zetaris Cloud sign-up | https://cloud.enterprise.zetaris.com/register |
| Zetaris platform download (Run locally) | https://cloud.enterprise.zetaris.com/dashboard/download |
| Zetaris getting-started repo | https://github.com/zetaris/getting-started |
| Zetaris guides website | https://zetaris.github.io/getting-started |
| Zetaris managed AWS cluster guide | https://zetaris.github.io/getting-started/docs/install/managed-aws-cluster-guide.html |
| Zetaris local API reference (after install) | http://localhost:8888/redoc/index.html |
| Meterless (Nightshift download) | https://meterless.ai |
| Meterless engine prompts (IDEATE / IMPLEMENT / COMBINE / HARDEN / POWER) | https://meterless.ai/engines.html |
| Meterless open-source engines | https://github.com/Meterless/Meterless |
| NVIDIA model catalog and API keys | https://build.nvidia.com/models |
| NVIDIA API base (only inside Nightshift) | https://integrate.api.nvidia.com/v1 |
| BUILD workshop recording (from setup guide) | https://youtu.be/Qxg5xCJIAcQ |
| Supabase dashboard / docs | https://supabase.com/dashboard · https://supabase.com/docs |
| ElevenLabs API docs | https://elevenlabs.io/docs |
| Open-Meteo (weather, no key) | https://open-meteo.com |
| OpenStreetMap / Overpass | https://www.openstreetmap.org · https://overpass-turbo.eu |
| deck.gl / MapLibre | https://deck.gl · https://maplibre.org |
| Docker Desktop | https://docs.docker.com/get-docker |

