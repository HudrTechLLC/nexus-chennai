# Model-output fixtures (committed)

The generator makes every synthetic record, but two kinds of data come from the models. Live mode on
a judge's own Zetaris needs them, so they are committed here, small and synthetic (WS1-19, approved by
nexus-chief):

| File | Rows | What | Why it is needed |
|---|---|---|---|
| `crime_features_v.parquet` | one per generator crime with features | the Extractor's MO features (Nightshift output), in the exact columns and text form of `sb.crime_features_v`, plus `bundle_json`, the `features` text `sb.case_bundle_v` builds | the Extractor reuses features read through `q_features`, so a judge's machine does not re-extract every case |
| `tip_verdicts.parquet` | 40 | Tip Guard's `guard` verdict and the resulting `status` for each generator tip | `q_tip_corroboration` filters on status; without verdicts, tips corroborate nothing |
| `MANIFEST.json` | | export time, the commit it ran from, counts, extractor versions, tip statuses | provenance |

`data/fs_export.py` reads them; `python -m data.setup_live` loads them into Zetaris.

To re-export after a re-extraction (reads our QA database, so it needs the database password file):

    NEXUS_DB_PASSWORD="$(tr -d '\r\n' < <password file>)" python -m data.fixtures.export --gen data/generated

Only generator rows are exported: FIRs filed in the console stay in our database. Every row is synthetic.
