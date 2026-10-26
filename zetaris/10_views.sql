-- zetaris/10_views.sql · Semantic views (spec E5, WS1-12). Owner: nexus-1 (data lane).
-- Run with zetaris/register.py, one statement per call. Views live in schema-store container `nexus`
-- (created below; queried as nexus.<view>).
--
-- v_crime_unified: every crime Nexus knows, one row each, D3.1 flattened plus sections_raw.
-- Column list is pinned and identical to data/sample/views.sql (data/generator/sample.py UNIFIED_COLUMNS),
-- which tests/zetaris/test_views_sql.py checks. Consumers: q_hex_counts, nexus.dq_* (20_dq.sql), Linker.
-- Slice 2: Supabase + legacy CCTNS CSVs (s3csv.cctns) + archive parquet (s3pq.archive), UNION ALL.
--   station: the legacy export has no modern station id, so it is matched by locality (CCTNS: last part of
--            PLACE_OCC; archive: station_name) to the station name without its "(code)" suffix.
--   category: from the (sub_type, category) pairs Supabase already uses.
--   sections_raw: the legacy section text, set only when a token is in neither section_map.ipc_code nor
--            bns_code (CCTNS ',' separated; archive ';' separated, bare IPC numbers), for dq_unmapped_sections.
--   times: legacy local times, converted to UTC timestamps like the Supabase columns. CCTNS FIR_DT is a date
--            only, so reported_at is the END of that day (23:59:59 city time): never earlier than a same-day
--            occurrence, which would read as time_inconsistent.
-- jsonb columns arrive over JDBC as JSON strings; timestamps are Spark timestamps (UTC session).

