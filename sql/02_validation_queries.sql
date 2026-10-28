-- 1. Verify signal distribution and idempotency counters (no duplicate rows on re-run)
SELECT
    task_id,
    signal_type,
    COUNT(*) AS distinct_records,
    SUM(ingest_run_count) AS total_upsert_touches,
    MIN(published_at) AS earliest_pub_date,
    MAX(published_at) AS latest_pub_date
FROM iris_staging.signal_ingest
WHERE task_id = 'IRIS-SIG-47'
GROUP BY task_id, signal_type
ORDER BY distinct_records DESC;

-- 2. Verify PostGIS EPSG:25832 geometries and inspect ETRS89 / UTM Zone 32N coordinates
SELECT
    source_record_id,
    signal_type,
    geographic_context_raw,
    location_status,
    ST_SRID(geom) AS srid,
    ROUND(ST_X(geom)::numeric, 2) AS utm32_easting_m,
    ROUND(ST_Y(geom)::numeric, 2) AS utm32_northing_m,
    ST_AsEWKT(geom) AS ewkt_25832
FROM iris_staging.signal_ingest
WHERE task_id = 'IRIS-SIG-47'
  AND geom IS NOT NULL
ORDER BY published_at DESC;

-- 3. Audit ambiguous, unresolved, or rejected coordinate records
SELECT
    source_record_id,
    title,
    geographic_context_raw,
    location_status,
    location_resolution_note,
    source_url
FROM iris_staging.signal_ingest
WHERE task_id = 'IRIS-SIG-47'
  AND location_status <> 'RESOLVED'
ORDER BY published_at DESC;

-- 4. Confirm zero duplicate (task_id, source_record_id) pairs exist
SELECT
    task_id,
    source_record_id,
    COUNT(*) AS row_count
FROM iris_staging.signal_ingest
GROUP BY task_id, source_record_id
HAVING COUNT(*) > 1;
