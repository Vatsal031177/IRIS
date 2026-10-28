import hashlib
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pyproj import Transformer

from services.common.models import (
    LocationStatus,
    NormalizedSignalRecord,
    PipelineQualityReport,
    RawNewsArticle,
    SignalType,
)


@dataclass(frozen=True)
class GazetteerEntry:
    canonical_name: str
    wgs84_lon: float
    wgs84_lat: float
    aliases: Tuple[str, ...]


# Verified European / DACH Institutional Hub Gazetteer (WGS84 lon, lat)
GAZETTEER: List[GazetteerEntry] = [
    GazetteerEntry(
        canonical_name="Stuttgart, Baden-Württemberg, Germany",
        wgs84_lon=9.1829,
        wgs84_lat=48.7758,
        aliases=("stuttgart", "baden-württemberg", "lbbw asset management", "lbbw am"),
    ),
    GazetteerEntry(
        canonical_name="Frankfurt am Main, Hesse, Germany",
        wgs84_lon=8.6821,
        wgs84_lat=50.1109,
        aliases=("frankfurt", "prime capital", "universal investment", "dws"),
    ),
    GazetteerEntry(
        canonical_name="Aurich, Lower Saxony, Germany",
        wgs84_lon=7.4865,
        wgs84_lat=53.4705,
        aliases=("aurich", "ökorenta", "oekorenta"),
    ),
    GazetteerEntry(
        canonical_name="Grünwald (Munich), Bavaria, Germany",
        wgs84_lon=11.5236,
        wgs84_lat=48.0469,
        aliases=("grünwald", "kgal", "münchen", "munich"),
    ),
    GazetteerEntry(
        canonical_name="Berlin, Germany",
        wgs84_lon=13.4050,
        wgs84_lat=52.5200,
        aliases=("berlin",),
    ),
    GazetteerEntry(
        canonical_name="Hamburg, Germany",
        wgs84_lon=9.9937,
        wgs84_lat=53.5511,
        aliases=("hamburg", "berenberg"),
    ),
    GazetteerEntry(
        canonical_name="Luxembourg City, Luxembourg",
        wgs84_lon=6.1319,
        wgs84_lat=49.6116,
        aliases=("luxemburg", "luxembourg", "m&g european property fund"),
    ),
    GazetteerEntry(
        canonical_name="Vienna, Austria",
        wgs84_lon=16.3738,
        wgs84_lat=48.2082,
        aliases=("wien", "vienna"),
    ),
    GazetteerEntry(
        canonical_name="Zurich, Switzerland",
        wgs84_lon=8.5417,
        wgs84_lat=47.3769,
        aliases=("zürich", "zurich", "swiss life", "ubs"),
    ),
    GazetteerEntry(
        canonical_name="Paris, France",
        wgs84_lon=2.3522,
        wgs84_lat=48.8566,
        aliases=("paris", "amundi"),
    ),
]

MULTI_REGION_PATTERNS = re.compile(
    r"\b(usa\s+und\s+europa|in\s+den\s+usa,\s+andererseits\s+in\s+europa|kontinentaleuropa|weltweit|global|internationale[n]?\s+aktien)\b",
    re.I,
)


