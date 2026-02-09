"""Russell Reynolds executive search scraper."""

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
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RussellReynoldsScraper(BaseScraper):
    """Scraper for Russell Reynolds Associates opportunities."""

    board = JobBoard.RUSSELLREYNOLDS
    BASE_URL = "https://www.russellreynolds.com/en/opportunities"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def _matches_preferences(self, title: str, preferences: SearchPreferences) -> bool:
        title_lower = title.lower()
        all_terms = preferences.keywords + preferences.titles
        return any(term.lower() in title_lower for term in all_terms) or any(
            word in title_lower
            for word in ["vp", "vice president", "head of", "director", "coo",
                         "chief", "general manager", "operations", "product", "growth"]
        )

    def _matches_location(self, location: str, preferences: SearchPreferences) -> bool:
        if not preferences.locations:
            return True
        loc_lower = location.lower()
        for pref_loc in preferences.locations:
            pref_lower = pref_loc.lower()
            if pref_lower == "remote" and "remote" in loc_lower:
                return True
            if any(part.strip() in loc_lower for part in pref_lower.split(",")):
                return True
        return False

    def search_jobs(self, preferences: SearchPreferences) -> list[JobListing]:
        """Search Russell Reynolds for executive opportunities."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        try:
            soup = self._get(self.BASE_URL)

            cards = soup.select(
                ".opportunity, .job-listing, article, .search-result, "
                "[class*='opportunity'], [class*='role'], [class*='position'], "
                ".card, li.result"
            )

            for card in cards:
                listing = self._parse_card(card, preferences)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)

            logger.info(f"Russell Reynolds: found {len(jobs)} matching roles")

        except Exception as e:
            logger.error(f"Russell Reynolds search failed: {e}")

        return jobs

    def _parse_card(
        self, card: Tag, preferences: SearchPreferences
    ) -> Optional[JobListing]:
        try:
            title_el = card.select_one(
                "h2, h3, h4, .title, [class*='title'], [class*='name']"
            )
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            if not self._matches_preferences(title, preferences):
                return None

            location_el = card.select_one(
                ".location, [class*='location'], [class*='city']"
            )
            location = location_el.get_text(strip=True) if location_el else ""
            if location and not self._matches_location(location, preferences):
                return None

            link_el = card.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = f"https://www.russellreynolds.com{href}"

            external_id = re.sub(r"\W+", "_", href[-60:] if href else title)

            company_el = card.select_one(
                ".company, [class*='company'], [class*='client'], [class*='org']"
            )
            company = company_el.get_text(strip=True) if company_el else "Confidential"

            desc_el = card.select_one("p, .description, [class*='desc']")
            description = desc_el.get_text(strip=True) if desc_el else ""

            return JobListing(
                external_id=f"russellreynolds_{external_id}",
                board=JobBoard.RUSSELLREYNOLDS,
                url=href or self.BASE_URL,
                title=title,
                company=company,
                location=location,
                description=description,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Russell Reynolds card: {e}")
            return None

    def get_job_details(self, job: JobListing) -> JobListing:
        if not job.url or job.url == self.BASE_URL:
            return job
        try:
            soup = self._get(job.url)
            desc_el = soup.select_one(
                ".opportunity-detail, .job-description, article, main, "
                "[class*='content']"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)
        except Exception as e:
            logger.warning(f"Failed to get Russell Reynolds details: {e}")
        return job

    def login(self, email: str, password: str) -> bool:
        return False
