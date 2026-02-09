"""LinkedIn job scraper."""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
from datetime import datetime, timedelta
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

# LinkedIn uses numeric codes for filters
EXPERIENCE_MAP = {
    ExperienceLevel.INTERN: "1",
    ExperienceLevel.ENTRY: "2",
    ExperienceLevel.MID: "3",
    ExperienceLevel.SENIOR: "4",
    ExperienceLevel.DIRECTOR: "5",
    ExperienceLevel.EXECUTIVE: "6",
}

JOB_TYPE_MAP = {
    JobType.FULL_TIME: "F",
    JobType.PART_TIME: "P",
    JobType.CONTRACT: "C",
    JobType.INTERNSHIP: "I",
}

TIME_FILTER_MAP = {
    1: "r86400",
    7: "r604800",
    30: "r2592000",
}

WORK_MODE_MAP = {
    WorkMode.ONSITE: "1",
    WorkMode.REMOTE: "2",
    WorkMode.HYBRID: "3",
}


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn job listings using the public jobs API."""

    board = JobBoard.LINKEDIN
    BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def _build_search_params(
        self, preferences: SearchPreferences, start: int = 0, location: str = ""
    ) -> dict:
        """Build LinkedIn search query parameters."""
        params: dict = {
            "keywords": " ".join(preferences.keywords),
            "start": start,
            "sortBy": "DD",  # Sort by date
        }

        if location:
            params["location"] = location
        elif preferences.locations:
            params["location"] = preferences.locations[0]

        if preferences.experience_levels:
            levels = ",".join(
                EXPERIENCE_MAP[lvl]
                for lvl in preferences.experience_levels
                if lvl in EXPERIENCE_MAP
            )
            if levels:
                params["f_E"] = levels

        if preferences.job_types:
            types = ",".join(
                JOB_TYPE_MAP[jt]
                for jt in preferences.job_types
                if jt in JOB_TYPE_MAP
            )
            if types:
                params["f_JT"] = types

        if preferences.work_modes:
            modes = ",".join(
                WORK_MODE_MAP[wm]
                for wm in preferences.work_modes
                if wm in WORK_MODE_MAP
            )
            if modes:
                params["f_WT"] = modes
        elif preferences.remote_only:
            params["f_WT"] = "2"

        # Time posted filter
        days = preferences.posted_within_days
        for threshold, code in sorted(TIME_FILTER_MAP.items()):
            if days <= threshold:
                params["f_TPR"] = code
                break
        else:
            params["f_TPR"] = "r2592000"

        return params

    def _parse_listing(self, card: Tag) -> Optional[JobListing]:
        """Parse a single job card from LinkedIn search results."""
        try:
            title_el = card.select_one(".base-search-card__title")
            company_el = card.select_one(".base-search-card__subtitle a")
            location_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")
            date_el = card.select_one("time")

            if not title_el or not link_el:
                return None

            url = link_el.get("href", "").split("?")[0]
            external_id = ""
            # Always extract the numeric ID from the end of the URL
            numeric_match = re.search(r"-(\d+)$", url)
            if numeric_match:
                external_id = numeric_match.group(1)
            else:
                id_match = re.search(r"/view/([^/?]+)", url)
                if id_match:
                    external_id = id_match.group(1)

            if not external_id:
                return None

            posted_date = None
            if date_el and date_el.get("datetime"):
                try:
                    posted_date = datetime.fromisoformat(
                        date_el["datetime"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            easy_apply = bool(card.select_one(".job-search-card__easy-apply-label"))

            return JobListing(
                external_id=external_id,
                board=JobBoard.LINKEDIN,
                url=url,
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else "Unknown",
                location=location_el.get_text(strip=True) if location_el else "",
                posted_date=posted_date,
                easy_apply=easy_apply,
            )
        except Exception as e:
            logger.warning(f"Failed to parse LinkedIn card: {e}")
            return None

    def _search_pages(
        self,
        term: str,
        location: str,
        preferences: SearchPreferences,
        jobs: list[JobListing],
        seen_ids: set[str],
        max_pages: int = 2,
    ) -> None:
        """Search LinkedIn for a single term+location combo across pages."""
        for page in range(max_pages):
            start = page * 25
            params = self._build_search_params(preferences, start, location=location)
            params["keywords"] = term

            loc_label = location or "anywhere"
            logger.info(f"LinkedIn: '{term}' in '{loc_label}' page {page + 1}")

            try:
                soup = self._get(self.BASE_URL, params=params)
            except Exception as e:
                logger.error(f"LinkedIn search failed: '{term}' in '{loc_label}': {e}")
                break

            cards = soup.select("li")
            if not cards:
                break

            new_on_page = 0
            for card in cards:
                listing = self._parse_listing(card)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)
                    new_on_page += 1

            logger.info(
                f"Found {len(cards)} cards, {new_on_page} new, "
                f"{len(jobs)} total unique jobs"
            )

            if new_on_page == 0:
                break

    def search_jobs(
        self, preferences: SearchPreferences, max_pages: int = 2
    ) -> list[JobListing]:
        """Search LinkedIn across all locations and keywords, plus target companies."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        # Build unique search terms from keywords + titles
        search_terms = list(preferences.keywords)
        for title in preferences.titles:
            if title.lower() not in [k.lower() for k in search_terms]:
                search_terms.append(title)

        # Search each location separately
        locations = preferences.locations if preferences.locations else [""]

        for location in locations:
            for term in search_terms:
                self._search_pages(term, location, preferences, jobs, seen_ids, max_pages)

        # Company-targeted searches
        if hasattr(preferences, "companies_target") and preferences.companies_target:
            for company in preferences.companies_target:
                for location in locations:
                    self._search_pages(
                        company, location, preferences, jobs, seen_ids, max_pages=1
                    )

        logger.info(f"LinkedIn total: {len(jobs)} unique jobs across {len(locations)} locations")
        return jobs

    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full job description from LinkedIn."""
        try:
            # Try the detail API with numeric ID first, fall back to job URL
            try:
                url = self.DETAIL_URL.format(job_id=job.external_id)
                soup = self._get(url)
            except Exception:
                soup = self._get(job.url)

            desc_el = soup.select_one(".description__text")
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)

            criteria = soup.select(".description__job-criteria-item")
            for item in criteria:
                label = item.select_one(
                    ".description__job-criteria-subheader"
                )
                value = item.select_one(
                    ".description__job-criteria-text"
                )
                if label and value:
                    label_text = label.get_text(strip=True).lower()
                    value_text = value.get_text(strip=True)

                    if "seniority" in label_text:
                        job.experience_level = self._map_experience(value_text)
                    elif "employment type" in label_text:
                        job.job_type = self._map_job_type(value_text)

        except Exception as e:
            logger.warning(f"Failed to get LinkedIn job details: {e}")

        return job

    def login(self, email: str, password: str) -> bool:
        """LinkedIn login (requires Selenium for full authentication)."""
        logger.info(
            "LinkedIn login via requests is limited. "
            "For Easy Apply, use Selenium-based flow."
        )
        return False

    @staticmethod
    def _map_experience(text: str) -> Optional[ExperienceLevel]:
        text = text.lower()
        mapping = {
            "intern": ExperienceLevel.INTERN,
            "entry": ExperienceLevel.ENTRY,
            "associate": ExperienceLevel.ENTRY,
            "mid-senior": ExperienceLevel.SENIOR,
            "director": ExperienceLevel.DIRECTOR,
            "executive": ExperienceLevel.EXECUTIVE,
        }
        for key, level in mapping.items():
            if key in text:
                return level
        return None

    @staticmethod
    def _map_job_type(text: str) -> Optional[JobType]:
        text = text.lower()
        mapping = {
            "full-time": JobType.FULL_TIME,
            "part-time": JobType.PART_TIME,
            "contract": JobType.CONTRACT,
            "internship": JobType.INTERNSHIP,
        }
        for key, jt in mapping.items():
            if key in text:
                return jt
        return None
