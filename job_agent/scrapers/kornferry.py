"""Korn Ferry executive search scraper."""

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


class KornFerryScraper(BaseScraper):
    """Scraper for Korn Ferry executive opportunities."""

    board = JobBoard.KORNFERRY
    BASE_URL = "https://www.kornferry.com/opportunities"
    SEARCH_URL = "https://www.kornferry.com/api/opportunities"

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
        """Search Korn Ferry for executive opportunities."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        # Try API endpoint first
        try:
            data = self._get_json(self.SEARCH_URL)
            items = data if isinstance(data, list) else data.get("results", data.get("opportunities", []))
            for item in items:
                listing = self._parse_api_item(item, preferences)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)
            logger.info(f"Korn Ferry API: found {len(jobs)} matching roles")
            return jobs
        except Exception:
            logger.debug("Korn Ferry API not available, falling back to HTML")

        # Fallback to HTML
        try:
            soup = self._get(self.BASE_URL)
            cards = soup.select(
                ".opportunity, .job-card, article, .listing, "
                "[class*='opportunity'], [class*='role'], .card"
            )

            for card in cards:
                listing = self._parse_html_card(card, preferences)
                if listing and listing.external_id not in seen_ids:
                    seen_ids.add(listing.external_id)
                    jobs.append(listing)

            logger.info(f"Korn Ferry HTML: found {len(jobs)} matching roles")
        except Exception as e:
            logger.error(f"Korn Ferry search failed: {e}")

        return jobs

    def _parse_api_item(
        self, item: dict, preferences: SearchPreferences
    ) -> Optional[JobListing]:
        try:
            title = item.get("title", item.get("name", ""))
            if not title or not self._matches_preferences(title, preferences):
                return None

            location = item.get("location", "")
            if location and not self._matches_location(location, preferences):
                return None

            external_id = str(item.get("id", item.get("slug", "")))
            if not external_id:
                external_id = re.sub(r"\W+", "_", title)[:50]

            url = item.get("url", "")
            if not url:
                url = f"https://www.kornferry.com/opportunities/{external_id}"

            return JobListing(
                external_id=f"kornferry_{external_id}",
                board=JobBoard.KORNFERRY,
                url=url,
                title=title,
                company=item.get("company", item.get("client", "Confidential")),
                location=location,
                description=item.get("description", ""),
            )
        except Exception as e:
            logger.warning(f"Failed to parse Korn Ferry API item: {e}")
            return None

    def _parse_html_card(
        self, card: Tag, preferences: SearchPreferences
    ) -> Optional[JobListing]:
        try:
            title_el = card.select_one("h2, h3, .title, [class*='title']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not self._matches_preferences(title, preferences):
                return None

            location_el = card.select_one(".location, [class*='location']")
            location = location_el.get_text(strip=True) if location_el else ""
            if location and not self._matches_location(location, preferences):
                return None

            link_el = card.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                href = f"https://www.kornferry.com{href}"

            external_id = re.sub(r"\W+", "_", href[-60:] if href else title)

            return JobListing(
                external_id=f"kornferry_{external_id}",
                board=JobBoard.KORNFERRY,
                url=href or self.BASE_URL,
                title=title,
                company="Confidential",
                location=location,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Korn Ferry card: {e}")
            return None

    def get_job_details(self, job: JobListing) -> JobListing:
        if not job.url or job.url == self.BASE_URL:
            return job
        try:
            soup = self._get(job.url)
            desc_el = soup.select_one(
                ".opportunity-detail, .job-description, article, main"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)
        except Exception as e:
            logger.warning(f"Failed to get Korn Ferry details: {e}")
        return job

    def login(self, email: str, password: str) -> bool:
        return False
