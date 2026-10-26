-- 00 · Sources (spec E5). Run with: python zetaris/register.py --file 00_sources.sql
-- One statement at a time; each ends with ';' on its last line. Approved by nexus-chief (R12).

-- sb: Supabase Postgres (system of record) through the session pooler, read-only role
-- zetaris_reader (SELECT only, no BYPASSRLS; row policies grant it read on federated tables).
CREATE DATASOURCE sb DESCRIBE BY "Supabase Postgres nexus-qa, read-only role zetaris_reader" OPTIONS (
  jdbcdriver "org.postgresql.Driver",
  jdbcurl "jdbc:postgresql://aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require",
  username "zetaris_reader.ukrujnsjucwvytnokbtw",
  password "{{secret:zetaris_reader}}",
  fetchsize "1000"
);

-- Tables without PostGIS columns are imported as they are. `tips` is NOT imported raw: it holds
-- a passphrase hash and untrusted text, so agents see only the column-limited tips_v below.
REGISTER DATASOURCE TABLES ("crimes", "crime_features", "crime_vehicles", "statements", "evidence_media",
  "case_diary", "forensics", "persons", "person_links", "missing_persons", "section_map", "public_incidents",
  "link_alerts", "link_factors", "alert_decisions", "series", "series_members") FROM sb;

-- PostGIS geometry does not map over Spark JDBC, so geometry tables come in as views without it.
CREATE DATASOURCE VIEW stations FROM sb AS SELECT station_id, name, type, zone, district, region, synthetic FROM public.stations;

CREATE DATASOURCE VIEW wards FROM sb AS SELECT ward_no, name, zone FROM public.wards;

SELECT count(*) AS crimes FROM sb.crimes;

-- Postgres text[] arrives over JDBC as a '{...}' string, so features come through a view that
-- turns arrays and jsonb into JSON text on the source.
CREATE DATASOURCE VIEW crime_features_v FROM sb AS SELECT crime_id, extractor_version, mo::text AS mo, array_to_json(visual_tags)::text AS visual_tags, entities::text AS entities, model, receipt_id, confidence, (reviewed_by IS NOT NULL) AS reviewed_by_officer, synthetic FROM public.crime_features;
