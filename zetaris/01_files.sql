-- zetaris/01_files.sql · File sources (spec D1, E5; D-022a). Owner: nexus-1 (data lane).
-- The generator's bulk files live in Zetaris's internal file store, not in Postgres: placed by
-- zetaris/stage_files.py (docker cp into the customer-data volume, no restart) under
--   file:/home/zetaris/customer-data/shared/nexus/<layout below>
-- and registered here as Lightning file-store tables. One statement per call (register.py).
-- s3csv / s3pq keep their spec names so the bucket path can return later by changing `path` only.
-- DESCRIBE BY text: letters, digits, spaces, commas and full stops only.

CREATE LIGHTNING DATABASE s3csv DESCRIBE BY "Nexus CSV files, internal store";

CREATE LIGHTNING DATABASE s3pq DESCRIBE BY "Nexus Parquet files, internal store";

CREATE LIGHTNING FILESTORE TABLE cctv_cameras FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/cctv_cameras.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE anpr_cameras FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/anpr_cameras.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE vehicles FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/vehicles.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE releases FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/releases.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE history_sheets FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/history_sheets.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE place_aliases FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/place_aliases.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE calendar FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/calendar.csv", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE cctns FROM s3csv FORMAT CSV OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/cctns/", header "true", delimiter ","
);

CREATE LIGHTNING FILESTORE TABLE anpr_reads FROM s3pq FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/anpr/"
);

CREATE LIGHTNING FILESTORE TABLE calls FROM s3pq FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/calls/"
);

CREATE LIGHTNING FILESTORE TABLE archive FROM s3pq FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/archive/archive.parquet"
);

CREATE LIGHTNING FILESTORE TABLE osm_pois FROM s3pq FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/ref/osm_pois.parquet"
);

SELECT 'cctv_cameras' AS t, count(*) AS n FROM s3csv.cctv_cameras UNION ALL
SELECT 'anpr_cameras', count(*) FROM s3csv.anpr_cameras UNION ALL
SELECT 'vehicles', count(*) FROM s3csv.vehicles UNION ALL
SELECT 'releases', count(*) FROM s3csv.releases UNION ALL
SELECT 'history_sheets', count(*) FROM s3csv.history_sheets UNION ALL
SELECT 'place_aliases', count(*) FROM s3csv.place_aliases UNION ALL
SELECT 'calendar', count(*) FROM s3csv.calendar UNION ALL
SELECT 'cctns', count(*) FROM s3csv.cctns UNION ALL
SELECT 'anpr_reads', count(*) FROM s3pq.anpr_reads UNION ALL
SELECT 'calls', count(*) FROM s3pq.calls UNION ALL
SELECT 'archive', count(*) FROM s3pq.archive UNION ALL
SELECT 'osm_pois', count(*) FROM s3pq.osm_pois;
