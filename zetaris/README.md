# Zetaris: sources, views, named queries

Agents read crime data only through Zetaris (rule R1). Everything here runs through `register.py`, one statement at a time, with a `--dry-run` that is sent to nexus-chief before any first-time CREATE (R12).

```bash
python zetaris/register.py --dry-run                          # print all statements, secrets masked
python zetaris/register.py --file 00_sources.sql --only 6     # run one statement
```

`register.py` reads secrets from files (`{{secret:NAME}}`) and city values from the city pack (`{{city:map.bounds.0}}`). It masks secrets in stdout and in `logs/zetaris-register-*.jsonl`.

## Files
| File | Owner | What |
|---|---|---|
| `00_sources.sql` | nexus-1 | `sb` = Supabase Postgres over the session pooler as `zetaris_reader` (SELECT only, no BYPASSRLS); tables, plus datasource views where JDBC can't map a type |
| `10_views.sql` | nexus-1 | semantic views (`nexus` container) |
| `20_dq.sql` | nexus-2 | data-quality views |
| `40_feeds.sql` | nexus-2 | REST news / social feeds |

## Live state (nexus-qa)
- `sb` is registered. Tables: crimes, crime_features, crime_vehicles, statements, evidence_media, case_diary, forensics, persons, person_links, missing_persons, section_map, public_incidents, link_alerts, link_factors, alert_decisions, series, series_members.
- Datasource views:
  - `stations` and `wards`: no PostGIS column, because geometry doesn't map over Spark JDBC.
  - `crime_features_v`: `text[]` and `jsonb` become JSON text on the source.
- `SELECT count(*) FROM sb.crimes` returns 14000.
- `tips` is **not** registered raw: it holds a passphrase hash and untrusted text. `zetaris_reader` has column-level SELECT on safe columns only (`0003_zetaris_reader_tips.sql`), and Zetaris reads the `tips_v` view of exactly those columns.

## Gotchas found while registering
- `DESCRIBE BY` text allows only letters, digits, space, `_ . , -`. No parentheses.
- Spark returns timestamps in UTC. Named queries convert them to city time with `from_utc_timestamp(col, <city tz>)`. The zone and offset come from the city pack, never from code.
- `render()` treats `:name` as a parameter, so SQL must not contain literal `:mm`-style time formats. Use `cast(... AS STRING)` instead.
- `q_case` takes 7–10 s cold. Still to check: whether `WHERE crime_id = …` is pushed down to Postgres.

## Object store (CSV / Parquet sources): limitation

> **`s3csv` and `s3pq` are NOT S3.** They are Lightning databases over Zetaris's **internal file store**
> (`file:/home/zetaris/customer-data/shared/nexus/`, D-022a). The names are kept from the spec so code and
> views don't change if the bucket path returns. `zetaris/stage_files.py` copies the generated files into
> that volume with `docker cp` (no container restart), and `01_files.sql` registers them: 12 tables, live
> 2026-10-26, counts in the PR.
Supabase Storage's S3-compatible endpoint works with standard S3 clients. The bucket is `nexus-chennai-data`, private, and boto3 SigV4 in `ap-southeast-1` lists it. But Zetaris's S3A client fails with `com.amazonaws.SdkClientException: Unable to execute HTTP request: Received fatal alert: handshake_failure` (hadoop-aws 3.3.5, aws-java-sdk 1.12.797). The container's OS TLS is fine, so the cause is the S3A JSSE channel. It most likely strips the GCM cipher suites the Cloudflare edge requires.

The team chose not to change the running container mid-build (D-022a). File sources therefore use Zetaris's internal file store, still registered as file sources, and the bucket stays a backup copy.

**To switch back later:** fix the S3A channel (for example `fs.s3a.ssl.channel.mode=default_jsse_with_gcm`, or a newer JDK/wildfly-openssl). Then set `s3Endpoint "ukrujnsjucwvytnokbtw.storage.supabase.co/storage/v1/s3"` and `useS3PathStyleAccess "true"` on the file tables, with keys `{{secret:s3_key_id}}` / `{{secret:s3_secret}}`. That is a one-line change per table in `00_sources.sql`.

## News and social feeds: the API must be up first (40_feeds.sql)
**Live runs need the Nexus API on :8000 before Zetaris reads feeds.** The `nexus_feeds.rest_news` / `rest_social` REST tables call `http://host.docker.internal:8000/mock-feeds/*` (`services/api/app/feeds.py`), both when they are registered and every time `nexus.news_items`, `nexus.social_posts` or `nexus.v_news_mentions` is queried. So a live `q_news` is a call from the API into Zetaris and back into the API.

- The API handlers are sync (`def`), so the callback is served on another threadpool thread. A single uvicorn worker is enough.
- `q_news` fails fast: one attempt with an 8 s timeout, no retries, then it is skipped for 60 s on that client (`NamedQuery.timeout_s`, `BREAKER_SECONDS`). Planner and Linker treat a failure as "no news" with a `step_failed` / `support_failed` trace line; it never fails a `/run`.
- Order for a live demo: start the API on port 8000 (`python run.py`), then register or query the feed views.
- Keep the default bind, 127.0.0.1. Docker Desktop forwards `host.docker.internal` to the host's loopback (checked 2026-10-26: `docker exec zetaris-driver-1 curl http://host.docker.internal:8000/mock-feeds/news?limit=1` returned 200 in 46 ms with the API on 127.0.0.1:8000). Do not bind 0.0.0.0.