-- Container for every semantic view (also in nexus-2's files; register.py skips "already exists").
CREATE SCHEMASTORE CONTAINER nexus;

CREATE OR REPLACE SCHEMASTORE VIEW v_crime_unified WITH CONTAINER nexus AS
WITH codes AS (
  SELECT ipc_code AS code FROM sb.section_map WHERE ipc_code IS NOT NULL
  UNION SELECT bns_code AS code FROM sb.section_map WHERE bns_code IS NOT NULL),
cats AS (SELECT DISTINCT sub_type, category FROM sb.crimes WHERE sub_type IS NOT NULL),
st AS (SELECT station_id, lower(substring_index(name, ' (', 1)) AS locality FROM sb.stations),
cctns_unmapped AS (
  SELECT t.rid, max(CASE WHEN k.code IS NULL THEN 1 ELSE 0 END) AS unmapped
  FROM (SELECT concat(PS_CODE, ':', FIR_NUM) AS rid, trim(tok) AS tok
        FROM s3csv.cctns LATERAL VIEW explode(split(ACT_SEC, ',')) x AS tok) t
  LEFT JOIN codes k ON k.code = t.tok GROUP BY t.rid),
archive_unmapped AS (
  SELECT t.case_ref, max(CASE WHEN k.code IS NULL THEN 1 ELSE 0 END) AS unmapped
  FROM (SELECT case_ref, trim(tok) AS tok FROM s3pq.archive LATERAL VIEW explode(split(ipc_sections, ';')) x AS tok) t
  LEFT JOIN codes k ON k.code = CASE WHEN t.tok LIKE 'BNS%' THEN t.tok ELSE concat('IPC ', t.tok) END
  GROUP BY t.case_ref)
SELECT crime_id, source, source_row_id, station_id, fir_no, category, sub_type, sections, occurred_from,
       occurred_to, reported_at, lat, lon, address, ward_no, h3_r9, h3_r8, geohash7, week, severity, property,
       weapon, offenders_described, victims, status, narrative, CAST(NULL AS STRING) AS sections_raw, synthetic
FROM sb.crimes
UNION ALL
SELECT concat('CCTNS-', c.PS_CODE, '-', replace(c.FIR_NUM, '/', '-')) AS crime_id, 's3csv.cctns' AS source,
       concat(c.PS_CODE, ':', c.FIR_NUM) AS source_row_id, s.station_id, c.FIR_NUM AS fir_no, m.category,
       lower(replace(c.MINOR_HEAD, ' ', '_')) AS sub_type, CAST(NULL AS STRING) AS sections,
       to_utc_timestamp(to_timestamp(c.OCC_DT_FROM, 'dd-MM-yyyy HH:mm'), '{{city:timezone}}') AS occurred_from,
       to_utc_timestamp(to_timestamp(c.OCC_DT_TO, 'dd-MM-yyyy HH:mm'), '{{city:timezone}}') AS occurred_to,
       to_utc_timestamp(to_timestamp(concat(c.FIR_DT, ' 23:59:59'), 'dd-MM-yyyy HH:mm:ss'), '{{city:timezone}}') AS reported_at,
       CAST(c.LAT AS DOUBLE) AS lat, CAST(c.LONG AS DOUBLE) AS lon, c.PLACE_OCC AS address,
       CAST(NULL AS INT) AS ward_no, CAST(NULL AS STRING) AS h3_r9, CAST(NULL AS STRING) AS h3_r8,
       CAST(NULL AS STRING) AS geohash7, CAST(NULL AS STRING) AS week, CAST(NULL AS SMALLINT) AS severity,
       CAST(NULL AS STRING) AS property, CAST(NULL AS STRING) AS weapon, CAST(NULL AS STRING) AS offenders_described,
       CAST(NULL AS STRING) AS victims, 'legacy' AS status, c.BRIEF_FACTS AS narrative,
       CASE WHEN u.unmapped = 1 THEN c.ACT_SEC END AS sections_raw, true AS synthetic
FROM s3csv.cctns c
LEFT JOIN st s ON s.locality = lower(trim(substring_index(c.PLACE_OCC, ',', -1)))
LEFT JOIN cats m ON m.sub_type = lower(replace(c.MINOR_HEAD, ' ', '_'))
LEFT JOIN cctns_unmapped u ON u.rid = concat(c.PS_CODE, ':', c.FIR_NUM)
UNION ALL
SELECT a.case_ref AS crime_id, 's3pq.archive' AS source, a.case_ref AS source_row_id, s.station_id,
       CAST(NULL AS STRING) AS fir_no, m.category, a.crime_subhead AS sub_type, CAST(NULL AS STRING) AS sections,
       to_utc_timestamp(to_timestamp(concat(a.date_of_occurrence, lpad(a.time_of_occurrence, 4, '0')), 'yyyyMMddHHmm'),
                        '{{city:timezone}}') AS occurred_from,
       CAST(NULL AS TIMESTAMP) AS occurred_to, CAST(NULL AS TIMESTAMP) AS reported_at, a.latitude AS lat,
       a.longitude AS lon, CAST(NULL AS STRING) AS address, CAST(NULL AS INT) AS ward_no, CAST(NULL AS STRING) AS h3_r9,
       CAST(NULL AS STRING) AS h3_r8, CAST(NULL AS STRING) AS geohash7, CAST(NULL AS STRING) AS week,
       CAST(NULL AS SMALLINT) AS severity, CAST(NULL AS STRING) AS property, CAST(NULL AS STRING) AS weapon,
       CAST(NULL AS STRING) AS offenders_described, CAST(NULL AS STRING) AS victims, a.disposal AS status,
       CAST(NULL AS STRING) AS narrative, CASE WHEN u.unmapped = 1 THEN a.ipc_sections END AS sections_raw,
       true AS synthetic
FROM s3pq.archive a
LEFT JOIN st s ON s.locality = lower(a.station_name)
LEFT JOIN cats m ON m.sub_type = a.crime_subhead
LEFT JOIN archive_unmapped u ON u.case_ref = a.case_ref;

SELECT source, count(*) AS n FROM nexus.v_crime_unified GROUP BY source ORDER BY source;
