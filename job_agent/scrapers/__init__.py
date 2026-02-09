"""Job board scrapers for LinkedIn, Indeed, Glassdoor, ZipRecruiter, executive recruiting firms, career pages, and ATS APIs."""

from job_agent.scrapers.base import BaseScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.indeed import IndeedScraper
from job_agent.scrapers.glassdoor import GlassdoorScraper
from job_agent.scrapers.ziprecruiter import ZipRecruiterScraper
from job_agent.scrapers.heidrick import HeidrickScraper
from job_agent.scrapers.kornferry import KornFerryScraper
from job_agent.scrapers.spencerstuart import SpencerStuartScraper
from job_agent.scrapers.russellreynolds import RussellReynoldsScraper
from job_agent.scrapers.careerpages import CareerPageScraper
from job_agent.scrapers.greenhouse_ats import GreenhouseScraper
from job_agent.scrapers.lever_ats import LeverScraper

SCRAPERS = {
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "glassdoor": GlassdoorScraper,
    "ziprecruiter": ZipRecruiterScraper,
    "heidrick": HeidrickScraper,
    "kornferry": KornFerryScraper,
    "spencerstuart": SpencerStuartScraper,
    "russellreynolds": RussellReynoldsScraper,
    "careerpages": CareerPageScraper,
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
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
    "CareerPageScraper",
    "GreenhouseScraper",
    "LeverScraper",
    "SCRAPERS",
]
