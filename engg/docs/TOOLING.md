---
tags: [nexus, runbook]
---

# Development tooling

Skills, subagents, slash commands and hooks created under `.claude/` for building Nexus (spec O4). These are development aids only. None of them is in the product's request path, and the README's "AI and Model Usage" section mentions them.
Related: [SPEC Part O](SPEC.md#claude-code) · [validation](validation/README.md) · [00-INDEX](00-INDEX.md)

| Kind | Name | Purpose | Status |
|---|---|---|---|
| Slash command | `/gate <WS>` | Run the O6 gate, save `engg/docs/validation/<WS>-<date>.md` | ⏳ |
| Slash command | `/phase <P#>` | Load the phase brief and exit check from Part K | ⏳ |
| Subagent | `hackathon-judge` | Read-only rubric review that cites files and trace lines | ⏳ |
| Subagent | `security-reviewer` | Secret scan, RLS, anonymity of `/api/public/*` | ⏳ |
| Hook | PreToolUse Write/Edit | Block writes to `.env`, `*.pem`, `*.key` and files containing `nvapi-` | ⏳ |

Development aids also used: Claude Code (Anthropic) to build the code, and Supabase MCP for read-only schema checks.
