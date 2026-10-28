from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.common.config import Settings
from services.common.models import (
    LocationStatus,
    PipelineQualityReport,
    RawNewsArticle,
    SignalType,
)
from services.orchestrator.main import run_pipeline
from services.processor.classifier import DealFlowSignalClassifier
from services.processor.georesolver import PostGISGeoResolver
from services.scraper.harvester import InstitutionalMoneyHarvester


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_fixture_pipeline_end_to_end(tmp_path: Path) -> None:
    records, report = run_pipeline(
        mode="fixture",
        fixture_dir=FIXTURE_DIR,
        output_dir=tmp_path,
        skip_db=True,
    )

    # 11 DOM cards: 1 malformed (no date), 1 duplicate (254520), 1 non-target HR article -> 8 valid signals
    assert report.raw_articles_discovered == 11
    assert report.malformed_records_rejected == 1
    assert report.in_batch_duplicates_skipped == 1
    assert report.non_matching_domain_filtered == 1
    assert report.valid_signals_produced == 8
    assert len(records) == 8

    # Verify spatial statuses: 5 RESOLVED, 1 AMBIGUOUS_MULTI_REGION, 1 UNRESOLVED_NO_LOCATION, 1 INVALID_COORDINATES_REJECTED
    assert report.locations_resolved_25832 == 5
    assert report.locations_ambiguous == 1
    assert report.locations_unresolved == 1
    assert report.invalid_coordinates_rejected == 1

    # Verify output files were generated
    assert (tmp_path / "sample_signal_ingest.jsonl").exists()
    assert (tmp_path / "quality_and_error_report.md").exists()


def test_epsg_25832_coordinate_transformation() -> None:
    resolver = PostGISGeoResolver()
    report = PipelineQualityReport(
        run_timestamp_utc="2026-10-28T12:00:00Z", mode="test"
    )
    article = RawNewsArticle(
        source_record_id="254516",
        source_url="https://www.institutional-money.com/news/maerkte/headline/lbbw-am-sieht-chancen-bei-infrastruktur-und-private-debt-254516",
        title="LBBW AM sieht Chancen bei Infrastruktur und Private Debt",
        published_at=date(2026, 10, 20),
        category="maerkte",
        summary_text="LBBW Asset Management in Stuttgart sieht Chancen bei Infrastruktur.",
    )

    rec = resolver.resolve_and_normalize(
        article,
        SignalType.INSTITUTIONAL_ALLOCATION_MANDATE,
        ["institutionelle_private_markets"],
        report,
    )

    assert rec.location_status == LocationStatus.RESOLVED
    assert rec.geographic_context_raw == "Stuttgart, Baden-Württemberg, Germany"
    # Stuttgart (~9.1829 E, 48.7758 N) in UTM Zone 32N (EPSG:25832) is ~513,443m E, ~5,402,404m N
    assert rec.utm32_easting is not None and 513000 <= rec.utm32_easting <= 514000
    assert rec.utm32_northing is not None and 5402000 <= rec.utm32_northing <= 5403000
    assert rec.ewkt_25832.startswith("SRID=25832;POINT(")


def test_invalid_coordinates_are_never_silently_accepted() -> None:
    resolver = PostGISGeoResolver()
    report = PipelineQualityReport(
        run_timestamp_utc="2026-10-28T12:00:00Z", mode="test"
    )
    # Null Island (0, 0) must be rejected
    null_island_article = RawNewsArticle(
        source_record_id="900001",
        source_url="https://www.institutional-money.com/news/produkte/headline/test-900001",
        title="Test Infrastrukturfonds",
        published_at=date(2026, 10, 20),
        explicit_lon=0.0,
        explicit_lat=0.0,
    )
    rec = resolver.resolve_and_normalize(
        null_island_article,
        SignalType.INFRASTRUCTURE_FUND_LAUNCH,
        ["infrastrukturfonds"],
        report,
    )
    assert rec.location_status == LocationStatus.INVALID_COORDINATES_REJECTED
    assert rec.ewkt_25832 is None
    assert report.invalid_coordinates_rejected == 1


def test_idempotent_rerun_produces_identical_keys(tmp_path: Path) -> None:
    records_run_1, _ = run_pipeline(
        mode="fixture", fixture_dir=FIXTURE_DIR, output_dir=tmp_path, skip_db=True
    )
    records_run_2, _ = run_pipeline(
        mode="fixture", fixture_dir=FIXTURE_DIR, output_dir=tmp_path, skip_db=True
    )

    keys_1 = [(r.task_id, r.source_record_id, r.raw_payload_hash) for r in records_run_1]
    keys_2 = [(r.task_id, r.source_record_id, r.raw_payload_hash) for r in records_run_2]
    assert keys_1 == keys_2
    assert len(set(keys_1)) == len(keys_1)


def test_network_failure_and_empty_response_handling() -> None:
    settings = Settings(http_max_retries=1, http_timeout_seconds=2)
    harvester = InstitutionalMoneyHarvester(settings)
    report = PipelineQualityReport(
        run_timestamp_utc="2026-10-28T12:00:00Z", mode="live"
    )

    with patch.object(
        harvester.session,
        "get",
        side_effect=requests.ConnectionError("Simulated DNS/Socket timeout"),
    ):
        articles = harvester.harvest_live(report)
        assert articles == []
        assert len(report.errors) == 1
