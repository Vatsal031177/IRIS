iris-sig-47-harvester/
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── README.md
├── sql/
│   ├── 01_init_schema.sql
│   └── 02_validation_queries.sql
├── services/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── models.py
│   ├── scraper/
│   │   ├── __init__.py
│   │   └── harvester.py
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── classifier.py
│   │   └── georesolver.py
│   ├── loader/
│   │   ├── __init__.py
│   │   └── db_loader.py
│   └── orchestrator/
│       ├── __init__.py
│       └── main.py
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── listing_page_1.html
│   │   ├── listing_page_2_empty.html
│   │   └── article_details.json
│   └── test_pipeline.py
└── outputs/
    ├── sample_signal_ingest.jsonl
    └── quality_and_error_report.md
    
    
    # IRIS-SIG-47: Institutional Money Newsroom & Deal Flow Harvester

End-to-end microservices ingestion pipeline for **Task ID `IRIS-SIG-47`**, harvesting infrastructure fund launches, institutional allocation mandates, and ESG debt issuance from `https://www.institutional-money.com/news/` using **Integration Pattern B (HTML)** and persisting spatial records into **PostgreSQL 16 / PostGIS 3.4 (`iris_staging.signal_ingest`)**.

## 1. Source Verification & Mapping Assumptions

- **Source Endpoint**: `https://www.institutional-money.com/news/` (operated by FONDS professionell Multimedia GmbH) organizes articles under category paths (`/news/maerkte/`, `/news/produkte/`, `/news/vermischtes/`, `/news/regulierung/`).
- **Source Identifiers**: Canonical URLs follow the pattern `/news/{category}/headline/{slug}-{article_id}`. The numeric `{article_id}` (e.g., `254520`, `254516`, `254453`) is extracted and stored as `source_record_id`.
- **Publication Dates**: Verified directly from the `DD.MM.YYYY` German date stamp on newsroom items or ISO metadata (`YYYY-MM-DD`). Records lacking a verifiable publication date are rejected and logged.
- **Signal Classification**:
  - `INFRASTRUCTURE_FUND_LAUNCH`: Matches infrastructure funds (`Infrastrukturfonds`, `Infrastructure Fund`), renewable energy/grid/battery storage fund launches, and fund closings.
  - `INSTITUTIONAL_ALLOCATION_MANDATE`: Matches institutional capital commitments (`Kapitalzusagen`), pension fund (`Pensionskasse`, `Versorgungswerk`, `Pensionsvermögen`) allocation shifts, and Private Markets/Private Debt mandates.
  - `ESG_DEBT_ISSUANCE`: Matches `Green Bond`, `grüne Anleihe`, EU Green Bond Standard issuances, and ESG bond offerings.
- **Spatial Resolution (`EPSG:25832`)**:
  - Identified European municipal/headquarters locations (e.g., Stuttgart, Frankfurt am Main, Aurich, Luxembourg City) are transformed from `EPSG:4326` (WGS84) to `EPSG:25832` (ETRS89 / UTM Zone 32N) via `pyproj` and stored as `geometry(Point, 25832)`.
  - Multi-region stories (e.g., `"in den USA, andererseits in Europa"`) or multi-city mentions are flagged as `AMBIGUOUS_MULTI_REGION` with `geom = NULL`.
  - Articles without identifiable municipal context are flagged as `UNRESOLVED_NO_LOCATION` with `geom = NULL`.
  - Out-of-bounds coordinates or `(0, 0)` are rejected as `INVALID_COORDINATES_REJECTED` (`geom = NULL`) and logged in the quality report.

## 2. How to Run

### Option A: Local Python Execution (No Database Required)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run automated tests
pytest -v

# Run harvester against verified HTML fixtures (writes outputs/sample_signal_ingest.jsonl & report)
python -m services.orchestrator.main --mode fixture --skip-db
