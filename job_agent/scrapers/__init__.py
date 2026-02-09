"""Job board scrapers for LinkedIn, Indeed, Glassdoor, and ZipRecruiter."""

from job_agent.scrapers.base import BaseScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.indeed import IndeedScraper
from job_agent.scrapers.glassdoor import GlassdoorScraper
from job_agent.scrapers.ziprecruiter import ZipRecruiterScraper

SCRAPERS = {
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "glassdoor": GlassdoorScraper,
    "ziprecruiter": ZipRecruiterScraper,
}

__all__ = [
    "BaseScraper",
    "LinkedInScraper",
    "IndeedScraper",
    "GlassdoorScraper",
    "ZipRecruiterScraper",
    "SCRAPERS",
]
