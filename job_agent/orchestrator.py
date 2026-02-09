"""Main orchestrator that coordinates scraping, tailoring, and applying."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from job_agent.config import AgentConfig, init_config_dir
from job_agent.engines.applicator import ApplicatorEngine
from job_agent.engines.tailoring import TailoringEngine
from job_agent.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobBoard,
    JobListing,
)
from job_agent.scrapers import SCRAPERS
from job_agent.utils.database import Database
from job_agent.utils.notifications import NotificationService

logger = logging.getLogger(__name__)


class JobApplicationOrchestrator:
    """Coordinates the full job application pipeline."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        init_config_dir(config)
        self.db = Database(config.db_path)
        self.tailoring = TailoringEngine(config)
        self.applicator = ApplicatorEngine(config)
        self.notifications = NotificationService(config)

    def discover_jobs(self) -> list[JobListing]:
        """Search all configured job boards and collect new listings."""
        all_jobs: list[JobListing] = []

        for board in self.config.search.boards:
            scraper_cls = SCRAPERS.get(board.value)
            if scraper_cls is None:
                logger.warning(f"No scraper available for {board.value}")
                continue

            logger.info(f"Searching {board.value}...")
            scraper = scraper_cls(self.config)

            try:
                jobs = scraper.search_jobs(self.config.search)
                new_count = 0

                for job in jobs:
                    if not self.db.is_duplicate(
                        job.external_id,
                        job.board.value,
                        self.config.dedup_window_days,
                    ):
                        # Fetch full details
                        try:
                            job = scraper.get_job_details(job)
                        except Exception as e:
                            logger.warning(f"Failed to get details for {job.title}: {e}")

                        all_jobs.append(job)
                        new_count += 1
                    else:
                        logger.debug(f"Skipping duplicate: {job.title} at {job.company}")

                logger.info(
                    f"{board.value}: found {len(jobs)} jobs, {new_count} new"
                )

            except Exception as e:
                logger.error(f"Failed to search {board.value}: {e}")
            finally:
                scraper.close()

        logger.info(f"Total new jobs discovered: {len(all_jobs)}")
        return all_jobs

    def score_and_rank(
        self, jobs: list[JobListing], min_score: float = 0.3
    ) -> list[ApplicationRecord]:
        """Score each job against the user profile and rank by match quality."""
        scored: list[ApplicationRecord] = []
        profile = self.config.profile

        for job in jobs:
            try:
                match_result = self.tailoring.score_match(job, profile)
                score = match_result.get("score", 0.0)

                if score < min_score:
                    logger.info(
                        f"Skipping low match ({score:.2f}): {job.title} at {job.company}"
                    )
                    continue

                app = ApplicationRecord(
                    job=job,
                    match_score=score,
                    match_reasons=match_result.get("reasons", []),
                )

                # Save to database
                job_id = self.db.save_job(job)
                self.db.save_application(app, job_id)

                scored.append(app)
                logger.info(
                    f"Match {score:.2f}: {job.title} at {job.company}"
                )

            except Exception as e:
                logger.error(f"Failed to score {job.title}: {e}")

        # Sort by match score descending
        scored.sort(key=lambda a: a.match_score, reverse=True)
        logger.info(f"Scored {len(scored)} jobs above threshold {min_score}")
        return scored

    def prepare_applications(
        self, applications: list[ApplicationRecord]
    ) -> list[ApplicationRecord]:
        """Tailor resume and generate cover letter for each application."""
        prepared: list[ApplicationRecord] = []
        profile = self.config.profile

        for app in applications:
            try:
                app.update_status(ApplicationStatus.TAILORING)

                # Tailor resume if available
                if profile.resume_path:
                    from pathlib import Path

                    try:
                        resume_content = Path(profile.resume_path).read_text()
                        tailored = self.tailoring.tailor_resume(
                            app.job, profile, resume_content
                        )

                        output_dir = self.config.data_dir / "resumes"
                        output_dir.mkdir(parents=True, exist_ok=True)
                        filename = (
                            f"resume_{app.job.company}_{app.job.external_id}.txt"
                            .replace(" ", "_")
                            .lower()
                        )
                        path = output_dir / filename
                        path.write_text(tailored)
                        app.tailored_resume_path = str(path)
                    except Exception as e:
                        logger.warning(f"Resume tailoring failed: {e}")

                # Generate cover letter
                try:
                    cover_letter = self.tailoring.generate_cover_letter(
                        app.job, profile
                    )

                    output_dir = self.config.data_dir / "cover_letters"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    filename = (
                        f"cover_{app.job.company}_{app.job.external_id}.txt"
                        .replace(" ", "_")
                        .lower()
                    )
                    path = output_dir / filename
                    path.write_text(cover_letter)
                    app.cover_letter_path = str(path)
                except Exception as e:
                    logger.warning(f"Cover letter generation failed: {e}")

                app.update_status(ApplicationStatus.QUEUED)
                prepared.append(app)

            except Exception as e:
                logger.error(
                    f"Failed to prepare {app.job.title} at {app.job.company}: {e}"
                )

        return prepared

    def submit_applications(
        self, applications: list[ApplicationRecord], dry_run: bool = False
    ) -> list[ApplicationRecord]:
        """Submit applications, respecting daily limits."""
        stats = self.db.get_stats()
        applied_today = stats.get("applied_today", 0)
        daily_limit = self.config.search.max_applications_per_day
        remaining = max(0, daily_limit - applied_today)

        if remaining == 0:
            logger.warning(
                f"Daily application limit reached ({daily_limit}). "
                "Try again tomorrow."
            )
            return []

        to_submit = applications[:remaining]
        submitted: list[ApplicationRecord] = []
        profile = self.config.profile

        for app in to_submit:
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would apply to {app.job.title} at {app.job.company} "
                    f"(score: {app.match_score:.2f})"
                )
                app.update_status(
                    ApplicationStatus.QUEUED, "Dry run - not submitted"
                )
                submitted.append(app)
                continue

            try:
                result = self.applicator.apply(app, profile)
                submitted.append(result)

                # Send notification
                if result.status == ApplicationStatus.SUBMITTED:
                    self.notifications.notify_application_submitted(result)
                elif result.status == ApplicationStatus.FAILED:
                    last_note = ""
                    if result.status_history:
                        last_note = result.status_history[-1].get("note", "")
                    self.notifications.notify_error(result, last_note)

                # Rate limit between applications
                time.sleep(self.config.rate_limit_delay)

            except Exception as e:
                logger.error(
                    f"Error submitting to {app.job.title} at {app.job.company}: {e}"
                )

        return submitted

    def run_full_pipeline(
        self,
        min_score: float = 0.3,
        auto_apply: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Run the complete discover -> score -> prepare -> apply pipeline."""
        logger.info("Starting full job application pipeline")
        results = {
            "discovered": 0,
            "scored": 0,
            "prepared": 0,
            "submitted": 0,
            "failed": 0,
        }

        # Step 1: Discover jobs
        jobs = self.discover_jobs()
        results["discovered"] = len(jobs)

        if not jobs:
            logger.info("No new jobs found.")
            return results

        # Step 2: Score and rank
        scored = self.score_and_rank(jobs, min_score)
        results["scored"] = len(scored)

        if not scored:
            logger.info("No jobs matched above the minimum score.")
            return results

        # Step 3: Prepare applications
        prepared = self.prepare_applications(scored)
        results["prepared"] = len(prepared)

        # Step 4: Submit (if auto-apply enabled)
        if auto_apply or self.config.search.auto_apply:
            submitted = self.submit_applications(prepared, dry_run=dry_run)
            for app in submitted:
                if app.status == ApplicationStatus.SUBMITTED:
                    results["submitted"] += 1
                elif app.status == ApplicationStatus.FAILED:
                    results["failed"] += 1

        logger.info(f"Pipeline complete: {results}")
        return results

    def get_dashboard_data(self) -> dict:
        """Get data for the CLI dashboard."""
        stats = self.db.get_stats()
        recent = self.db.get_applications(limit=20)
        return {"stats": stats, "recent_applications": recent}

    def close(self) -> None:
        """Clean up all resources."""
        self.applicator.close()
