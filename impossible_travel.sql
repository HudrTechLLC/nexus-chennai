-- Impossible travel: the same plate read by two ANPR cameras too far apart for the time between
-- reads (implied speed over 150 km/h). Standalone form of nexus.dq_impossible_travel, for the
-- Zetaris SQL editor. Cameras are CSV, so lat/lon are cast. One statement.
SELECT plate_text, camera_id_1, camera_id_2, read_at_1, read_at_2, distance_km, implied_kmh FROM (
  SELECT plate_text, prev_camera_id AS camera_id_1, camera_id AS camera_id_2,
         prev_read_at AS read_at_1, read_at AS read_at_2, distance_km,
         distance_km * 3600.0 / NULLIF((unix_timestamp(read_at) - unix_timestamp(prev_read_at)), 0) AS implied_kmh
  FROM (
    SELECT plate_text, prev_camera_id, camera_id, prev_read_at, read_at,
           2 * 6371 * asin(sqrt(pow(sin(radians(lat - prev_lat) / 2), 2) + cos(radians(prev_lat)) * cos(radians(lat)) * pow(sin(radians(lon - prev_lon) / 2), 2))) AS distance_km
    FROM (
      SELECT plate_text, camera_id, read_at, lat, lon,
             LAG(camera_id) OVER (PARTITION BY plate_text ORDER BY read_at) AS prev_camera_id,
             LAG(read_at) OVER (PARTITION BY plate_text ORDER BY read_at) AS prev_read_at,
             LAG(lat) OVER (PARTITION BY plate_text ORDER BY read_at) AS prev_lat,
             LAG(lon) OVER (PARTITION BY plate_text ORDER BY read_at) AS prev_lon
      FROM (
        SELECT r.plate_text, r.camera_id, r.read_at,
               CAST(c.lat AS DOUBLE) AS lat, CAST(c.lon AS DOUBLE) AS lon
        FROM s3pq.anpr_reads r
        LEFT JOIN s3csv.anpr_cameras c ON c.camera_id = r.camera_id
        WHERE r.plate_text IS NOT NULL) located
    ) sequenced
    WHERE prev_camera_id IS NOT NULL AND prev_camera_id <> camera_id) hopped
) speeds
WHERE implied_kmh > 150
ORDER BY plate_text, read_at_2, camera_id_2
