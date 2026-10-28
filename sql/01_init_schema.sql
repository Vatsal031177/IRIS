-- PostgreSQL 16 / PostGIS 3.4 Schema Initialization for IRIS-SIG-47
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS iris_staging;

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest (
    ingest_id               BIGSERIAL PRIMARY KEY,
    task_id                 VARCHAR(32) NOT NULL DEFAULT 'IRIS-SIG-47',
    source_name             VARCHAR(128) NOT NULL DEFAULT 'institutional-money.com',
    integration_pattern     VARCHAR(16) NOT NULL DEFAULT 'B (HTML)',
    source_record_id        VARCHAR(64) NOT NULL,
    source_url              TEXT NOT NULL,
    title                   TEXT NOT NULL,
    published_at            DATE NOT NULL,
    category                VARCHAR(64),
    signal_type             VARCHAR(64) NOT NULL CHECK (
                                signal_type IN (
                                    'INFRASTRUCTURE_FUND_LAUNCH',
                                    'INSTITUTIONAL_ALLOCATION_MANDATE',
                                    'ESG_DEBT_ISSUANCE'
                                )
                            ),
    matched_keywords        TEXT[] NOT NULL DEFAULT '{}',
    summary_text            TEXT,
    geographic_context_raw  VARCHAR(255),
    location_status         VARCHAR(64) NOT NULL CHECK (
                                location_status IN (
                                    'RESOLVED',
                                    'AMBIGUOUS_MULTI_REGION',
                                    'UNRESOLVED_NO_LOCATION',
                                    'INVALID_COORDINATES_REJECTED'
                                )
                            ),
    location_resolution_note TEXT,
    wgs84_lon               DOUBLE PRECISION CHECK (wgs84_lon IS NULL OR (wgs84_lon BETWEEN -180.0 AND 180.0)),
    wgs84_lat               DOUBLE PRECISION CHECK (wgs84_lat IS NULL OR (wgs84_lat BETWEEN -90.0 AND 90.0)),
    geom                     geometry(Point, 25832),
    raw_payload_hash        CHAR(64) NOT NULL,
    ingest_run_count        INTEGER NOT NULL DEFAULT 1,
    first_ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_iris_sig_47_source_record UNIQUE (task_id, source_record_id),
    CONSTRAINT chk_valid_geometry_state CHECK (
        (location_status = 'RESOLVED' AND geom IS NOT NULL AND ST_SRID(geom) = 25832)
        OR
        (location_status <> 'RESOLVED' AND geom IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_signal_ingest_geom
    ON iris_staging.signal_ingest USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_signal_ingest_signal_type
    ON iris_staging.signal_ingest (signal_type, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_ingest_location_status
    ON iris_staging.signal_ingest (location_status);