class PostGISGeoResolver:
    """
    Resolves geographic context from institutional news items and transforms valid
    WGS84 coordinates to EPSG:25832 (ETRS89 / UTM zone 32N).
    Enforces strict coordinate bounds checking so invalid coordinates are never silently accepted.
    """

    # Valid European domain envelope for EPSG:25832 point resolution
    MIN_LON, MAX_LON = -10.0, 32.0
    MIN_LAT, MAX_LAT = 34.0, 72.0

    def __init__(self) -> None:
        self._transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:25832", always_xy=True
        )

    def resolve_and_normalize(
        self,
        article: RawNewsArticle,
        signal_type: SignalType,
        matched_keywords: List[str],
        report: PipelineQualityReport,
    ) -> NormalizedSignalRecord:
        payload_hash = hashlib.sha256(
            json.dumps(
                {
                    "id": article.source_record_id,
                    "url": article.source_url,
                    "title": article.title,
                    "date": article.published_at.isoformat(),
                    "summary": article.summary_text or "",
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        # 1. Check if explicit coordinates were provided on the record and validate strictly
        if article.explicit_lon is not None or article.explicit_lat is not None:
            if not self._is_valid_coordinate_pair(
                article.explicit_lon, article.explicit_lat
            ):
                report.invalid_coordinates_rejected += 1
                note = (
                    f"Explicit coordinates ({article.explicit_lon}, {article.explicit_lat}) "
                    "rejected: outside valid European WGS84 bounds or null island (0,0)."
                )
                report.errors.append(
                    f"Record {article.source_record_id}: {note}"
                )
                return NormalizedSignalRecord(
                    source_record_id=article.source_record_id,
                    source_url=article.source_url,
                    title=article.title,
                    published_at=article.published_at,
                    category=article.category,
                    signal_type=signal_type,
                    matched_keywords=matched_keywords,
                    summary_text=article.summary_text,
                    geographic_context_raw=f"INVALID({article.explicit_lon}, {article.explicit_lat})",
                    location_status=LocationStatus.INVALID_COORDINATES_REJECTED,
                    location_resolution_note=note,
                    raw_payload_hash=payload_hash,
                )

            easting, northing, ewkt = self._to_epsg_25832(
                article.explicit_lon, article.explicit_lat
            )
            report.locations_resolved_25832 += 1
            return NormalizedSignalRecord(
                source_record_id=article.source_record_id,
                source_url=article.source_url,
                title=article.title,
                published_at=article.published_at,
                category=article.category,
                signal_type=signal_type,
                matched_keywords=matched_keywords,
                summary_text=article.summary_text,
                geographic_context_raw=f"Explicit WGS84 ({article.explicit_lon}, {article.explicit_lat})",
                location_status=LocationStatus.RESOLVED,
                location_resolution_note="Resolved from verified explicit coordinates to EPSG:25832.",
                wgs84_lon=article.explicit_lon,
                wgs84_lat=article.explicit_lat,
                utm32_easting=easting,
                utm32_northing=northing,
                ewkt_25832=ewkt,
                raw_payload_hash=payload_hash,
            )

        # 2. Match against Gazetteer entities/cities in title + summary
        combined_text = f"{article.title} {article.summary_text or ''}".lower()
        matched_entries: List[GazetteerEntry] = []
        for entry in GAZETTEER:
            if any(alias in combined_text for alias in entry.aliases):
                matched_entries.append(entry)

        if len(matched_entries) == 1:
            entry = matched_entries[0]
            easting, northing, ewkt = self._to_epsg_25832(
                entry.wgs84_lon, entry.wgs84_lat
            )
            report.locations_resolved_25832 += 1
            return NormalizedSignalRecord(
                source_record_id=article.source_record_id,
                source_url=article.source_url,
                title=article.title,
                published_at=article.published_at,
                category=article.category,
                signal_type=signal_type,
                matched_keywords=matched_keywords,
                summary_text=article.summary_text,
                geographic_context_raw=entry.canonical_name,
                location_status=LocationStatus.RESOLVED,
                location_resolution_note=f"Deterministic gazetteer match for '{entry.canonical_name}' transformed to EPSG:25832.",
                wgs84_lon=entry.wgs84_lon,
                wgs84_lat=entry.wgs84_lat,
                utm32_easting=easting,
                utm32_northing=northing,
                ewkt_25832=ewkt,
                raw_payload_hash=payload_hash,
            )

        if len(matched_entries) > 1:
            names = "; ".join(e.canonical_name for e in matched_entries)
            report.locations_ambiguous += 1
            return NormalizedSignalRecord(
                source_record_id=article.source_record_id,
                source_url=article.source_url,
                title=article.title,
                published_at=article.published_at,
                category=article.category,
                signal_type=signal_type,
                matched_keywords=matched_keywords,
                summary_text=article.summary_text,
                geographic_context_raw=names,
                location_status=LocationStatus.AMBIGUOUS_MULTI_REGION,
                location_resolution_note=f"Multiple distinct locations matched ({names}); geometry left NULL to prevent false point assignment.",
                raw_payload_hash=payload_hash,
            )

        # 3. Check for broad multi-region / supranational scope (e.g. USA & Europe, Global)
        multi_match = MULTI_REGION_PATTERNS.search(combined_text)
        if multi_match:
            report.locations_ambiguous += 1
            raw_scope = multi_match.group(0)
            return NormalizedSignalRecord(
                source_record_id=article.source_record_id,
                source_url=article.source_url,
                title=article.title,
                published_at=article.published_at,
                category=article.category,
                signal_type=signal_type,
                matched_keywords=matched_keywords,
                summary_text=article.summary_text,
                geographic_context_raw=raw_scope,
                location_status=LocationStatus.AMBIGUOUS_MULTI_REGION,
                location_resolution_note=f"Broad macro/multi-region context ('{raw_scope}') cannot be reduced to a single EPSG:25832 point.",
                raw_payload_hash=payload_hash,
            )

        # 4. Unresolved location
        report.locations_unresolved += 1
        return NormalizedSignalRecord(
            source_record_id=article.source_record_id,
            source_url=article.source_url,
            title=article.title,
            published_at=article.published_at,
            category=article.category,
            signal_type=signal_type,
            matched_keywords=matched_keywords,
            summary_text=article.summary_text,
            geographic_context_raw=None,
            location_status=LocationStatus.UNRESOLVED_NO_LOCATION,
            location_resolution_note="No municipality or headquarters location identifiable in source text.",
            raw_payload_hash=payload_hash,
        )

    def _is_valid_coordinate_pair(
        self, lon: Optional[float], lat: Optional[float]
    ) -> bool:
        if lon is None or lat is None:
            return False
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            return False
        if abs(lon) < 1e-6 and abs(lat) < 1e-6:
            return False
        if not (self.MIN_LON <= lon <= self.MAX_LON and self.MIN_LAT <= lat <= self.MAX_LAT):
            return False
        return True

    def _to_epsg_25832(self, lon: float, lat: float) -> Tuple[float, float, str]:
        easting, northing = self._transformer.transform(lon, lat)
        easting_r = round(float(easting), 2)
        northing_r = round(float(northing), 2)
        ewkt = f"SRID=25832;POINT({easting_r:.2f} {northing_r:.2f})"
        return easting_r, northing_r, ewkt
