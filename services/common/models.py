from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class SignalType(str, Enum):
    INFRASTRUCTURE_FUND_LAUNCH = "INFRASTRUCTURE_FUND_LAUNCH"
    INSTITUTIONAL_ALLOCATION_MANDATE = "INSTITUTIONAL_ALLOCATION_MANDATE"
    ESG_DEBT_ISSUANCE = "ESG_DEBT_ISSUANCE"


class LocationStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS_MULTI_REGION = "AMBIGUOUS_MULTI_REGION"
    UNRESOLVED_NO_LOCATION = "UNRESOLVED_NO_LOCATION"
    INVALID_COORDINATES_REJECTED = "INVALID_COORDINATES_REJECTED"


class RawNewsArticle(BaseModel):
    source_record_id: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=10)
    title: str = Field(..., min_length=3)
    published_at: date
    category: Optional[str] = None
    summary_text: Optional[str] = None
    explicit_lon: Optional[float] = None
    explicit_lat: Optional[float] = None


class NormalizedSignalRecord(BaseModel):
    task_id: str = "IRIS-SIG-47"
    source_name: str = "institutional-money.com"
    integration_pattern: str = "B (HTML)"
    source_record_id: str
    source_url: str
    title: str
    published_at: date
    category: Optional[str] = None
    signal_type: SignalType
    matched_keywords: List[str]
    summary_text: Optional[str] = None
    geographic_context_raw: Optional[str] = None
    location_status: LocationStatus
    location_resolution_note: str
    wgs84_lon: Optional[float] = None
    wgs84_lat: Optional[float] = None
    utm32_easting: Optional[float] = None
    utm32_northing: Optional[float] = None
    ewkt_25832: Optional[str] = None
    raw_payload_hash: str

    @field_validator("ewkt_25832")
    @classmethod
    def validate_ewkt_consistency(cls, v: Optional[str], info) -> Optional[str]:
        status = info.data.get("location_status")
        if status == LocationStatus.RESOLVED and not v:
            raise ValueError("RESOLVED location status requires a valid EPSG:25832 EWKT point.")
        if status != LocationStatus.RESOLVED and v is not None:
            raise ValueError("Non-RESOLVED location status must have NULL geometry.")
        return v


class PipelineQualityReport(BaseModel):
    task_id: str = "IRIS-SIG-47"
    run_timestamp_utc: datetime
    mode: str
    pages_fetched: int = 0
    raw_articles_discovered: int = 0
    malformed_records_rejected: int = 0
    in_batch_duplicates_skipped: int = 0
    non_matching_domain_filtered: int = 0
    valid_signals_produced: int = 0
    db_inserted_or_updated: int = 0
    locations_resolved_25832: int = 0
    locations_ambiguous: int = 0
    locations_unresolved: int = 0
    invalid_coordinates_rejected: int = 0
    errors: List[str] = Field(default_factory=list)
