"""Glassdoor job scraper."""

from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import Tag

from job_agent.config import AgentConfig
from job_agent.models import (
    JobBoard,
    JobListing,
    JobType,
    SearchPreferences,
    WorkMode,
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class GlassdoorScraper(BaseScraper):
    """Scraper for Glassdoor job listings."""

    board = JobBoard.GLASSDOOR
    BASE_URL = "https://www.glassdoor.com/Job/jobs.htm"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        self.session.headers.update(
            {
                "Referer": "https://www.glassdoor.com/",
            }
        )

    def _build_search_params(
        self, preferences: SearchPreferences, page: int = 1
    ) -> dict:
        """Build Glassdoor search query parameters."""
        params: dict = {
            "sc.keyword": " ".join(preferences.keywords),
            "p": page,
        }

        if preferences.locations:
            params["locT"] = "C"  # City
            params["locKeyword"] = preferences.locations[0]

        if preferences.remote_only:
            params["remoteWorkType"] = "1"

        # Date posted filter
        days = preferences.posted_within_days
        if days <= 1:
            params["fromAge"] = "1"
        elif days <= 3:
            params["fromAge"] = "3"
        elif days <= 7:
            params["fromAge"] = "7"
        elif days <= 14:
            params["fromAge"] = "14"
        elif days <= 30:
            params["fromAge"] = "30"

        if preferences.salary_min:
            params["minSalary"] = str(preferences.salary_min)

        return params

    def _parse_listing(self, card: Tag) -> Optional[JobListing]:
        """Parse a single job card from Glassdoor search results."""
        try:
            title_el = card.select_one(
                "a.jobLink, [data-test='job-title'], .job-title"
            )
            company_el = card.select_one(
                ".employerName, [data-test='emp-name'], .job-employer"
            )
            location_el = card.select_one(
                ".loc, [data-test='emp-location'], .job-location"
            )
            salary_el = card.select_one(
                ".salary-estimate, [data-test='detailSalary']"
            )

            if not title_el:
                return None

            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.glassdoor.com{href}"

            # Extract external ID from URL
            external_id = ""
            id_match = re.search(r"jobListingId=(\d+)", href)
            if id_match:
                external_id = id_match.group(1)
            else:
                id_match = re.search(r"JV_\w+_(\d+)", href)
                if id_match:
                    external_id = id_match.group(1)

            if not external_id:
                data_id = card.get("data-id", "") or card.get("data-job-id", "")
                external_id = str(data_id) if data_id else ""

            if not external_id:
                return None

            salary_text = salary_el.get_text(strip=True) if salary_el else ""

            easy_apply = bool(
                card.select_one(".easyApply, [data-test='easyApply']")
            )

            return JobListing(
                external_id=external_id,
                board=JobBoard.GLASSDOOR,
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
            logger.warning(f"Failed to parse Glassdoor card: {e}")
            return None

    def search_jobs(
        self, preferences: SearchPreferences, max_pages: int = 5
    ) -> list[JobListing]:
        """Search Glassdoor for job listings."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            params = self._build_search_params(preferences, page)

            logger.info(
                f"Glassdoor search page {page}: keywords={preferences.keywords}"
            )

            try:
                soup = self._get(self.BASE_URL, params=params)
            except Exception as e:
                logger.error(f"Glassdoor search failed on page {page}: {e}")
                break

            cards = soup.select(
                "li.jl, [data-test='jobListing'], .react-job-listing"
            )
            if not cards:
                logger.info("No more Glassdoor results found.")
                break

            for card in cards:
                listing = self._parse_listing(card)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)

            logger.info(f"Found {len(cards)} cards, {len(jobs)} total unique jobs")

        return jobs

    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full job description from Glassdoor."""
        try:
            soup = self._get(job.url)

            desc_el = soup.select_one(
                "#JobDescriptionContainer, .desc, "
                "[data-test='jobDescriptionContent']"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)

            # Extract company rating
            rating_el = soup.select_one(
                ".ratingNum, [data-test='rating']"
            )
            if rating_el:
                job.notes = f"Company rating: {rating_el.get_text(strip=True)}"

        except Exception as e:
            logger.warning(f"Failed to get Glassdoor job details: {e}")

        return job

    def login(self, email: str, password: str) -> bool:
        """Glassdoor login (requires browser automation)."""
        logger.info(
            "Glassdoor login via requests is limited. "
            "Use Selenium-based flow for Easy Apply."
        )
        return False
