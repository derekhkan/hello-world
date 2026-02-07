"""Tweet generation using LLM aligned with content strategy."""

import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content Strategy — embedded as prompt context
# ---------------------------------------------------------------------------

CORE_NARRATIVE = """Execution turns complex systems into simple outcomes.
Only once hundreds of millions of people were online did entirely new cultural and economic categories emerge.
Crypto is likely no different. We likely need hundreds of millions of people onchain through financial applications — payments, stablecoins, savings, DeFi — before meaningful adoption in categories like media, gaming, AI, or others further out.
Many applications depend on wallets, identity, liquidity, and trust already being in place.
The core idea: blockchains introduce a new primitive — the ability to coordinate people and capital at internet scale, with ownership embedded directly into the system. And increasingly, to coordinate AI agents too."""

PILLARS = {
    "operator_stories": {
        "name": "Operator Stories",
        "description": "Real moments → real lessons. Tradeoffs, failures, decisions, constraints. What worked, what didn't, why it mattered.",
        "question": "What did reality teach me here?",
    },
    "web2_web3_translation": {
        "name": "Web2 ↔ Web3 Translation",
        "description": "Same dynamics, new rails. Marketplaces, ad exchanges, rebates, loyalty. How these patterns show up in DeFi, tokens, liquidity.",
        "question": "What would this be called in Web2?",
    },
    "user_empathy_metrics": {
        "name": "User Empathy, Metrics & Frameworks",
        "description": "Signal over noise. What's the user mindset, are we relating to that? How does that translate to a metric?",
        "question": "What would I actually track?",
    },
    "philosophy_for_builders": {
        "name": "Philosophy for Builders",
        "description": "Human emotion → operating behavior. Anxiety, impatience, control, ambition. Stoic ideas grounded in daily execution. Always end with a concrete practice, not inspiration.",
        "question": "What's the concrete practice?",
    },
}

FORMATS = {
    "story_lesson_principle": {
        "name": "Story → Lesson → Principle",
        "structure": "Moment → Tension → Decision → Lesson → Principle + takeaway",
    },
    "calm_contrarian": {
        "name": "Calm Contrarian Take",
        "structure": "Clear claim → Why people miss it → 2-3 supporting points → What to do instead",
    },
    "web2_translation": {
        "name": "Web2 Translation",
        "structure": '"In Web2, this was ___." → "In Web3, it shows up as ___." → "Same incentive structure." → Trap + fix.',
    },
    "one_metric_truth": {
        "name": "One Metric Truth",
        "structure": "Name the metric → Why it matters → What it replaces → How to use it",
    },
}


class ContentGenerator:
    """Generates tweets using an LLM, guided by content strategy and news."""

    def __init__(self, config: dict, llm_client=None):
        self.llm_client = llm_client
        self.llm_config = config.get("llm", {})

    def generate_tweet(
        self,
        pillar: str,
        fmt: str,
        news_takeaway: dict | None = None,
    ) -> str:
        """Generate a single tweet for the given pillar and format.

        Args:
            pillar: One of the PILLARS keys.
            fmt: One of the FORMATS keys.
            news_takeaway: Optional news takeaway dict from NewsScanner.

        Returns:
            Tweet text (≤280 chars).
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for tweet generation")

        pillar_info = PILLARS[pillar]
        format_info = FORMATS[fmt]

        news_context = ""
        if news_takeaway:
            news_context = f"""
Use this trending news as inspiration (do NOT just summarize it — extract an original insight):
Headline: {news_takeaway.get('headline', '')}
Insight: {news_takeaway.get('insight', '')}
Source: {news_takeaway.get('source_name', '')}"""

        system_prompt = f"""You are a sharp, concise crypto/web3 Twitter voice. You write tweets for builders who are deep in the space — not hype, not fluff.

Core thesis you operate from:
{CORE_NARRATIVE}

Your tone: calm authority. You've built things. You've seen cycles. You share real signal. No emojis. No hashtags. No "GM" or "WAGMI". No engagement bait. No questions at the end asking people to reply.

Write like a builder talking to other builders. Short sentences. Clear thinking."""

        user_prompt = f"""Write ONE tweet (max 280 characters, hard limit).

Content pillar: {pillar_info['name']}
— {pillar_info['description']}
— Ask yourself: "{pillar_info['question']}"

Format: {format_info['name']}
— Structure: {format_info['structure']}
{news_context}

Rules:
- MUST be 280 characters or fewer
- No hashtags, no emojis, no @ mentions
- No "hot take:" or "unpopular opinion:" prefixes
- Sound like a real person, not a content bot
- Be specific, not generic. Use concrete examples when possible
- If philosophy pillar: end with a concrete practice

Return ONLY the tweet text, nothing else."""

        response = self.llm_client.messages.create(
            model=self.llm_config.get("model", "claude-sonnet-4-5-20250929"),
            max_tokens=300,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        tweet = response.content[0].text.strip().strip('"')

        # Enforce character limit — retry once if over
        if len(tweet) > 280:
            logger.warning(f"Tweet too long ({len(tweet)} chars), requesting shorter version")
            tweet = self._shorten(tweet)

        return tweet

    def generate_batch(
        self,
        assignments: list[dict],
        news_takeaways: list[dict] | None = None,
    ) -> list[dict]:
        """Generate multiple tweets for a batch of pillar/format assignments.

        Args:
            assignments: List of {"pillar": str, "format": str} dicts.
            news_takeaways: Optional list of news takeaways to distribute.

        Returns:
            List of {"pillar": str, "format": str, "tweet": str, "news": dict|None}.
        """
        results = []
        for i, assignment in enumerate(assignments):
            takeaway = None
            if news_takeaways and i < len(news_takeaways):
                takeaway = news_takeaways[i]

            tweet = self.generate_tweet(
                pillar=assignment["pillar"],
                fmt=assignment["format"],
                news_takeaway=takeaway,
            )
            results.append({
                "pillar": assignment["pillar"],
                "format": assignment["format"],
                "tweet": tweet,
                "news": takeaway,
            })
        return results

    def _shorten(self, tweet: str) -> str:
        """Ask the LLM to shorten a tweet to fit within 280 chars."""
        response = self.llm_client.messages.create(
            model=self.llm_config.get("model", "claude-sonnet-4-5-20250929"),
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"This tweet is too long. Rewrite it to be under 280 characters while keeping the core insight. Return ONLY the tweet text.\n\n{tweet}",
            }],
        )
        shortened = response.content[0].text.strip().strip('"')
        if len(shortened) > 280:
            # Hard truncate as last resort
            shortened = shortened[:277] + "..."
            logger.warning("Had to hard-truncate tweet")
        return shortened
