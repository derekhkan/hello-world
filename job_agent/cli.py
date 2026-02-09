"""CLI interface for the job application agent."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from job_agent.config import (
    AgentConfig,
    init_config_dir,
    load_config,
    save_config,
)
from job_agent.models import ApplicationStatus, JobBoard
from job_agent.orchestrator import JobApplicationOrchestrator

console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.option("--config", "-c", type=click.Path(), default=None, help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx: click.Context, config: str | None, verbose: bool) -> None:
    """Job Application Agent - Automated job search and application."""
    setup_logging(verbose)
    config_path = Path(config) if config else None
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize the agent with your profile and preferences."""
    config = ctx.obj["config"]

    console.print(Panel("Job Application Agent Setup", style="bold blue"))
    console.print()

    # Collect profile information
    console.print("[bold]Your Profile[/bold]")
    config.profile.first_name = click.prompt("First name", default=config.profile.first_name or "")
    config.profile.last_name = click.prompt("Last name", default=config.profile.last_name or "")
    config.profile.email = click.prompt("Email", default=config.profile.email or "")
    config.profile.phone = click.prompt("Phone", default=config.profile.phone or "")
    config.profile.location = click.prompt("Location (city, state)", default=config.profile.location or "")
    config.profile.linkedin_url = click.prompt("LinkedIn URL", default=config.profile.linkedin_url or "")
    config.profile.github_url = click.prompt("GitHub URL", default=config.profile.github_url or "")
    config.profile.portfolio_url = click.prompt("Portfolio URL", default=config.profile.portfolio_url or "")

    resume_path = click.prompt(
        "Path to your resume (txt/pdf)",
        default=config.profile.resume_path or "",
    )
    if resume_path:
        config.profile.resume_path = str(Path(resume_path).expanduser().resolve())

    skills_input = click.prompt(
        "Skills (comma-separated)",
        default=", ".join(config.profile.skills) if config.profile.skills else "",
    )
    config.profile.skills = [s.strip() for s in skills_input.split(",") if s.strip()]

    summary = click.prompt(
        "Professional summary (1-2 sentences)",
        default=config.profile.summary or "",
    )
    config.profile.summary = summary

    console.print()
    console.print("[bold]Search Preferences[/bold]")

    keywords = click.prompt(
        "Search keywords (comma-separated)",
        default=", ".join(config.search.keywords) if config.search.keywords else "",
    )
    config.search.keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    titles = click.prompt(
        "Target job titles (comma-separated)",
        default=", ".join(config.search.titles) if config.search.titles else "",
    )
    config.search.titles = [t.strip() for t in titles.split(",") if t.strip()]

    locations = click.prompt(
        "Preferred locations (comma-separated, or 'remote')",
        default=", ".join(config.search.locations) if config.search.locations else "",
    )
    config.search.locations = [loc.strip() for loc in locations.split(",") if loc.strip()]

    config.search.remote_only = click.confirm("Remote only?", default=config.search.remote_only)

    salary = click.prompt("Minimum salary (annual, or 0 to skip)", type=int, default=config.search.salary_min or 0)
    config.search.salary_min = salary if salary > 0 else None

    config.search.max_applications_per_day = click.prompt(
        "Max applications per day",
        type=int,
        default=config.search.max_applications_per_day,
    )

    config.search.auto_apply = click.confirm(
        "Enable auto-apply?", default=config.search.auto_apply
    )

    console.print()
    console.print("[bold]Job Boards[/bold]")
    boards = []
    for board in JobBoard:
        if click.confirm(f"Search {board.value.title()}?", default=True):
            boards.append(board)
    config.search.boards = boards

    # LLM configuration
    console.print()
    console.print("[bold]AI Configuration[/bold]")
    config.llm.api_key = click.prompt(
        "OpenAI API key",
        default=config.llm.api_key or "",
        hide_input=True,
    )

    # Save config
    init_config_dir(config)
    save_config(config)
    console.print()
    console.print("[green]Configuration saved![/green]")
    console.print(f"Config directory: {config.config_dir}")


@main.command()
@click.option("--min-score", type=float, default=0.3, help="Minimum match score (0.0-1.0)")
@click.option("--auto-apply", is_flag=True, help="Automatically submit applications")
@click.option("--dry-run", is_flag=True, help="Discover and score without applying")
@click.pass_context
def run(ctx: click.Context, min_score: float, auto_apply: bool, dry_run: bool) -> None:
    """Run the full job search and application pipeline."""
    config = ctx.obj["config"]

    if not config.profile.first_name:
        console.print("[red]Profile not configured. Run 'job-agent init' first.[/red]")
        return

    if not config.search.keywords:
        console.print("[red]No search keywords set. Run 'job-agent init' first.[/red]")
        return

    console.print(Panel("Starting Job Application Pipeline", style="bold blue"))

    if dry_run:
        console.print("[yellow]DRY RUN mode - no applications will be submitted[/yellow]")

    orchestrator = JobApplicationOrchestrator(config)
    try:
        results = orchestrator.run_full_pipeline(
            min_score=min_score,
            auto_apply=auto_apply,
            dry_run=dry_run,
        )

        # Display results
        table = Table(title="Pipeline Results")
        table.add_column("Stage", style="bold")
        table.add_column("Count", justify="right")

        table.add_row("Jobs Discovered", str(results["discovered"]))
        table.add_row("Jobs Scored (above threshold)", str(results["scored"]))
        table.add_row("Applications Prepared", str(results["prepared"]))
        table.add_row("Applications Submitted", str(results["submitted"]))
        table.add_row("Applications Failed", str(results["failed"]))

        console.print()
        console.print(table)

    finally:
        orchestrator.close()


