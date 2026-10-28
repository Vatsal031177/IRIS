import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.common.config import Settings
from services.common.models import PipelineQualityReport, RawNewsArticle

logger = logging.getLogger("scraper-service")

ARTICLE_URL_PATTERN = re.compile(
    r"/news/(?P<category>[a-z0-9\-]+)/headline/(?P<slug>[a-z0-9\-]+)-(?P<article_id>\d+)/?$",
    re.IGNORECASE,
)
GERMAN_DATE_PATTERN = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


class InstitutionalMoneyHarvester:
    """
    Pattern B (HTML) Harvester for https://www.institutional-money.com/news/
    Extracts newsroom items, parses German publication dates (DD.MM.YYYY),
    preserves numeric article IDs, and handles pagination and network faults.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = self._build_resilient_session()

    def _build_resilient_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.settings.http_max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        return session

    def fetch_html(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=self.settings.http_timeout_seconds)
            if response.status_code != 200:
                logger.warning("Non-200 HTTP status %s for URL: %s", response.status_code, url)
                return None
            if not response.text or not response.text.strip():
                logger.warning("Empty HTML response body for URL: %s", url)
                return None
            return response.text
        except requests.RequestException as exc:
            logger.error("Network failure fetching %s: %s", url, exc)
            return None

    def parse_listing_html(
        self,
        html_content: str,
        seen_ids: Set[str],
        report: PipelineQualityReport,
        article_details_lookup: Optional[Dict[str, dict]] = None,
    ) -> List[RawNewsArticle]:
        if not html_content or not html_content.strip():
            report.errors.append("Empty listing HTML encountered; yielded 0 items.")
            return []

        soup = BeautifulSoup(html_content, "lxml")
        candidate_nodes = soup.select("article.news-item, div.news-list-item, li.news-entry")
        if not candidate_nodes:
            # Fallback selector for generic anchor links matching Institutional Money headline pattern
            candidate_nodes = [
                a.parent for a in soup.find_all("a", href=ARTICLE_URL_PATTERN) if a.parent
            ]

        extracted: List[RawNewsArticle] = []

        for node in candidate_nodes:
            report.raw_articles_discovered += 1
            link_tag = (
                node if node.name == "a" else node.find("a", href=ARTICLE_URL_PATTERN)
            )
            if not link_tag or not link_tag.get("href"):
                report.malformed_records_rejected += 1
                report.errors.append("Malformed HTML card: missing headline anchor href.")
                continue

            raw_href = link_tag["href"].strip()
            match = ARTICLE_URL_PATTERN.search(raw_href)
            if not match:
                report.malformed_records_rejected += 1
                report.errors.append(f"Malformed article URL pattern: {raw_href}")
                continue

            article_id = match.group("article_id")
            category = match.group("category").lower()
            full_url = urljoin(self.settings.source_base_url, raw_href).rstrip("/")

            if article_id in seen_ids:
                report.in_batch_duplicates_skipped += 1
                continue

            title_el = node.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|headline", re.I))
            title_text = (
                title_el.get_text(" ", strip=True)
                if title_el
                else link_tag.get_text(" ", strip=True)
            )
            if not title_text or len(title_text) < 5:
                report.malformed_records_rejected += 1
                report.errors.append(
                    f"Record {article_id} rejected: missing or truncated title."
                )
                continue

            # Extract date from card text or fallback detail metadata
            node_text = node.get_text(" ", strip=True)
            pub_date = self._extract_date(node_text)

            summary_text = None
            explicit_lon = None
            explicit_lat = None

            if article_details_lookup and article_id in article_details_lookup:
                detail = article_details_lookup[article_id]
                summary_text = detail.get("summary_text")
                if not pub_date and detail.get("published_at"):
                    pub_date = self._extract_date(detail["published_at"])
                explicit_lon = detail.get("explicit_lon")
                explicit_lat = detail.get("explicit_lat")
            else:
                summary_el = node.find(["p", "div"], class_=re.compile(r"teaser|summary|eckpunkte", re.I))
                if summary_el:
                    summary_text = summary_el.get_text(" ", strip=True)

            if not pub_date:
                report.malformed_records_rejected += 1
                report.errors.append(
                    f"Record {article_id} ('{title_text[:40]}...') rejected: unverified/missing publication date."
                )
                continue

            seen_ids.add(article_id)
            extracted.append(
                RawNewsArticle(
                    source_record_id=article_id,
                    source_url=full_url,
                    title=title_text,
                    published_at=pub_date,
                    category=category,
                    summary_text=summary_text,
                    explicit_lon=explicit_lon,
                    explicit_lat=explicit_lat,
                )
            )

        return extracted

    @staticmethod
    def _extract_date(text: str) -> Optional[date]:
        if not text:
            return None
        # Check ISO YYYY-MM-DD first
        iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                return None

        # Check German DD.MM.YYYY format used by institutional-money.com
        de_match = GERMAN_DATE_PATTERN.search(text)
        if de_match:
            day, month, year = (
                int(de_match.group(1)),
                int(de_match.group(2)),
                int(de_match.group(3)),
            )
            try:
                return date(year, month, day)
            except ValueError:
                return None
        return None

    def harvest_from_fixtures(
        self, fixture_dir: Path, report: PipelineQualityReport
    ) -> List[RawNewsArticle]:
        seen_ids: Set[str] = set()
        all_articles: List[RawNewsArticle] = []

        details_path = fixture_dir / "article_details.json"
        details_lookup = {}
        if details_path.exists():
            details_lookup = json.loads(details_path.read_text(encoding="utf-8"))

        for page_file in sorted(fixture_dir.glob("listing_page_*.html")):
            report.pages_fetched += 1
            html_text = page_file.read_text(encoding="utf-8")
            page_articles = self.parse_listing_html(
                html_text, seen_ids, report, details_lookup
            )
            all_articles.extend(page_articles)

        return all_articles

    def harvest_live(self, report: PipelineQualityReport) -> List[RawNewsArticle]:
        seen_ids: Set[str] = set()
        all_articles: List[RawNewsArticle] = []

        for page_num in range(1, self.settings.max_pages + 1):
            page_url = (
                self.settings.source_base_url
                if page_num == 1
                else f"{self.settings.source_base_url}?page={page_num}"
            )
            html_text = self.fetch_html(page_url)
            if not html_text:
                report.errors.append(f"Failed or empty response on live page {page_url}")
                break
            report.pages_fetched += 1
            page_articles = self.parse_listing_html(html_text, seen_ids, report)
            if not page_articles:
                break
            all_articles.extend(page_articles)

        return all_articles
