"""Data models for the job application agent."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JobBoard(str, enum.Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    ZIPRECRUITER = "ziprecruiter"
    HEIDRICK = "heidrick"
    KORNFERRY = "kornferry"
    SPENCERSTUART = "spencerstuart"
    RUSSELLREYNOLDS = "russellreynolds"
    CAREERPAGES = "careerpages"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"


class ApplicationStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    TAILORING = "tailoring"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    FAILED = "failed"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"
    WITHDRAWN = "withdrawn"


class ExperienceLevel(str, enum.Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    DIRECTOR = "director"
    VP = "vp"
    EXECUTIVE = "executive"


class JobType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"


class WorkMode(str, enum.Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


# --- User Profile ---


class Education(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[float] = None
    highlights: list[str] = Field(default_factory=list)


class WorkExperience(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: Optional[str] = None
    current: bool = False
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    github_url: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    resume_path: str = ""
    willing_to_relocate: bool = False
    work_authorization: str = "authorized"
    desired_salary_min: Optional[int] = None
    desired_salary_max: Optional[int] = None


# --- Search Preferences ---


class SearchPreferences(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    work_modes: list[WorkMode] = Field(default_factory=list)
    experience_levels: list[ExperienceLevel] = Field(default_factory=list)
    job_types: list[JobType] = Field(default_factory=lambda: [JobType.FULL_TIME])
    salary_min: Optional[int] = None
    companies_target: list[str] = Field(default_factory=list)
    companies_per_run: int = 50  # rotate through target companies in daily batches
    companies_include: list[str] = Field(default_factory=list)
    companies_exclude: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    posted_within_days: int = 7
    boards: list[JobBoard] = Field(
        default_factory=lambda: [
            JobBoard.LINKEDIN,
            JobBoard.INDEED,
            JobBoard.GLASSDOOR,
            JobBoard.ZIPRECRUITER,
        ]
    )
    max_applications_per_day: int = 25
    auto_apply: bool = False


# --- Job Listing ---


class JobListing(BaseModel):
    id: Optional[str] = None
    external_id: str
    board: JobBoard
    url: str
    title: str
    company: str
    location: str = ""
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_text: str = ""
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    experience_level: Optional[ExperienceLevel] = None
    job_type: Optional[JobType] = None
    posted_date: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    easy_apply: bool = False
    application_url: Optional[str] = None
    company_logo_url: Optional[str] = None


# --- Application Record ---


class ApplicationRecord(BaseModel):
    id: Optional[str] = None
    job: JobListing
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    match_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
    applied_at: Optional[datetime] = None
    status_history: list[dict] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def update_status(self, new_status: ApplicationStatus, note: str = "") -> None:
        self.status_history.append(
            {
                "from": self.status.value,
                "to": new_status.value,
                "at": datetime.utcnow().isoformat(),
                "note": note,
            }
        )
        self.status = new_status
        self.updated_at = datetime.utcnow()
