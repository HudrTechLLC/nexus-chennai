# Nexus Chennai

**Track 1 · Solving Fragmented Intelligence** · Open Agent Hackathon 2026 · team Heisenbugs

Nexus is a city-wide crime-linking system. Agents running on NVIDIA Nemotron through Meterless Nightshift read every case, tip, CCTV still and news report through **Zetaris**. They raise link alerts for crimes that are probably related across police stations. Each alert has a weighted confidence, evidence for every reason and a recommended joint action. A Skeptic agent re-checks every link against the source rows before a human decides.

> **Status: in development.** This README is completed in phase P10. All data in this repository is **synthetic** (`synthetic: true`). No real people, cases or police systems are involved.

## Docs
Everything about the project lives in [`engg/docs/`](engg/docs/00-INDEX.md):
- [spec](engg/docs/SPEC.md)
- [architecture](engg/docs/ARCHITECTURE.md)
- [decisions](engg/docs/DECISIONS.md)
- [progress](engg/docs/PROGRESS.md)
- [deliverables](engg/docs/DELIVERABLES.md)
- [setup](engg/docs/SETUP.md)

## Sponsor technology
Zetaris (data layer) · Meterless Nightshift (primary AI provider) · Meterless engines · NVIDIA Nemotron. Details: [SPONSOR_TECH](engg/docs/SPONSOR_TECH.md).

## AI and model usage
- Product model calls go only through Meterless Nightshift with pinned Nemotron lanes.
- Claude Code (Anthropic) was used as a development tool and is not in the product's request path.
- Cursor was not used.
