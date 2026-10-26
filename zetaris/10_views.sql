-- zetaris/10_views.sql · Semantic views (spec E5, WS1-12). Owner: nexus-1 (data lane).
-- Run with zetaris/register.py, one statement per call. Views live in schema-store container `nexus`
-- (created below; queried as nexus.<view>).
--
-- v_crime_unified: every crime Nexus knows, one row each, D3.1 flattened plus sections_raw.
-- Column list is pinned and identical to data/sample/views.sql (data/generator/sample.py UNIFIED_COLUMNS),
-- which tests/zetaris/test_views_sql.py checks. Consumers: q_hex_counts, nexus.dq_* (20_dq.sql), Linker.
-- Slice 1 is Supabase only. The legacy CCTNS CSVs and the archive parquet join this view (UNION ALL,
-- sections_raw set) once the internal-store file sources are registered (pending R12 batch).
-- jsonb columns arrive over JDBC as JSON strings; timestamps are Spark timestamps (UTC session).

-- Container for every semantic view (also in nexus-2's files; register.py skips "already exists").
CREATE SCHEMASTORE CONTAINER nexus;

CREATE OR REPLACE SCHEMASTORE VIEW v_crime_unified WITH CONTAINER nexus AS
SELECT crime_id, source, source_row_id, station_id, fir_no, category, sub_type, sections, occurred_from,
       occurred_to, reported_at, lat, lon, address, ward_no, h3_r9, h3_r8, geohash7, week, severity, property,
       weapon, offenders_described, victims, status, narrative, CAST(NULL AS STRING) AS sections_raw, synthetic
FROM sb.crimes;

SELECT count(*) AS n FROM nexus.v_crime_unified;
