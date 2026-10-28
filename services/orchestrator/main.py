import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from services.common.config import get_settings
from services.common.models import NormalizedSignalRecord, PipelineQualityReport
from services.loader.db_loader import PostGISSignalLoader
from services.processor.classifier import DealFlowSignalClassifier
from services.processor.georesolver import PostGISGeoResolver
from services.scraper.harvester import InstitutionalMoneyHarvester

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")


def run_pipeline(
    mode: str = "fixture",
    fixture_dir: Path = Path("tests/fixtures"),
    output_dir: Path = Path("outputs"),
    skip_db: bool = False,
) -> Tuple[List[NormalizedSignalRecord], PipelineQualityReport]:
    settings = get_settings()
    report = PipelineQualityReport(
        task_id=settings.task_id,
        run_timestamp_utc=datetime.now(timezone.utc),
        mode=mode,
    )

    harvester = InstitutionalMoneyHarvester(settings)
    classifier = DealFlowSignalClassifier()
    georesolver = PostGISGeoResolver()

    if mode == "fixture":
        raw_articles = harvester.harvest_from_fixtures(fixture_dir, report)
    elif mode == "live":
        raw_articles = harvester.harvest_live(report)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    normalized_records: List[NormalizedSignalRecord] = []
    for article in raw_articles:
        classification = classifier.classify(article)
        if classification is None:
            report.non_matching_domain_filtered += 1
            continue

        signal_type, matched_keywords = classification
        record = georesolver.resolve_and_normalize(
            article=article,
            signal_type=signal_type,
            matched_keywords=matched_keywords,
            report=report,
        )
        normalized_records.append(record)

    report.valid_signals_produced = len(normalized_records)

    # Export JSONL and Markdown Quality Report
    PostGISSignalLoader.export_jsonl(
        normalized_records, output_dir / "sample_signal_ingest.jsonl"
    )
    if not skip_db:
        loader = PostGISSignalLoader(settings.postgres_dsn)
        loader.upsert_records(normalized_records, report)

    PostGISSignalLoader.write_quality_report(
        report, output_dir / "quality_and_error_report.md"
    )
    logger.info(
        "Pipeline completed: %d valid signals, %d resolved to EPSG:25832.",
        report.valid_signals_produced,
        report.locations_resolved_25832,
    )
    return normalized_records, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IRIS-SIG-47 Institutional Money Deal Flow Harvester"
    )
    parser.add_argument(
        "--mode",
        choices=["fixture", "live"],
        default="fixture",
        help="Run against verified HTML fixtures or live institutional-money.com/news/",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/fixtures"),
        help="Path to HTML fixtures directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for JSONL output and quality report",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Run extraction, classification, and EPSG:25832 resolution without PostgreSQL connection",
    )
    args = parser.parse_args()
    run_pipeline(
        mode=args.mode,
        fixture_dir=args.fixture_dir,
        output_dir=args.output_dir,
        skip_db=args.skip_db,
    )


if __name__ == "__main__":
    main()