@main.command()
@click.pass_context
def search(ctx: click.Context) -> None:
    """Search for jobs without applying."""
    config = ctx.obj["config"]
    orchestrator = JobApplicationOrchestrator(config)

    try:
        jobs = orchestrator.discover_jobs()

        if not jobs:
            console.print("[yellow]No new jobs found.[/yellow]")
            return

        table = Table(title=f"Found {len(jobs)} New Jobs")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="bold")
        table.add_column("Company")
        table.add_column("Location")
        table.add_column("Board")
        table.add_column("Easy Apply")

        for i, job in enumerate(jobs[:50], 1):
            table.add_row(
                str(i),
                job.title[:50],
                job.company[:30],
                job.location[:25],
                job.board.value,
                "Yes" if job.easy_apply else "",
            )

        console.print(table)

    finally:
        orchestrator.close()


@main.command()
@click.option("--status", type=click.Choice([s.value for s in ApplicationStatus]), default=None)
@click.option("--board", type=click.Choice([b.value for b in JobBoard]), default=None)
@click.option("--limit", type=int, default=20)
@click.pass_context
def status(ctx: click.Context, status: str | None, board: str | None, limit: int) -> None:
    """View application tracking dashboard."""
    config = ctx.obj["config"]
    db_path = config.db_path

    if not db_path.exists():
        console.print("[yellow]No applications tracked yet. Run 'job-agent run' first.[/yellow]")
        return

    from job_agent.utils.database import Database

    db = Database(db_path)

    # Stats panel
    stats = db.get_stats()
    stats_table = Table(title="Application Statistics", show_header=False)
    stats_table.add_column("Metric", style="bold")
    stats_table.add_column("Value", justify="right")

    stats_table.add_row("Total Applications", str(stats["total"]))
    stats_table.add_row("Applied Today", str(stats["applied_today"]))

    for status_name, count in stats.get("by_status", {}).items():
        stats_table.add_row(f"  {status_name}", str(count))

    console.print(stats_table)
    console.print()

    # Recent applications
    status_filter = ApplicationStatus(status) if status else None
    apps = db.get_applications(status=status_filter, board=board, limit=limit)

    if not apps:
        console.print("[yellow]No applications match the filter.[/yellow]")
        return

    app_table = Table(title="Applications")
    app_table.add_column("ID", style="dim", width=4)
    app_table.add_column("Title", style="bold")
    app_table.add_column("Company")
    app_table.add_column("Board")
    app_table.add_column("Status")
    app_table.add_column("Score", justify="right")
    app_table.add_column("Applied")

    for app in apps:
        status_style = {
            "submitted": "green",
            "interview": "bold green",
            "offer": "bold yellow",
            "failed": "red",
            "rejected": "dim red",
        }.get(app["status"], "")

        app_table.add_row(
            str(app["app_id"]),
            app["title"][:40],
            app["company"][:25],
            app["board"],
            f"[{status_style}]{app['status']}[/{status_style}]" if status_style else app["status"],
            f"{app['match_score']:.0%}",
            str(app["applied_at"] or "")[:10],
        )

    console.print(app_table)


@main.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv")
@click.option("--output", "-o", type=click.Path(), default=None)
@click.pass_context
def export(ctx: click.Context, fmt: str, output: str | None) -> None:
    """Export application data to CSV or JSON."""
    import csv
    import json
    from io import StringIO

    config = ctx.obj["config"]

    if not config.db_path.exists():
        console.print("[yellow]No data to export.[/yellow]")
        return

    from job_agent.utils.database import Database

    db = Database(config.db_path)
    apps = db.get_applications(limit=10000)

    if not apps:
        console.print("[yellow]No applications to export.[/yellow]")
        return

    if output is None:
        output_dir = config.data_dir / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = str(output_dir / f"applications.{fmt}")

    if fmt == "csv":
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=apps[0].keys())
            writer.writeheader()
            writer.writerows(apps)
    else:
        with open(output, "w") as f:
            json.dump(apps, f, indent=2, default=str)

    console.print(f"[green]Exported {len(apps)} applications to {output}[/green]")


@main.command()
@click.pass_context
def summary(ctx: click.Context) -> None:
    """Send a daily summary email."""
    config = ctx.obj["config"]

    if not config.db_path.exists():
        console.print("[yellow]No data for summary.[/yellow]")
        return

    from job_agent.utils.database import Database
    from job_agent.utils.notifications import NotificationService

    db = Database(config.db_path)
    notifier = NotificationService(config)

    stats = db.get_stats()
    recent = db.get_applications(limit=20)

    success = notifier.send_daily_summary(stats, recent)
    if success:
        console.print("[green]Daily summary email sent![/green]")
    else:
        console.print("[red]Failed to send summary. Check notification config.[/red]")


if __name__ == "__main__":
    main()
