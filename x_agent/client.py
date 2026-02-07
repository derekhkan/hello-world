"""Twitter/X API client wrapper using tweepy."""

import logging
import tweepy

logger = logging.getLogger(__name__)


class XClient:
    """Wrapper around tweepy for Twitter API v2 (and v1.1 for media)."""

    def __init__(self, config: dict):
        tw = config["twitter"]

        # v2 client for tweets and metrics
        self.client = tweepy.Client(
            bearer_token=tw["bearer_token"],
            consumer_key=tw["api_key"],
            consumer_secret=tw["api_secret"],
            access_token=tw["access_token"],
            access_token_secret=tw["access_token_secret"],
            wait_on_rate_limit=True,
        )

        # v1.1 auth for media uploads (if needed later)
        auth = tweepy.OAuth1UserHandler(
            tw["api_key"],
            tw["api_secret"],
            tw["access_token"],
            tw["access_token_secret"],
        )
        self.api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

        self._user_id = None

    @property
    def user_id(self) -> str:
        if self._user_id is None:
            me = self.client.get_me()
            self._user_id = me.data.id
        return self._user_id

    def post_tweet(self, text: str) -> dict:
        """Post a tweet and return the response data."""
        if len(text) > 280:
            raise ValueError(f"Tweet exceeds 280 chars ({len(text)})")

        response = self.client.create_tweet(text=text)
        tweet_id = response.data["id"]
        logger.info(f"Posted tweet {tweet_id}: {text[:80]}...")
        return {"id": tweet_id, "text": text}

    def get_tweet_metrics(self, tweet_id: str) -> dict:
        """Fetch public and non-public metrics for a tweet.

        Requires the tweet author to have the appropriate access level.
        """
        response = self.client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics", "non_public_metrics", "created_at"],
            user_auth=True,
        )
        if not response.data:
            logger.warning(f"No data returned for tweet {tweet_id}")
            return {}

        metrics = {}
        if response.data.public_metrics:
            metrics.update(response.data.public_metrics)
        if response.data.non_public_metrics:
            metrics.update(response.data.non_public_metrics)
        metrics["created_at"] = str(response.data.created_at) if response.data.created_at else None
        return metrics

    def get_recent_tweets(self, count: int = 20) -> list[dict]:
        """Fetch recent tweets from the authenticated user."""
        response = self.client.get_users_tweets(
            self.user_id,
            max_results=min(count, 100),
            tweet_fields=["public_metrics", "non_public_metrics", "created_at"],
            user_auth=True,
        )
        if not response.data:
            return []

        tweets = []
        for tweet in response.data:
            entry = {
                "id": tweet.id,
                "text": tweet.text,
                "created_at": str(tweet.created_at) if tweet.created_at else None,
            }
            if tweet.public_metrics:
                entry.update(tweet.public_metrics)
            if tweet.non_public_metrics:
                entry.update(tweet.non_public_metrics)
            tweets.append(entry)
        return tweets
