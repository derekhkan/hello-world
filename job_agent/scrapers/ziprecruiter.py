"""ZipRecruiter job scraper."""

from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import Tag

from job_agent.config import AgentConfig
from job_agent.models import (
    JobBoard,
    JobListing,
    SearchPreferences,
    WorkMode,
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DAYS_MAP = {
    1: "1",
    3: "3",
    5: "5",
    7: "7",
    10: "10",
    25: "25",
}


class ZipRecruiterScraper(BaseScraper):
    """Scraper for ZipRecruiter job listings."""

    board = JobBoard.ZIPRECRUITER
    BASE_URL = "https://www.ziprecruiter.com/jobs-search"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def _build_search_params(
        self, preferences: SearchPreferences, page: int = 1
    ) -> dict:
        """Build ZipRecruiter search query parameters."""
        params: dict = {
            "search": " ".join(preferences.keywords),
            "page": page,
        }

        if preferences.locations:
            params["location"] = preferences.locations[0]

        if preferences.remote_only:
            params["refine_by_location_type"] = "only_remote"

        # Radius/distance
        days = preferences.posted_within_days
        for threshold in sorted(DAYS_MAP.keys()):
            if days <= threshold:
                params["days"] = DAYS_MAP[threshold]
                break

        if preferences.salary_min:
            params["refine_by_salary"] = f"{preferences.salary_min}+"

        return params

    def _parse_listing(self, card: Tag) -> Optional[JobListing]:
        """Parse a single job card from ZipRecruiter search results."""
        try:
            title_el = card.select_one(
                ".job_link, [data-testid='job-title'], h2 a, .jobList-title a"
            )
            company_el = card.select_one(
                ".t_org_link, [data-testid='employer-name'], .jobList-introMeta a"
            )
            location_el = card.select_one(
                ".location, [data-testid='job-location'], .jobList-introMeta .normal"
            )
            salary_el = card.select_one(
                ".salary, [data-testid='salary']"
            )

            if not title_el:
                return None

            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.ziprecruiter.com{href}"

            # Extract external ID
            external_id = card.get("data-job-id", "")
            if not external_id:
                id_match = re.search(r"/([a-f0-9]{32}|[a-z0-9-]{20,})", href)
                if id_match:
                    external_id = id_match.group(1)

            if not external_id:
                external_id = re.sub(r"\W+", "_", href[-40:])

            salary_text = salary_el.get_text(strip=True) if salary_el else ""

            # Check for one-click apply
            easy_apply = bool(
                card.select_one(
                    ".one_click_apply, .quick-apply, "
                    "[data-testid='one-click-apply']"
                )
            )

            return JobListing(
                external_id=external_id,
                board=JobBoard.ZIPRECRUITER,
                url=href,
                title=title_el.get_text(strip=True),
                company=(
                    company_el.get_text(strip=True) if company_el else "Unknown"
                ),
                location=(
                    location_el.get_text(strip=True) if location_el else ""
                ),
                salary_text=salary_text,
                easy_apply=easy_apply,
            )
        except Exception as e:
            logger.warning(f"Failed to parse ZipRecruiter card: {e}")
            return None

    def search_jobs(
        self, preferences: SearchPreferences, max_pages: int = 5
    ) -> list[JobListing]:
        """Search ZipRecruiter for job listings."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            params = self._build_search_params(preferences, page)

            logger.info(
                f"ZipRecruiter search page {page}: keywords={preferences.keywords}"
            )

            try:
                soup = self._get(self.BASE_URL, params=params)
            except Exception as e:
                logger.error(f"ZipRecruiter search failed on page {page}: {e}")
                break

            cards = soup.select(
                ".job_result, article.job-listing, "
                "[data-testid='job-result-item']"
            )
            if not cards:
                logger.info("No more ZipRecruiter results found.")
                break

            for card in cards:
                listing = self._parse_listing(card)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)

            logger.info(f"Found {len(cards)} cards, {len(jobs)} total unique jobs")

        return jobs

    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full job description from ZipRecruiter."""
        try:
            soup = self._get(job.url)

            desc_el = soup.select_one(
                ".jobDescriptionSection, .job-description, "
                "[data-testid='job-description']"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)

                bullets = desc_el.select("li")
                job.requirements = [
                    b.get_text(strip=True) for b in bullets if b.get_text(strip=True)
                ]

        except Exception as e:
            logger.warning(f"Failed to get ZipRecruiter job details: {e}")

        return job

    def login(self, email: str, password: str) -> bool:
        """ZipRecruiter login (requires browser automation)."""
        logger.info(
            "ZipRecruiter login via requests is limited. "
            "Use Selenium-based flow for one-click apply."
        )
        return False
