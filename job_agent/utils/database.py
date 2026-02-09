"""SQLite database layer for tracking applications."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from job_agent.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobBoard,
    JobListing,
)

Base = declarative_base()


class JobRow(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String, nullable=False)
    board = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, default="")
    work_mode = Column(String, nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_text = Column(String, default="")
    description = Column(Text, default="")
    requirements = Column(Text, default="[]")
    experience_level = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    posted_date = Column(DateTime, nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    easy_apply = Column(Boolean, default=False)
    application_url = Column(String, nullable=True)


class ApplicationRow(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False)
    status = Column(String, default=ApplicationStatus.DISCOVERED.value)
    tailored_resume_path = Column(String, nullable=True)
    cover_letter_path = Column(String, nullable=True)
    match_score = Column(Float, default=0.0)
    match_reasons = Column(Text, default="[]")
    applied_at = Column(DateTime, nullable=True)
    status_history = Column(Text, default="[]")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Database:
    """Application tracking database."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine)

    def _session(self) -> Session:
        return self._Session()

    # --- Jobs ---

    def save_job(self, job: JobListing) -> int:
        """Insert or update a job listing. Returns the row id."""
        with self._session() as session:
            existing = (
                session.query(JobRow)
                .filter_by(external_id=job.external_id, board=job.board.value)
                .first()
            )
            if existing:
                existing.title = job.title
                existing.description = job.description
                existing.salary_text = job.salary_text
                session.commit()
                return existing.id

            row = JobRow(
                external_id=job.external_id,
                board=job.board.value,
                url=job.url,
                title=job.title,
                company=job.company,
                location=job.location,
                work_mode=job.work_mode.value if job.work_mode else None,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_text=job.salary_text,
                description=job.description,
                requirements=json.dumps(job.requirements),
                experience_level=(
                    job.experience_level.value if job.experience_level else None
                ),
                job_type=job.job_type.value if job.job_type else None,
                posted_date=job.posted_date,
                discovered_at=job.discovered_at,
                easy_apply=job.easy_apply,
                application_url=job.application_url,
            )
            session.add(row)
            session.commit()
            return row.id

    def is_duplicate(
        self, external_id: str, board: str, window_days: int = 30
    ) -> bool:
        """Check if a job was already seen within the dedup window."""
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        with self._session() as session:
            return (
                session.query(JobRow)
                .filter(
                    JobRow.external_id == external_id,
                    JobRow.board == board,
                    JobRow.discovered_at >= cutoff,
                )
                .first()
                is not None
            )

    def get_job(self, job_id: int) -> Optional[JobRow]:
        with self._session() as session:
            return session.query(JobRow).get(job_id)

    # --- Applications ---

    def save_application(self, app: ApplicationRecord, job_id: int) -> int:
        with self._session() as session:
            row = ApplicationRow(
                job_id=job_id,
                status=app.status.value,
                tailored_resume_path=app.tailored_resume_path,
                cover_letter_path=app.cover_letter_path,
                match_score=app.match_score,
                match_reasons=json.dumps(app.match_reasons),
                applied_at=app.applied_at,
                status_history=json.dumps(app.status_history),
                notes=app.notes,
                created_at=app.created_at,
                updated_at=app.updated_at,
            )
            session.add(row)
            session.commit()
            return row.id

    def update_application_status(
        self, app_id: int, status: ApplicationStatus, note: str = ""
    ) -> None:
        with self._session() as session:
            row = session.query(ApplicationRow).get(app_id)
            if not row:
                return
            history = json.loads(row.status_history)
            history.append(
                {
                    "from": row.status,
                    "to": status.value,
                    "at": datetime.utcnow().isoformat(),
                    "note": note,
                }
            )
            row.status = status.value
            row.status_history = json.dumps(history)
            row.updated_at = datetime.utcnow()
            if status == ApplicationStatus.SUBMITTED:
                row.applied_at = datetime.utcnow()
            session.commit()

    def get_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        board: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch applications with joined job data."""
        with self._session() as session:
            query = (
                session.query(ApplicationRow, JobRow)
                .join(JobRow, ApplicationRow.job_id == JobRow.id)
            )
            if status:
                query = query.filter(ApplicationRow.status == status.value)
            if board:
                query = query.filter(JobRow.board == board)
            query = query.order_by(ApplicationRow.updated_at.desc()).limit(limit)

            results = []
            for app_row, job_row in query.all():
                results.append(
                    {
                        "app_id": app_row.id,
                        "status": app_row.status,
                        "match_score": app_row.match_score,
                        "applied_at": app_row.applied_at,
                        "title": job_row.title,
                        "company": job_row.company,
                        "board": job_row.board,
                        "url": job_row.url,
                        "location": job_row.location,
                    }
                )
            return results

    def get_stats(self) -> dict:
        """Get application statistics."""
        with self._session() as session:
            total = session.query(ApplicationRow).count()
            by_status = {}
            for status in ApplicationStatus:
                count = (
                    session.query(ApplicationRow)
                    .filter(ApplicationRow.status == status.value)
                    .count()
                )
                if count > 0:
                    by_status[status.value] = count

            today = datetime.utcnow().replace(hour=0, minute=0, second=0)
            today_count = (
                session.query(ApplicationRow)
                .filter(
                    ApplicationRow.status == ApplicationStatus.SUBMITTED.value,
                    ApplicationRow.applied_at >= today,
                )
                .count()
            )

            return {
                "total": total,
                "by_status": by_status,
                "applied_today": today_count,
            }
