"""Scan crypto news sites for trending articles and key takeaways."""

import logging
import json
import os
from datetime import datetime, timedelta

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class NewsScanner:
    """Scans crypto news sources and extracts trending articles."""

    def __init__(self, config: dict, llm_client=None):
        self.sources = config.get("news_sources", [])
        self.data_dir = config.get("data_dir", "data")
        self.llm_client = llm_client
        self.llm_config = config.get("llm", {})
        self._cache_path = os.path.join(self.data_dir, "news_cache.json")

    def scan_all(self, max_articles_per_source: int = 10) -> list[dict]:
        """Scan all configured news sources and return articles."""
        all_articles = []
        for source in self.sources:
            try:
                articles = self._scan_source(source, max_articles_per_source)
                all_articles.extend(articles)
                logger.info(f"Fetched {len(articles)} articles from {source['name']}")
            except Exception as e:
                logger.error(f"Failed to scan {source['name']}: {e}")
        self._save_cache(all_articles)
        return all_articles

    def get_takeaways(self, articles: list[dict], count: int = 5) -> list[dict]:
        """Use LLM to extract key takeaways aligned with content strategy."""
        if not articles:
            return []
        if not self.llm_client:
            logger.warning("No LLM client configured, returning raw articles")
            return articles[:count]

        articles_text = "\n\n".join(
            f"[{a['source']}] {a['title']}\n{a.get('summary', '')}\nURL: {a.get('url', '')}"
            for a in articles[:20]
        )

        prompt = f"""You are a crypto/web3 content strategist. Analyze these trending articles and extract the {count} most important takeaways that would be relevant for a builder-focused Twitter account.

The content strategy focuses on:
1. Operator Stories - real lessons from building
2. Web2 to Web3 Translation - same dynamics, new rails
3. User Empathy, Metrics & Frameworks - signal over noise
4. Philosophy for Builders - human emotion meets execution

Core thesis: Crypto needs hundreds of millions onchain through financial apps (payments, stablecoins, DeFi) before other categories take off. Blockchains enable coordinating people and capital at internet scale with embedded ownership.

Articles:
{articles_text}

Return a JSON array of {count} takeaways, each with:
- "headline": one-line summary of the trend/news
- "insight": the deeper takeaway for builders (1-2 sentences)
- "pillar": which content pillar it best fits ("operator_stories", "web2_web3_translation", "user_empathy_metrics", or "philosophy_for_builders")
- "source_url": the original article URL
- "source_name": the source name

Return ONLY valid JSON, no other text."""

        response = self.llm_client.messages.create(
            model=self.llm_config.get("model", "claude-sonnet-4-5-20250929"),
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            text = response.content[0].text.strip()
            # Handle markdown code fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to parse LLM takeaways response: {e}")
            return []

    def _scan_source(self, source: dict, max_articles: int) -> list[dict]:
        """Scan a single news source."""
        source_type = source.get("type", "rss")
        if source_type == "rss":
            return self._scan_rss(source, max_articles)
        return self._scan_html(source, max_articles)

    def _scan_rss(self, source: dict, max_articles: int) -> list[dict]:
        """Parse an RSS feed."""
        feed = feedparser.parse(source["url"], agent=USER_AGENT)
        articles = []
        for entry in feed.entries[:max_articles]:
            articles.append({
                "title": entry.get("title", ""),
                "summary": _clean_html(entry.get("summary", "")),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": source["name"],
            })
        return articles

    def _scan_html(self, source: dict, max_articles: int) -> list[dict]:
        """Scrape article links from a news site homepage."""
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = []
        seen_urls = set()

        # Generic extraction: find article links with titles
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            title = tag.get_text(strip=True)

            if not title or len(title) < 20:
                continue
            if not href.startswith("http"):
                href = source["url"].rstrip("/") + href
            if href in seen_urls:
                continue

            # Filter for article-like URLs
            if any(skip in href for skip in ["/tag/", "/author/", "/category/", "#", "javascript:"]):
                continue

            seen_urls.add(href)
            articles.append({
                "title": title,
                "summary": "",
                "url": href,
                "published": "",
                "source": source["name"],
            })

            if len(articles) >= max_articles:
                break

        return articles

    def _save_cache(self, articles: list[dict]):
        """Cache articles to disk."""
        os.makedirs(self.data_dir, exist_ok=True)
        cache = {
            "fetched_at": datetime.utcnow().isoformat(),
            "articles": articles,
        }
        with open(self._cache_path, "w") as f:
            json.dump(cache, f, indent=2)

    def load_cache(self, max_age_hours: int = 6) -> list[dict] | None:
        """Load cached articles if fresh enough."""
        if not os.path.exists(self._cache_path):
            return None
        try:
            with open(self._cache_path, "r") as f:
                cache = json.load(f)
            fetched = datetime.fromisoformat(cache["fetched_at"])
            if datetime.utcnow() - fetched > timedelta(hours=max_age_hours):
                return None
            return cache["articles"]
        except (json.JSONDecodeError, KeyError):
            return None


def _clean_html(text: str) -> str:
    """Strip HTML tags from a string."""
    if "<" in text:
        return BeautifulSoup(text, "html.parser").get_text(strip=True)
    return text.strip()
