"""Job board scrapers for LinkedIn, Indeed, Glassdoor, ZipRecruiter, and executive recruiting firms."""

from job_agent.scrapers.base import BaseScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.indeed import IndeedScraper
from job_agent.scrapers.glassdoor import GlassdoorScraper
from job_agent.scrapers.ziprecruiter import ZipRecruiterScraper
from job_agent.scrapers.heidrick import HeidrickScraper
from job_agent.scrapers.kornferry import KornFerryScraper
from job_agent.scrapers.spencerstuart import SpencerStuartScraper
from job_agent.scrapers.russellreynolds import RussellReynoldsScraper

SCRAPERS = {
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "glassdoor": GlassdoorScraper,
    "ziprecruiter": ZipRecruiterScraper,
    "heidrick": HeidrickScraper,
    "kornferry": KornFerryScraper,
    "spencerstuart": SpencerStuartScraper,
    "russellreynolds": RussellReynoldsScraper,
}

__all__ = [
    "BaseScraper",
    "LinkedInScraper",
    "IndeedScraper",
    "GlassdoorScraper",
    "ZipRecruiterScraper",
    "HeidrickScraper",
    "KornFerryScraper",
    "SpencerStuartScraper",
    "RussellReynoldsScraper",
    "SCRAPERS",
]
