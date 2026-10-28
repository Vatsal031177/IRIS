import json
import logging
from pathlib import Path
from typing import List

import psycopg
from services.common.models import NormalizedSignalRecord, PipelineQualityReport

logger = logging.getLogger("loader-service")

UPSERT_SIGNAL_SQL = """
INSERT INTO iris_staging.signal_ingest (
    task_id,
    source_name,
    integration_pattern,
    source_record_id,
    source_url,
    title,
    published_at,
    category,
    signal_type,
    matched_keywords,
    summary_text,
    geographic_context_raw,
    location_status,
    location_resolution_note,
    wgs84_lon,
    wgs84_lat,
    geom,
    raw_payload_hash,
    ingest_run_count,
    first_ingested_at,
    last_ingested_at
)
VALUES (
    %(task_id)s,
    %(source_name)s,
    %(integration_pattern)s,
    %(source_record_id)s,
    %(source_url)s,
    %(title)s,
    %(published_at)s,
    %(category)s,
    %(signal_type)s,
    %(matched_keywords)s,
    %(summary_text)s,
    %(geographic_context_raw)s,
    %(location_status)s,
    %(location_resolution_note)s,
    %(wgs84_lon)s,
    %(wgs84_lat)s,
    CASE
        WHEN %(ewkt_25832)s::text IS NOT NULL
        THEN ST_GeomFromEWKT(%(ewkt_25832)s::text)
        ELSE NULL
    END,
    %(raw_payload_hash)s,
    1,
    NOW(),
    NOW()
)
ON CONFLICT (task_id, source_record_id) DO UPDATE SET
    source_url               = EXCLUDED.source_url,
    title                    = EXCLUDED.title,
    published_at             = EXCLUDED.published_at,
    category                 = EXCLUDED.category,
    signal_type              = EXCLUDED.signal_type,
    matched_keywords         = EXCLUDED.matched_keywords,
    summary_text             = EXCLUDED.summary_text,
    geographic_context_raw   = EXCLUDED.geographic_context_raw,
    location_status          = EXCLUDED.location_status,
    location_resolution_note = EXCLUDED.location_resolution_note,
    wgs84_lon                = EXCLUDED.wgs84_lon,
    wgs84_lat                = EXCLUDED.wgs84_lat,
    geom                     = EXCLUDED.geom,
    raw_payload_hash         = EXCLUDED.raw_payload_hash,
    ingest_run_count         = iris_staging.signal_ingest.ingest_run_count + 1,
    last_ingested_at         = NOW();
"""


class PostGISSignalLoader:
    """
    Loads normalized signal records into PostgreSQL 16 / PostGIS 3.4
    table iris_staging.signal_ingest using repeatable, idempotent upserts.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn

    def upsert_records(
        self, records: List[NormalizedSignalRecord], report: PipelineQualityReport
    ) -> int:
        if not records:
            return 0

        upserted = 0
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for record in records:
                    params = record.model_dump()
                    params["signal_type"] = record.signal_type.value
                    params["location_status"] = record.location_status.value
                    cur.execute(UPSERT_SIGNAL_SQL, params)
                    upserted += 1
            conn.commit()

        report.db_inserted_or_updated = upserted
        return upserted

    @staticmethod
    def export_jsonl(records: List[NormalizedSignalRecord], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(
                    json.dumps(rec.model_dump(mode="json"), ensure_ascii=False) + "\n"
                )

    @staticmethod
    def write_quality_report(
        report: PipelineQualityReport, output_path: Path
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        error_lines = (
            "\n".join(f"- `{err}`" for err in report.errors)
            if report.errors
            else "- None"
        )
        md = f"""# IRIS-SIG-47 Data Quality & Error Report

- **Task ID**: `{report.task_id}`
- **Execution Mode**: `{report.mode}`
- **Timestamp (UTC)**: `{report.run_timestamp_utc.isoformat()}`
- **Destination Table**: `iris_staging.signal_ingest`

## Pipeline Telemetry Summary

| Metric | Count |
| :--- | ---: |
| HTML Pages Fetched | {report.pages_fetched} |
| Raw DOM Candidate Cards Discovered | {report.raw_articles_discovered} |
| Malformed / Missing-Field Cards Rejected | {report.malformed_records_rejected} |
| In-Batch Duplicate Article IDs Skipped | {report.in_batch_duplicates_skipped} |
| Non-Target Domain Articles Filtered Out | {report.non_matching_domain_filtered} |
| **Valid Target Signals Normalized** | **{report.valid_signals_produced}** |
| **Database Rows Upserted (`iris_staging.signal_ingest`)** | **{report.db_inserted_or_updated}** |

## Spatial Resolution Breakdown (`EPSG:25832`)

| Location Status | Count | Handling Policy |
| :--- | ---: | :--- |
| `RESOLVED` | {report.locations_resolved_25832} | Transformed to `SRID=25832;POINT(Easting Northing)` |
| `AMBIGUOUS_MULTI_REGION` | {report.locations_ambiguous} | `geom = NULL`, documented in `location_resolution_note` |
| `UNRESOLVED_NO_LOCATION` | {report.locations_unresolved} | `geom = NULL`, documented in `location_resolution_note` |
| `INVALID_COORDINATES_REJECTED` | {report.invalid_coordinates_rejected} | `geom = NULL`, rejected and logged |

## Logged Validation & Scraping Errors

{error_lines}
"""
        output_path.write_text(md, encoding="utf-8")
