#!/usr/bin/env python3
"""X/Twitter Agent — CLI entry point.

Usage:
    python main_x.py run [--dry-run]         Start daemon (posts at scheduled times)
    python main_x.py post [--dry-run]        Run pipeline once (scan → generate → post)
    python main_x.py preview [--count N]     Generate tweets for preview (no posting)
    python main_x.py scan-news               Scan news sources and show takeaways
    python main_x.py engagement [--days N]   Show engagement summary
    python main_x.py ab-report               Show A/B time slot test results
"""

import argparse
import json
import logging
import sys

import anthropic

from x_agent.config import load_config
from x_agent.client import XClient
from x_agent.news_scanner import NewsScanner
from x_agent.content_generator import ContentGenerator
from x_agent.content_calendar import ContentCalendar
from x_agent.scheduler import ABScheduler
from x_agent.content_manager import ContentManager


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_manager(config: dict) -> ContentManager:
    """Wire up all components and return the ContentManager."""
    llm_client = anthropic.Anthropic(api_key=config["llm"]["api_key"])

    client = XClient(config)
    news_scanner = NewsScanner(config, llm_client=llm_client)
    generator = ContentGenerator(config, llm_client=llm_client)
    calendar = ContentCalendar(config)
    scheduler = ABScheduler(config)

    return ContentManager(
        config=config,
        client=client,
        news_scanner=news_scanner,
        generator=generator,
        calendar=calendar,
        scheduler=scheduler,
    )


def cmd_run(manager: ContentManager, args):
    """Start the daemon."""
    manager.run_daemon(dry_run=args.dry_run)


def cmd_post(manager: ContentManager, args):
    """Run pipeline once."""
    result = manager.run_once(dry_run=args.dry_run)
    status = "DRY RUN" if args.dry_run else "POSTED"
    print(f"\n[{status}]")
    print(f"Pillar:  {result['pillar']}")
    print(f"Format:  {result['format']}")
    print(f"Tweet:   {result['tweet']}")
    if result.get("tweet_id"):
        print(f"ID:      {result['tweet_id']}")
    if result.get("news"):
        print(f"News:    {result['news'].get('headline', '')}")


def cmd_preview(manager: ContentManager, args):
    """Generate tweets for preview."""
    previews = manager.generate_preview(count=args.count)
    for i, p in enumerate(previews, 1):
        print(f"\n--- Tweet {i} ---")
        print(f"Pillar:  {p['pillar']}")
        print(f"Format:  {p['format']}")
        print(f"Tweet:   {p['tweet']}")
        print(f"Chars:   {len(p['tweet'])}")
        if p.get("news"):
            print(f"News:    {p['news'].get('headline', '')}")


def cmd_scan_news(manager: ContentManager, _args):
    """Scan news and show takeaways."""
    result = manager.scan_news()
    print(f"\nArticles found: {result['articles_found']}")
    print(f"\nKey Takeaways:")
    for i, t in enumerate(result["takeaways"], 1):
        print(f"\n  {i}. [{t.get('pillar', '?')}] {t.get('headline', '')}")
        print(f"     {t.get('insight', '')}")
        print(f"     Source: {t.get('source_name', '')} — {t.get('source_url', '')}")


def cmd_engagement(manager: ContentManager, args):
    """Show engagement summary."""
    summary = manager.get_engagement_summary(days=args.days)
    print(f"\nEngagement Summary (last {args.days} days)")
    print(f"Posts: {summary.get('total_posts', 0)} | Tracked: {summary.get('tracked', 0)}")
    if "totals" in summary:
        t = summary["totals"]
        print(f"\nTotals:")
        print(f"  Impressions: {t['impressions']:,}")
        print(f"  Likes:       {t['likes']:,}")
        print(f"  Retweets:    {t['retweets']:,}")
        print(f"  Replies:     {t['replies']:,}")
        print(f"  Bookmarks:   {t['bookmarks']:,}")
    if "averages" in summary:
        a = summary["averages"]
        print(f"\nAverages per tweet:")
        print(f"  Impressions: {a['impressions']}")
        print(f"  Likes:       {a['likes']}")
        print(f"  Retweets:    {a['retweets']}")
        print(f"  Replies:     {a['replies']}")
    if "by_pillar" in summary:
        print(f"\nBy Pillar:")
        for pillar, data in summary["by_pillar"].items():
            print(f"  {pillar}: {data['count']} posts, avg {data.get('avg_impressions', 0)} impressions, avg {data.get('avg_likes', 0)} likes")


def cmd_ab_report(manager: ContentManager, _args):
    """Show A/B test results."""
    report = manager.get_ab_report()
    for group in ["morning", "evening"]:
        slots = report.get(group, {})
        if not slots:
            print(f"\n{group.title()}: No data yet")
            continue
        print(f"\n{group.title()} Slots:")
        for slot, stats in sorted(slots.items()):
            conf = "***" if stats["n_samples"] >= 10 else "**" if stats["n_samples"] >= 5 else "*"
            print(f"  {slot} — avg score: {stats['avg_score']:.2f} | n={stats['n_samples']} {conf}")
            if stats.get("avg_metrics"):
                m = stats["avg_metrics"]
                print(f"         avg impressions: {m.get('impression_count', 0)}, likes: {m.get('like_count', 0)}, RTs: {m.get('retweet_count', 0)}")

    rec = report.get("recommendation", {})
    if rec:
        print(f"\nRecommendation:")
        for group, r in rec.items():
            print(f"  {group.title()}: post at {r['best_time']} (score={r['avg_score']:.2f}, confidence={r['confidence']}, n={r['n_samples']})")


def main():
    parser = argparse.ArgumentParser(description="X/Twitter Agent")
    parser.add_argument("--config", default="x_config.yaml", help="Config file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Start daemon")
    p_run.add_argument("--dry-run", action="store_true", help="Generate but don't post")

    # post
    p_post = subparsers.add_parser("post", help="Run pipeline once")
    p_post.add_argument("--dry-run", action="store_true", help="Generate but don't post")

    # preview
    p_preview = subparsers.add_parser("preview", help="Preview generated tweets")
    p_preview.add_argument("--count", type=int, default=2, help="Number of tweets")

    # scan-news
    subparsers.add_parser("scan-news", help="Scan news sources")

    # engagement
    p_eng = subparsers.add_parser("engagement", help="Engagement summary")
    p_eng.add_argument("--days", type=int, default=7, help="Lookback days")

    # ab-report
    subparsers.add_parser("ab-report", help="A/B test results")

    args = parser.parse_args()
    setup_logging(args.verbose)

    config = load_config(args.config)
    manager = build_manager(config)

    commands = {
        "run": cmd_run,
        "post": cmd_post,
        "preview": cmd_preview,
        "scan-news": cmd_scan_news,
        "engagement": cmd_engagement,
        "ab-report": cmd_ab_report,
    }
    commands[args.command](manager, args)


if __name__ == "__main__":
    main()
