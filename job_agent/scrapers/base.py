"""Base scraper class with shared browser automation and rate limiting."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from job_agent.config import AgentConfig
from job_agent.models import JobBoard, JobListing, SearchPreferences

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all job board scrapers."""

    board: JobBoard

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self._setup_session()
        self._last_request_time = 0.0

    def _setup_session(self) -> None:
        """Configure the HTTP session with headers and proxy."""
        try:
            ua = UserAgent()
            user_agent = self.config.browser.user_agent or ua.random
        except Exception:
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
        )

        if self.config.browser.proxy:
            self.session.proxies = {
                "http": self.config.browser.proxy,
                "https": self.config.browser.proxy,
            }

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        delay = self.config.rate_limit_delay + random.uniform(0.5, 2.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: Optional[dict] = None) -> BeautifulSoup:
        """Make a rate-limited GET request and return parsed HTML."""
        self._rate_limit()
        logger.debug(f"GET {url} params={params}")

        for attempt in range(self.config.max_retries):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.config.browser.timeout
                )
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except requests.RequestException as e:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                else:
                    raise

    def _get_json(self, url: str, params: Optional[dict] = None) -> dict:
        """Make a rate-limited GET request and return JSON."""
        self._rate_limit()
        logger.debug(f"GET JSON {url} params={params}")

        for attempt in range(self.config.max_retries):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.config.browser.timeout
                )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                else:
                    raise

    @abstractmethod
    def search_jobs(
        self, preferences: SearchPreferences
    ) -> list[JobListing]:
        """Search for jobs matching the given preferences."""
        ...

    @abstractmethod
    def get_job_details(self, job: JobListing) -> JobListing:
        """Fetch full job details for a listing."""
        ...

    @abstractmethod
    def login(self, email: str, password: str) -> bool:
        """Authenticate with the job board."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        self.session.close()
