# Nexus Chennai · Claude Code instructions

Read `engg/docs/00-INDEX.md` first, then `engg/docs/SPEC.md` Part O, then Parts K and L, then `engg/docs/PROGRESS.md`.
In this repo every spec reference to `docs/` means `engg/docs/` (DECISIONS D-002).

- Project: Nexus Chennai, Open Agent Hackathon 2026, Track 1 (Solving Fragmented Intelligence).
- Deadline: 27 Oct 2026 23:45 UTC (28 Oct 05:15 IST). Submit ≥ 6 hours early.
- Official Rules win over this spec. Hackathon digest: engg/docs/hackathon/DIGEST.md.
- Build one phase at a time (Part K). Each phase has an exit check; run it.
- After each workstream, run /gate <WS> and save the report in engg/docs/validation/.
- Ground rules R1–R12 (Part O3) are non-negotiable: Zetaris for all agent reads,
  Nightshift with pinned Nemotron lanes for all model calls, no hardcoded outputs,
  no secrets, every claimed engine has a feature and a passing test, sample mode
  runs real logic, scores in code, tips are untrusted, no Cursor.
- Record every decision or verification in engg/docs/DECISIONS.md; update PROGRESS.md at session end.
- Any behaviour change updates the matching note in engg/docs/ in the same commit/PR.
- Nothing city-specific in code: it belongs in cities/<city>/ (D-004).
- You may create skills, subagents, slash commands and hooks under .claude/;
  document them in engg/docs/TOOLING.md.
- Ask before first-time Zetaris CREATE statements, deletions, weight changes or spend.
- Never put a secret in a commit, a command line or Vercel via a tool parameter.
- Stack: Next.js (apps/web, port 3001, also on Vercel), FastAPI + LangGraph (services/api, port 8000),
  Supabase (system of record), Zetaris (REST 8888), Nightshift (8088).
- Commands: python run.py · pytest -q · python -m data.generator --seed 42 ·
  python zetaris/register.py --dry-run · python -m app.eval · docker compose up
