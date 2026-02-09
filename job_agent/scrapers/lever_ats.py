"""Lever ATS scraper — uses the public Lever Postings API for
discovery and application submission. No Selenium required."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from typing import Optional

from job_agent.config import AgentConfig
from job_agent.models import (
    JobBoard,
    JobListing,
    SearchPreferences,
)
from job_agent.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Lever board slugs for target companies.
LEVER_BOARDS: dict[str, str] = {
    "Shopify": "shopify",
    "Twilio": "twilio",
    "Okta": "okta",
    "Elastic": "elastic",
    "Miro": "miro",
    "Mixpanel": "mixpanel",
    "Canva": "canva",
    "Salesloft": "salesloft",
    "Clearbit": "clearbit",
    "Recharge": "rechargecommerce",
    "Airbyte": "airbyte",
    "n8n": "n8n",
    "Gusto": "gusto",
    "1Password": "1password",
    "Coursera": "coursera",
    "Peloton": "onepeloton",
    "Drift": "drift",
    "Qualified": "qualified",
    "6sense": "6sense",
    "Demandbase": "demandbase",
    "Apollo.io": "apolloio",
    "ZoomInfo": "zoominfo",
    "Gorgias": "gorgias",
    "Sanity": "sanity",
    "Strapi": "strapi",
    "Prismic": "prismic",
    "Fly.io": "fly-io",
    "Railway": "railway",
    "Redis": "redis",
    "DataStax": "datastax",
    "Neo4j": "neo4j",
    "Matillion": "matillion",
    "Talend": "talend",
    "Appsmith": "appsmith",
    "Glide": "glide",
    "Softr": "softr",
    "Make": "make",
    "Workato": "workato",
    "Celonis": "celonis",
    "Dremio": "dremio",
    "Starburst": "starburst",
    "Dialpad": "dialpad",
    "8x8": "8x8",
    "Trulioo": "trulioo",
    "Onfido": "onfido",
    "Persona": "persona",
    "Alloy": "alloy",
    "Sift": "sift",
    "Sardine": "sardine",
    "TRM Labs": "trmlabs",
    "ConsenSys": "consensys",
    "QuickNode": "quicknode",
    "Moralis": "moralis",
    "Polygon Labs": "polygon-labs",
    "StarkWare": "starkware",
    "Matter Labs": "matterlabs",
    "Rarible": "rarible",
    "WalletConnect": "walletconnect",
    "Ramp Network": "rampnetwork",
    "Transak": "transak",
    "Cohere": "cohere",
    "Mistral AI": "mistral",
    "Hugging Face": "huggingface",
    "LangChain": "langchain",
    "LlamaIndex": "llamaindex",
    "Replicate": "replicate",
    "Modal": "modal",
    "AssemblyAI": "assemblyai",
    "Deepgram": "deepgram",
    "Kapwing": "kapwing",
    "VEED": "veed",
    "Stability AI": "stability",
    "Komodo Health": "komodohealth",
    "Notable Health": "notable",
    "Teladoc": "teladochealth",
    "Amwell": "amwell",
    "Khan Academy": "khanacademy",
    "MasterClass": "masterclass",
    "Quizlet": "quizlet",
    "Pluralsight": "pluralsight",
    "DataCamp": "datacamp",
    "Codecademy": "codecademy",
    "Oyster": "oyster",
    "Justworks": "justworks",
    "Lever": "lever",
    "Workable": "workable",
    "iCIMS": "icims",
    "Bitwarden": "bitwarden",
    "SentinelOne": "sentinelone",
    "Lacework": "lacework",
    "Fortinet": "fortinet",
    "Tailscale": "tailscale",
    "Proofpoint": "proofpoint",
    "KnowBe4": "knowbe4",
    "FreshBooks": "freshbooks",
    "Xero": "xero",
    "Crunchbase": "crunchbase",
    "Ahrefs": "ahrefs",
    "Cloudinary": "cloudinary",
    "Lucidchart": "lucid",
    "Whimsical": "whimsical",
    "Expedia": "expedia",
    "Booking.com": "booking",
    "Harness": "harness",
    "Pulumi": "pulumi",
    "Smartling": "smartling",
    "Lokalise": "lokalise",
    "Crowdin": "crowdin",
    "Deputy": "deputy",
    "Navan": "navan",
    "Similarweb": "similarweb",
    "Remote.com": "remote",
    "Rebuy": "rebuy",
    "Postscript": "postscript",
    "commercetools": "commercetools",
    "Render": "render",
}


class LeverScraper(BaseScraper):
    """Scraper for companies using Lever ATS — pure API, no browser."""

    board = JobBoard.LEVER
    API_BASE = "https://api.lever.co/v0/postings"

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
        """Search all mapped Lever boards for executive-level roles."""
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        # Daily rotation
        boards = list(LEVER_BOARDS.items())
        per_run = preferences.companies_per_run or len(boards)
        if per_run < len(boards):
            # Offset by half to avoid overlapping with Greenhouse batch
            total_batches = math.ceil(len(boards) / per_run)
            batch_idx = (datetime.utcnow().timetuple().tm_yday + 3) % total_batches
            batch_start = batch_idx * per_run
            batch = boards[batch_start : batch_start + per_run]
            logger.info(
                f"Lever: batch {batch_idx + 1}/{total_batches} "
                f"({len(batch)} boards)"
            )
        else:
            batch = boards

        for company_name, board_slug in batch:
            try:
                board_jobs = self._fetch_board(
                    company_name, board_slug, preferences
                )
                for j in board_jobs:
                    if j.external_id not in seen_ids:
                        seen_ids.add(j.external_id)
                        jobs.append(j)
            except Exception as e:
                logger.debug(f"Lever {company_name}: {e}")

        logger.info(f"Lever: {len(jobs)} matching roles from {len(batch)} boards")
        return jobs

    def _fetch_board(
        self, company: str, slug: str, preferences: SearchPreferences
    ) -> list[JobListing]:
        """Fetch jobs from a single Lever board."""
        url = f"{self.API_BASE}/{slug}"
        data = self._get_json(url)
        listings: list[JobListing] = []

        if not isinstance(data, list):
            return listings

        for posting in data:
            title = posting.get("text", "")
            if not self._is_relevant(title, preferences):
                continue

            # Lever puts location in categories
            categories = posting.get("categories", {})
            location = categories.get("location", "")
            if not self._location_matches(location, preferences):
                continue

            posting_id = posting.get("id", "")
            hosted_url = posting.get("hostedUrl", "")
            apply_url = posting.get("applyUrl", "")

            # Description from descriptionPlain or description (HTML)
            desc = posting.get("descriptionPlain", "")
            if not desc:
                desc_html = posting.get("description", "")
                if desc_html:
                    from bs4 import BeautifulSoup
                    desc = BeautifulSoup(desc_html, "html.parser").get_text(
                        separator="\n", strip=True
                    )[:5000]

            # Additional lists
            for section in posting.get("lists", []):
                section_text = section.get("text", "")
                section_content = section.get("content", "")
                if section_content:
                    from bs4 import BeautifulSoup
                    section_plain = BeautifulSoup(
                        section_content, "html.parser"
                    ).get_text(separator="\n", strip=True)
                    desc += f"\n\n{section_text}\n{section_plain}"

            posted_date = None
            created_at = posting.get("createdAt")
            if created_at:
                try:
                    posted_date = datetime.fromtimestamp(created_at / 1000)
                except (ValueError, TypeError, OSError):
                    pass

            listings.append(
                JobListing(
                    external_id=f"lever_{slug}_{posting_id}",
                    board=JobBoard.LEVER,
                    url=hosted_url or f"https://jobs.lever.co/{slug}/{posting_id}",
                    title=title,
                    company=company,
                    location=location,
                    description=desc[:5000],
                    posted_date=posted_date,
                    application_url=apply_url or hosted_url,
                )
            )

        if listings:
            logger.info(f"Lever {company}: {len(listings)} executive roles")
        return listings

    def get_job_details(self, job: JobListing) -> JobListing:
        """Details already fetched in search."""
        return job

    def login(self, email: str, password: str) -> bool:
        return False
