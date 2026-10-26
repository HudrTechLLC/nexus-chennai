-- zetaris/02_fs.sql · The crime data as files in Zetaris's own store (WS1-19). Owner: nexus-1 (data lane).
-- Runs only with `register.py --data files` (FILE_MODES). `python -m data.setup_live` builds the Parquet
-- (data/fs_export.py: same names, columns and Spark types as the sb objects they replace) and stages it with
-- zetaris/stage_files.py --fs under file:/home/zetaris/customer-data/shared/nexus/fs/<table>/.
-- With these, the named queries need no Supabase (adapters/zetaris_sources.py maps sb -> nexus_fs).
-- DESCRIBE BY text: letters, digits, spaces, commas and full stops only.

CREATE LIGHTNING DATABASE nexus_fs DESCRIBE BY "Nexus crime data as files, internal store";

CREATE LIGHTNING FILESTORE TABLE crimes FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/crimes/"
);

CREATE LIGHTNING FILESTORE TABLE statements FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/statements/"
);

CREATE LIGHTNING FILESTORE TABLE crime_vehicles FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/crime_vehicles/"
);

CREATE LIGHTNING FILESTORE TABLE evidence_media FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/evidence_media/"
);

CREATE LIGHTNING FILESTORE TABLE forensics FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/forensics/"
);

CREATE LIGHTNING FILESTORE TABLE crime_features_v FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/crime_features_v/"
);

CREATE LIGHTNING FILESTORE TABLE tips_v FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/tips_v/"
);

CREATE LIGHTNING FILESTORE TABLE section_map FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/section_map/"
);

CREATE LIGHTNING FILESTORE TABLE stations FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/stations/"
);

CREATE LIGHTNING FILESTORE TABLE link_alerts FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/link_alerts/"
);

CREATE LIGHTNING FILESTORE TABLE case_bundle_v FROM nexus_fs FORMAT PARQUET OPTIONS (
  path "file:///home/zetaris/customer-data/shared/nexus/fs/case_bundle_v/"
);

SELECT count(*) AS crimes FROM nexus_fs.crimes;
