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
Supabase Storage's S3-compatible endpoint works with standard S3 clients. The bucket is `nexus-chennai-data`, private, and boto3 SigV4 in `ap-southeast-1` lists it. But Zetaris's S3A client fails with `com.amazonaws.SdkClientException: Unable to execute HTTP request: Received fatal alert: handshake_failure` (hadoop-aws 3.3.5, aws-java-sdk 1.12.797). The container's OS TLS is fine, so the cause is the S3A JSSE channel. It most likely strips the GCM cipher suites the Cloudflare edge requires.

The team chose not to change the running container mid-build (D-022a). File sources therefore use Zetaris's internal file store, still registered as file sources, and the bucket stays a backup copy.

**To switch back later:** fix the S3A channel (for example `fs.s3a.ssl.channel.mode=default_jsse_with_gcm`, or a newer JDK/wildfly-openssl). Then set `s3Endpoint "ukrujnsjucwvytnokbtw.storage.supabase.co/storage/v1/s3"` and `useS3PathStyleAccess "true"` on the file tables, with keys `{{secret:s3_key_id}}` / `{{secret:s3_secret}}`. That is a one-line change per table in `00_sources.sql`.
