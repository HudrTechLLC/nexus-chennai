---
tags: [nexus, architecture]
---

# City packs

Nexus is city-agnostic, and Chennai is the first city pack. To add a city, write a new pack and regenerate the data. No code changes are needed. Decision: [DECISIONS](DECISIONS.md) D-004.
Related: [ARCHITECTURE](ARCHITECTURE.md) · [SPEC](SPEC.md) · [00-INDEX](00-INDEX.md)

## Layout

```
cities/<city>/
├── city.yaml            # name, timezone, map centre/bounds, H3 resolution, Supabase/Vercel region
├── stations.geojson     # police stations with zone/district + jurisdiction polygons
├── wards.geojson        # wards/localities used for placement and the public map
├── law_sections.csv     # legacy ↔ current section mapping (Chennai: IPC ↔ BNS)
├── sources.yaml         # which feeds exist, their Zetaris source names and formats
├── generator/           # names, streets, vehicles, festivals, planted-series templates
└── i18n/                # UI strings, appeal templates
```

## What changes per city

| Area | What changes | Chennai |
|---|---|---|
| Police structure | Stations, zones and districts | 70 stations + Tambaram and Avadi |
| Map | Centre, bounds, wards | Chennai bounds |
| Synthetic data | Names, places, vehicles, calendar, series | Tamil names in English, Deepavali |
| Law codes | Section mapping | IPC → BNS from 1 Jul 2024 |
| Sources | Feed names and shapes | CCTNS exports, 100/112, ANPR |
| Language | UI and narrative language | English |
| Region | Hosting region | Mumbai |

## What never changes

Agents, scoring and weights, the Skeptic, H-MEM, Tip Guard, the database schema, RLS, screens and the Zetaris query logic.

## Another country

Also needs:

- new law-code mapping and record formats;
- source adapters for its data feeds;
- privacy rules ([SPEC Part J](SPEC.md#security)), such as tip retention and map fuzzing;
- possibly retuned crime categories and weights. Weight changes need team approval (R12).
