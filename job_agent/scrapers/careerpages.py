"""Generic career page scraper for target company career URLs."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Optional

import yaml
from bs4 import BeautifulSoup, Tag

from job_agent.config import AgentConfig
from job_agent.models import (
    JobBoard,
    JobListing,
    SearchPreferences,
)
from job_agent.scrapers.base import BaseScraper
from datetime import datetime

logger = logging.getLogger(__name__)

# Title keywords that signal VP/Head/Director-level roles
EXECUTIVE_KEYWORDS = [
    "vp", "vice president", "head of", "director", "coo", "cpo", "cmo", "cro",
    "chief", "general manager", "svp", "senior vice president", "evp",
    "president", "partner",
]

# Keywords relevant to Derek's background
DOMAIN_KEYWORDS = [
    "operations", "product", "growth", "strategy", "revenue", "go-to-market",
    "gtm", "business development", "marketing", "platform", "monetization",
    "marketplace", "saas",
]


def _load_career_urls(path: str | Path) -> dict[str, str]:
    """Load company -> career URL mapping from YAML file."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("career_urls", {})


class CareerPageScraper(BaseScraper):
    """Scraper that checks company career pages directly for relevant openings."""

    board = JobBoard.CAREERPAGES

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        # Look for career_urls.yaml in several locations
        self.career_urls: dict[str, str] = {}
        for candidate in [
            Path("/opt/job-agent/data/career_urls.yaml"),
            Path(config.data_dir) / "career_urls.yaml",
            Path("data/career_urls.yaml"),
        ]:
            urls = _load_career_urls(candidate)
            if urls:
                self.career_urls = urls
                logger.info(f"Loaded {len(urls)} career URLs from {candidate}")
                break

    def _is_executive_role(self, title: str) -> bool:
        """Check if a job title is an executive/VP-level role."""
        title_lower = title.lower()
        return any(kw in title_lower for kw in EXECUTIVE_KEYWORDS)

    def _is_relevant_domain(self, title: str) -> bool:
        """Check if a job title is in a relevant domain."""
        title_lower = title.lower()
        return any(kw in title_lower for kw in DOMAIN_KEYWORDS)

    def _is_match(self, title: str, preferences: SearchPreferences) -> bool:
        """Check if a title matches: must be executive-level AND in relevant domain."""
        if not self._is_executive_role(title):
            return False
        # Also check domain relevance or user's specific keywords
        if self._is_relevant_domain(title):
            return True
        # Fall back to checking against user's search terms
        title_lower = title.lower()
        all_terms = preferences.keywords + preferences.titles
        return any(term.lower() in title_lower for term in all_terms)

    def search_jobs(self, preferences: SearchPreferences) -> list[JobListing]:
        """Search career pages for executive-level openings."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        if not self.career_urls:
            logger.warning("No career URLs loaded — skipping career page scraper")
            return jobs

        # Daily rotation through career URLs (same logic as LinkedIn company search)
        companies = list(self.career_urls.items())
        per_run = getattr(preferences, "companies_per_run", 50) or len(companies)
        if per_run < len(companies):
            total_batches = math.ceil(len(companies) / per_run)
            batch_idx = datetime.utcnow().timetuple().tm_yday % total_batches
            batch_start = batch_idx * per_run
            batch = companies[batch_start : batch_start + per_run]
            logger.info(
                f"Career pages: batch {batch_idx + 1}/{total_batches} "
                f"({len(batch)} companies)"
            )
        else:
            batch = companies

        for company_name, career_url in batch:
            try:
                page_jobs = self._scrape_career_page(
                    company_name, career_url, preferences
                )
                for listing in page_jobs:
                    if listing.external_id not in seen_ids:
                        seen_ids.add(listing.external_id)
                        jobs.append(listing)
            except Exception as e:
                logger.debug(f"Failed to scrape {company_name} career page: {e}")

        logger.info(f"Career pages: found {len(jobs)} matching roles from {len(batch)} companies")
        return jobs

    def _scrape_career_page(
        self, company: str, url: str, preferences: SearchPreferences
    ) -> list[JobListing]:
        """Scrape a single company's career page for relevant listings."""
        listings: list[JobListing] = []

        try:
            soup = self._get(url)
        except Exception as e:
            logger.debug(f"{company}: failed to fetch {url}: {e}")
            return listings

        # Strategy 1: Find job links (most career pages are link-heavy)
        links = soup.find_all("a", href=True)
        for link in links:
            text = link.get_text(strip=True)
            if not text or len(text) < 5 or len(text) > 200:
                continue

            if self._is_match(text, preferences):
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    # Resolve relative URL
                    from urllib.parse import urljoin
                    href = urljoin(url, href)

                ext_id = re.sub(r"\W+", "_", (href or text)[-80:])
                listings.append(
                    JobListing(
                        external_id=f"career_{re.sub(r'[^a-z0-9]', '_', company.lower())}_{ext_id}",
                        board=JobBoard.CAREERPAGES,
                        url=href or url,
                        title=text,
                        company=company,
                        location="",
                    )
                )

        # Strategy 2: Check headings and list items for job titles
        for tag in soup.find_all(["h2", "h3", "h4", "li"]):
            text = tag.get_text(strip=True)
            if not text or len(text) < 5 or len(text) > 200:
                continue

            if self._is_match(text, preferences):
                # Check if there's a link in or near this element
                link = tag.find("a", href=True) or (
                    tag.parent.find("a", href=True) if tag.parent else None
                )
                href = ""
                if link:
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)

                ext_id = re.sub(r"\W+", "_", (href or text)[-80:])
                full_id = f"career_{re.sub(r'[^a-z0-9]', '_', company.lower())}_{ext_id}"

                # Avoid duplicates within the same page
                if not any(j.external_id == full_id for j in listings):
                    listings.append(
                        JobListing(
                            external_id=full_id,
                            board=JobBoard.CAREERPAGES,
                            url=href or url,
                            title=text,
                            company=company,
                            location="",
                        )
                    )

        if listings:
            logger.info(f"{company}: found {len(listings)} executive-level roles")

        return listings

    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full details from the job listing page."""
        if not job.url:
            return job
        try:
            soup = self._get(job.url)
            # Try common job description containers
            desc_el = soup.select_one(
                ".job-description, .posting-description, .content, "
                "[class*='description'], [class*='details'], article, main"
            )
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)[:5000]
        except Exception as e:
            logger.debug(f"Failed to get career page details: {e}")
        return job

    def login(self, email: str, password: str) -> bool:
        return False
