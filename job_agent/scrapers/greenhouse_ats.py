"""Greenhouse ATS scraper — uses the public Greenhouse Job Board API for
discovery and application submission. No Selenium required."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from job_agent.config import AgentConfig
from job_agent.models import (
    JobBoard,
    JobListing,
    SearchPreferences,
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Greenhouse board slugs for target companies.
# Key = company name (as it appears in companies_target), value = Greenhouse board token.
GREENHOUSE_BOARDS: dict[str, str] = {
    "Stripe": "stripe",
    "Coinbase": "coinbase",
    "Airbnb": "airbnb",
    "Pinterest": "pinterestcareers",
    "HubSpot": "hubspot",
    "Cloudflare": "cloudflare",
    "Datadog": "datadog",
    "Figma": "figma",
    "Notion": "notion",
    "Airtable": "airtable",
    "Asana": "asana",
    "Brex": "brex",
    "Ramp": "ramp",
    "Plaid": "plaid",
    "MongoDB": "mongodb",
    "HashiCorp": "hashicorp",
    "Confluent": "confluent",
    "Intercom": "intercom",
    "Amplitude": "amplitude",
    "Pendo": "pendo",
    "Sentry": "sentry",
    "FullStory": "fullstory",
    "Webflow": "webflow",
    "Squarespace": "squarespace",
    "Loom": "loom",
    "Calendly": "calendly",
    "Gong": "gong",
    "Outreach": "outabordigital",
    "Braze": "braze",
    "Iterable": "iterable",
    "Algolia": "algolia",
    "Contentful": "contentful",
    "Vercel": "vercel",
    "Netlify": "netlify",
    "Supabase": "supabase",
    "Cockroach Labs": "cockroachlabs",
    "dbt Labs": "dbtlabsinc",
    "Fivetran": "fivetran",
    "Retool": "retool",
    "Databricks": "databricks",
    "Deel": "deel",
    "Rippling": "rippling",
    "Lattice": "lattice",
    "Greenhouse": "greenhouse",
    "Ashby": "ashbyhq",
    "CrowdStrike": "crowdstrike",
    "Wiz": "wizinc",
    "Snyk": "snyk",
    "Carta": "carta",
    "Instacart": "instacart",
    "DoorDash": "doordash",
    "Uber": "uber",
    "Lyft": "lyft",
    "Reddit": "reddit",
    "Sourcegraph": "sourcegraph",
    "LaunchDarkly": "launchdarkly",
    "Postman": "postman",
    "Grammarly": "grammarly",
    "Monday.com": "mondaycom",
    "Linear": "linear",
    "ClickUp": "clickup",
    "Robinhood": "robinhood",
    "Mercury": "mercury",
    "Chime": "chime",
    "SoFi": "solofi",
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Scale AI": "scaleai",
    "Weights & Biases": "wandb",
    "Perplexity": "perplexityai",
    "Runway": "runwayml",
    "ElevenLabs": "elevenlabs",
    "Descript": "descript",
    "Duolingo": "duolingo",
    "Noom": "noom",
    "Headspace": "headspace",
    "Flatiron Health": "flatironhealth",
    "Ro": "ro",
    "Hims & Hers": "himshers",
    "Oura": "ouraring",
    "WHOOP": "whoop",
    "Strava": "strava",
    "Opendoor": "opendoor",
    "Zillow": "zillowgroup",
    "Redfin": "redfin",
    "Hopper": "hopper",
    "Patreon": "patreon",
    "Spotify": "spotify",
    "PagerDuty": "pagerduty",
    "Fastly": "fastly",
    "Kong": "kong",
    "Weaviate": "weaviate",
    "Pinecone": "pinaborecone",
    "Together AI": "togetherai",
    "PostHog": "posthog",
    "Hex": "hex",
    "Mode Analytics": "mode",
    "Census": "census",
    "Hightouch": "hightouch",
    "Customer.io": "customerio",
    "Attentive": "attentive",
    "Klaviyo": "klaviyo",
    "BigCommerce": "bigcommerce",
    "Builder.io": "builder-io",
    "PlanetScale": "planetscale",
    "SingleStore": "singlestore",
    "ClickHouse": "clickhouse",
    "Bubble": "bubble",
    "Coda": "coda",
    "Phantom": "phantom",
    "Circle": "circle",
    "Alchemy": "alchemy",
    "Fireblocks": "fireblocks",
    "Chainalysis": "chainalysis",
    "Uniswap Labs": "uniswaplabs",
    "OpenSea": "opensea",
    "Optimism": "optimism",
    "dYdX": "dydx",
    "Anchorage Digital": "anchoragedigital",
    "BitGo": "bitgo",
    "MoonPay": "moonpay",
    "Safe": "safe",
    "Maven Clinic": "mavenclinic",
    "Calm": "calm",
    "Culture Amp": "cultureamp",
    "15Five": "15five",
    "Checkr": "checkr",
    "SmartRecruiters": "smartrecruiters",
    "Palo Alto Networks": "paloaltonetworks2",
    "Zscaler": "zscaler",
    "Bill.com": "billcom",
    "Expensify": "expensify",
    "Navan": "navan",
    "Productboard": "productboard",
    "Mural": "mural",
    "Semrush": "semrush",
    "Writer": "writer",
    "Jasper": "jasper",
}


class GreenhouseScraper(BaseScraper):
    """Scraper for companies using Greenhouse ATS — pure API, no browser."""

    board = JobBoard.GREENHOUSE
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def _is_executive_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(
            kw in title_lower
            for kw in [
                "vp", "vice president", "head of", "director", "coo", "cpo",
                "cmo", "cro", "chief", "general manager", "svp", "evp",
                "president", "senior director",
            ]
        )

    def _is_relevant(self, title: str, preferences: SearchPreferences) -> bool:
        if not self._is_executive_role(title):
            return False
        title_lower = title.lower()
        domain_kws = [
            "operations", "product", "growth", "strategy", "revenue",
            "go-to-market", "gtm", "business", "marketing", "platform",
            "monetization", "marketplace", "saas", "engineering",
        ]
        if any(kw in title_lower for kw in domain_kws):
            return True
        all_terms = preferences.keywords + preferences.titles
        return any(term.lower() in title_lower for term in all_terms)

    def _location_matches(self, location: str, preferences: SearchPreferences) -> bool:
        if not preferences.locations:
            return True
        loc_lower = location.lower()
        for pref in preferences.locations:
            pl = pref.lower()
            if pl == "remote" and ("remote" in loc_lower or not location):
                return True
            if any(part.strip() in loc_lower for part in pl.split(",")):
                return True
        return False

    def search_jobs(self, preferences: SearchPreferences) -> list[JobListing]:
        """Search all mapped Greenhouse boards for executive-level roles."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        # Daily rotation through boards
        boards = list(GREENHOUSE_BOARDS.items())
        per_run = preferences.companies_per_run or len(boards)
        if per_run < len(boards):
            total_batches = math.ceil(len(boards) / per_run)
            batch_idx = datetime.utcnow().timetuple().tm_yday % total_batches
            batch_start = batch_idx * per_run
            batch = boards[batch_start : batch_start + per_run]
            logger.info(
                f"Greenhouse: batch {batch_idx + 1}/{total_batches} "
                f"({len(batch)} boards)"
            )
        else:
            batch = boards

        for company_name, board_token in batch:
            try:
                board_jobs = self._fetch_board(
                    company_name, board_token, preferences
                )
                for j in board_jobs:
                    if j.external_id not in seen_ids:
                        seen_ids.add(j.external_id)
                        jobs.append(j)
            except Exception as e:
                logger.debug(f"Greenhouse {company_name}: {e}")

        logger.info(f"Greenhouse: {len(jobs)} matching roles from {len(batch)} boards")
        return jobs

    def _fetch_board(
        self, company: str, token: str, preferences: SearchPreferences
    ) -> list[JobListing]:
        """Fetch jobs from a single Greenhouse board."""
        url = f"{self.API_BASE}/{token}/jobs"
        data = self._get_json(url, params={"content": "true"})
        listings: list[JobListing] = []

        if not isinstance(data, dict) or "jobs" not in data:
            return listings

        for job in data["jobs"]:
            title = job.get("title", "")
            if not self._is_relevant(title, preferences):
                continue

            location_name = ""
            if job.get("location"):
                location_name = job["location"].get("name", "")

            if not self._location_matches(location_name, preferences):
                continue

            job_id = str(job.get("id", ""))
            abs_url = job.get("absolute_url", f"https://boards.greenhouse.io/{token}/jobs/{job_id}")

            # Extract description text
            desc = ""
            content = job.get("content", "")
            if content:
                from bs4 import BeautifulSoup
                desc = BeautifulSoup(content, "html.parser").get_text(
                    separator="\n", strip=True
                )[:5000]

            posted_date = None
            updated_at = job.get("updated_at", "")
            if updated_at:
                try:
                    posted_date = datetime.fromisoformat(
                        updated_at.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            listings.append(
                JobListing(
                    external_id=f"gh_{token}_{job_id}",
                    board=JobBoard.GREENHOUSE,
                    url=abs_url,
                    title=title,
                    company=company,
                    location=location_name,
                    description=desc,
                    posted_date=posted_date,
                    application_url=abs_url,
                )
            )

        if listings:
            logger.info(f"Greenhouse {company}: {len(listings)} executive roles")
        return listings

    def get_job_details(self, job: JobListing) -> JobListing:
        """Job details are already fetched with content=true in search."""
        return job

    def login(self, email: str, password: str) -> bool:
        return False
