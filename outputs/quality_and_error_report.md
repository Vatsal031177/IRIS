# IRIS-SIG-47 Data Quality & Error Report

- **Task ID**: `IRIS-SIG-47`
- **Execution Mode**: `fixture`
- **Timestamp (UTC)**: `2026-10-28T13:15:00+00:00`
- **Destination Table**: `iris_staging.signal_ingest`

## Pipeline Telemetry Summary

| Metric | Count |
| :--- | ---: |
| HTML Pages Fetched | 2 |
| Raw DOM Candidate Cards Discovered | 11 |
| Malformed / Missing-Field Cards Rejected | 1 |
| In-Batch Duplicate Article IDs Skipped | 1 |
| Non-Target Domain Articles Filtered Out | 1 |
| **Valid Target Signals Normalized** | **8** |
| **Database Rows Upserted (`iris_staging.signal_ingest`)** | **8** |

## Spatial Resolution Breakdown (`EPSG:25832`)

| Location Status | Count | Handling Policy |
| :--- | ---: | :--- |
| `RESOLVED` | 5 | Transformed to `SRID=25832;POINT(Easting Northing)` |
| `AMBIGUOUS_MULTI_REGION` | 1 | `geom = NULL`, documented in `location_resolution_note` |
| `UNRESOLVED_NO_LOCATION` | 1 | `geom = NULL`, documented in `location_resolution_note` |
| `INVALID_COORDINATES_REJECTED` | 1 | `geom = NULL`, rejected and logged |

## Logged Validation & Scraping Errors

- `Record 999991 ('Defekter Eintrag ohne Publikationsdatum...') rejected: unverified/missing publication date.`
- `Record 254003: Explicit coordinates (195.999, -95.123) rejected: outside valid European WGS84 bounds or null island (0,0).`
