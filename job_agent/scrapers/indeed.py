"""Indeed job scraper."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import Tag

from job_agent.config import AgentConfig
from job_agent.models import (
    ExperienceLevel,
    JobBoard,
    JobListing,
    JobType,
    SearchPreferences,
    WorkMode,
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

JOB_TYPE_MAP = {
    JobType.FULL_TIME: "fulltime",
    JobType.PART_TIME: "parttime",
    JobType.CONTRACT: "contract",
    JobType.INTERNSHIP: "internship",
}

EXPERIENCE_MAP = {
    ExperienceLevel.ENTRY: "entry_level",
    ExperienceLevel.MID: "mid_level",
    ExperienceLevel.SENIOR: "senior_level",
}


class IndeedScraper(BaseScraper):
    """Scraper for Indeed job listings."""

    board = JobBoard.INDEED
    BASE_URL = "https://www.indeed.com/jobs"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def _build_search_params(
        self, preferences: SearchPreferences, start: int = 0
    ) -> dict:
        """Build Indeed search query parameters."""
        params: dict = {
            "q": " ".join(preferences.keywords),
            "start": start,
            "sort": "date",
        }

        if preferences.locations:
            params["l"] = preferences.locations[0]

        if preferences.remote_only:
            params["remotejob"] = "032b3046-06a3-4876-8dfd-474eb5e7ed11"

        if preferences.job_types:
            jt = preferences.job_types[0]
            if jt in JOB_TYPE_MAP:
                params["jt"] = JOB_TYPE_MAP[jt]

        if preferences.experience_levels:
            lvl = preferences.experience_levels[0]
            if lvl in EXPERIENCE_MAP:
                params["explvl"] = EXPERIENCE_MAP[lvl]

        if preferences.salary_min:
            params["salary"] = str(preferences.salary_min)

        # Time posted filter
        days = preferences.posted_within_days
        if days <= 1:
            params["fromage"] = "1"
        elif days <= 3:
            params["fromage"] = "3"
        elif days <= 7:
            params["fromage"] = "7"
        elif days <= 14:
            params["fromage"] = "14"

        return params

    def _parse_listing(self, card: Tag) -> Optional[JobListing]:
        """Parse a single job card from Indeed search results."""
        try:
            title_el = card.select_one("h2.jobTitle a, h2.jobTitle span")
            company_el = card.select_one("[data-testid='company-name'], .companyName")
            location_el = card.select_one(
                "[data-testid='text-location'], .companyLocation"
            )

            link_el = card.select_one("h2.jobTitle a")
            if not link_el:
                link_el = card.select_one("a[data-jk]")

            if not title_el:
                return None

            # Extract job key for external ID
            external_id = ""
            if link_el:
                jk = link_el.get("data-jk", "")
                if jk:
                    external_id = jk
                else:
                    href = link_el.get("href", "")
                    jk_match = re.search(r"jk=([a-f0-9]+)", href)
                    if jk_match:
                        external_id = jk_match.group(1)

            if not external_id:
                # Try to get from parent card
                external_id = card.get("data-jk", "") or card.get("id", "")

            if not external_id:
                return None

            url = f"https://www.indeed.com/viewjob?jk={external_id}"

            # Salary info
            salary_el = card.select_one(
                ".salary-snippet-container, .estimated-salary, "
                "[data-testid='attribute_snippet_testid']"
            )
            salary_text = salary_el.get_text(strip=True) if salary_el else ""

            # Easy apply check
            easy_apply = bool(
                card.select_one(
                    ".iaLabel, .indeedApply, [data-testid='indeedApply']"
                )
            )

            return JobListing(
                external_id=external_id,
                board=JobBoard.INDEED,
                url=url,
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
            logger.warning(f"Failed to parse Indeed card: {e}")
            return None

    def search_jobs(
        self, preferences: SearchPreferences, max_pages: int = 5
    ) -> list[JobListing]:
        """Search Indeed for job listings."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for page in range(max_pages):
            start = page * 10
            params = self._build_search_params(preferences, start)

            logger.info(
                f"Indeed search page {page + 1}: keywords={preferences.keywords}"
            )

            try:
                soup = self._get(self.BASE_URL, params=params)
            except Exception as e:
                logger.error(f"Indeed search failed on page {page + 1}: {e}")
                break

            cards = soup.select(
                ".job_seen_beacon, .jobsearch-ResultsList > li, "
                "[data-testid='slider_item']"
            )
            if not cards:
                logger.info("No more Indeed results found.")
                break

            for card in cards:
                listing = self._parse_listing(card)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)

            logger.info(f"Found {len(cards)} cards, {len(jobs)} total unique jobs")

        return jobs

    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full job description from Indeed."""
        try:
            soup = self._get(job.url)

            desc_el = soup.select_one(
                "#jobDescriptionText, .jobsearch-jobDescriptionText"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)

            # Extract requirements from bullet points
            if desc_el:
                bullets = desc_el.select("li")
                job.requirements = [
                    b.get_text(strip=True) for b in bullets if b.get_text(strip=True)
                ]

        except Exception as e:
            logger.warning(f"Failed to get Indeed job details: {e}")

        return job

    def login(self, email: str, password: str) -> bool:
        """Indeed login (requires browser automation for full auth)."""
        logger.info(
            "Indeed login via requests is limited. "
            "For automated apply, use Selenium-based flow."
        )
        return False
