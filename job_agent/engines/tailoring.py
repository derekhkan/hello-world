"""Resume and cover letter tailoring engine using LLM."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, BaseLoader

from job_agent.config import AgentConfig
from job_agent.models import ApplicationRecord, JobListing, UserProfile

logger = logging.getLogger(__name__)

MATCH_SCORING_PROMPT = """\
You are a job matching expert. Analyze the fit between a candidate and a job listing.

## Candidate Profile
Name: {name}
Skills: {skills}
Experience Summary: {experience_summary}
Education: {education_summary}

## Job Listing
Title: {job_title}
Company: {company}
Description:
{description}

Requirements:
{requirements}

## Instructions
Rate the match from 0.0 to 1.0 and provide specific reasons.
Respond in JSON format:
{{
  "score": <float 0.0-1.0>,
  "reasons": ["reason 1", "reason 2", ...],
  "missing_skills": ["skill 1", "skill 2", ...],
  "strong_matches": ["match 1", "match 2", ...]
}}
"""

RESUME_TAILORING_PROMPT = """\
You are an expert resume writer. Tailor the following resume content for a specific job.

## Current Resume Content
{resume_content}

## Target Job
Title: {job_title}
Company: {company}
Description:
{description}

Key Requirements:
{requirements}

## Instructions
- Reorder and emphasize relevant experience and skills
- Use keywords from the job description naturally
- Keep it truthful - do not fabricate experience
- Maintain professional formatting
- Keep it concise (1-2 pages worth of content)
- Output the tailored resume as clean, structured text

## Tailored Resume:
"""

COVER_LETTER_PROMPT = """\
You are an expert career coach. Adapt the candidate's base cover letter for a specific role.

## Candidate
Name: {name}
Current/Recent Title: {current_title}

## Base Cover Letter (candidate's own voice - preserve tone and style):
{base_cover_letter}

## Target Job
Title: {job_title}
Company: {company}
Description:
{description}

## Instructions
- Start from the base cover letter above and adapt it for this specific role and company
- Preserve the candidate's authentic voice and tone throughout
- Add 1-2 sentences connecting their experience specifically to this company and role
- Reference specific aspects of the company or job description naturally
- Keep it concise (250-400 words)
- Do NOT use cliches like "I am writing to express my interest"
- Do NOT fabricate experience - only reference what's in the base letter and resume

## Tailored Cover Letter:
"""


class TailoringEngine:
    """Engine for scoring job matches and tailoring application materials."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._llm_client = None

    @property
    def llm_client(self):
        """Lazy-load the OpenAI client."""
        if self._llm_client is None:
            from openai import OpenAI

            self._llm_client = OpenAI(api_key=self.config.llm.api_key)
        return self._llm_client

    def _call_llm(self, prompt: str, max_tokens: int | None = None) -> str:
        """Call the LLM with a prompt and return the response text."""
        try:
            response = self.llm_client.chat.completions.create(
                model=self.config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.llm.temperature,
                max_tokens=max_tokens or self.config.llm.max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _format_experience(self, profile: UserProfile) -> str:
        """Format experience for prompts."""
        lines = []
        for exp in profile.experience[:5]:  # Top 5 recent
            current = " (current)" if exp.current else ""
            lines.append(f"- {exp.title} at {exp.company}{current}")
            if exp.highlights:
                for h in exp.highlights[:3]:
                    lines.append(f"  * {h}")
        return "\n".join(lines) if lines else "Not provided"

    def _format_education(self, profile: UserProfile) -> str:
        """Format education for prompts."""
        lines = []
        for edu in profile.education:
            lines.append(f"- {edu.degree} in {edu.field_of_study}, {edu.institution}")
        return "\n".join(lines) if lines else "Not provided"

    def score_match(self, job: JobListing, profile: UserProfile) -> dict:
        """Score how well a job matches the user's profile.

        Returns dict with: score (float), reasons (list), missing_skills (list),
        strong_matches (list).
        """
        prompt = MATCH_SCORING_PROMPT.format(
            name=f"{profile.first_name} {profile.last_name}",
            skills=", ".join(profile.skills),
            experience_summary=self._format_experience(profile),
            education_summary=self._format_education(profile),
            job_title=job.title,
            company=job.company,
            description=job.description[:3000],
            requirements="\n".join(f"- {r}" for r in job.requirements[:20]),
        )

        try:
            result_text = self._call_llm(prompt, max_tokens=500)
            # Extract JSON from response
            json_match = result_text
            if "```" in result_text:
                json_match = result_text.split("```")[1]
                if json_match.startswith("json"):
                    json_match = json_match[4:]
            return json.loads(json_match)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse match score: {e}")
            return {
                "score": 0.5,
                "reasons": ["Could not auto-score this match"],
                "missing_skills": [],
                "strong_matches": [],
            }

    def tailor_resume(
        self, job: JobListing, profile: UserProfile, resume_content: str
    ) -> str:
        """Generate a tailored version of the resume for a specific job."""
        prompt = RESUME_TAILORING_PROMPT.format(
            resume_content=resume_content[:5000],
            job_title=job.title,
            company=job.company,
            description=job.description[:3000],
            requirements="\n".join(f"- {r}" for r in job.requirements[:20]),
        )
        return self._call_llm(prompt, max_tokens=3000)

    def generate_cover_letter(
        self, job: JobListing, profile: UserProfile
    ) -> str:
        """Generate a tailored cover letter based on the candidate's base letter."""
        current_title = ""
        if profile.experience:
            current_exp = next(
                (e for e in profile.experience if e.current), profile.experience[0]
            )
            current_title = current_exp.title

        # Load base cover letter
        base_cover_letter = ""
        cover_letter_base_path = self.config.data_dir / "cover_letter.txt"
        if cover_letter_base_path.exists():
            base_cover_letter = cover_letter_base_path.read_text()
        elif Path("/opt/job-agent/data/cover_letter.txt").exists():
            base_cover_letter = Path("/opt/job-agent/data/cover_letter.txt").read_text()

        if not base_cover_letter:
            # Fallback: construct from profile
            base_cover_letter = profile.summary

        prompt = COVER_LETTER_PROMPT.format(
            name=f"{profile.first_name} {profile.last_name}",
            current_title=current_title,
            base_cover_letter=base_cover_letter,
            job_title=job.title,
            company=job.company,
            description=job.description[:3000],
        )
        return self._call_llm(prompt, max_tokens=1500)

    def prepare_application(
        self, job: JobListing, profile: UserProfile
    ) -> ApplicationRecord:
        """Full pipeline: score, tailor resume, generate cover letter."""
        logger.info(f"Preparing application for {job.title} at {job.company}")

        # Step 1: Score the match
        match_result = self.score_match(job, profile)
        logger.info(
            f"Match score: {match_result['score']:.2f} - "
            f"{', '.join(match_result.get('reasons', [])[:3])}"
        )

        # Step 2: Tailor resume if we have one
        tailored_resume_path = None
        if profile.resume_path:
            try:
                resume_content = Path(profile.resume_path).read_text()
                tailored = self.tailor_resume(job, profile, resume_content)

                output_dir = self.config.data_dir / "resumes"
                output_dir.mkdir(parents=True, exist_ok=True)
                filename = (
                    f"resume_{job.company}_{job.external_id}.txt"
                    .replace(" ", "_")
                    .lower()
                )
                output_path = output_dir / filename
                output_path.write_text(tailored)
                tailored_resume_path = str(output_path)
                logger.info(f"Tailored resume saved: {output_path}")
            except Exception as e:
                logger.warning(f"Resume tailoring failed: {e}")

        # Step 3: Generate cover letter
        cover_letter_path = None
        try:
            cover_letter = self.generate_cover_letter(job, profile)

            output_dir = self.config.data_dir / "cover_letters"
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = (
                f"cover_{job.company}_{job.external_id}.txt"
                .replace(" ", "_")
                .lower()
            )
            output_path = output_dir / filename
            output_path.write_text(cover_letter)
            cover_letter_path = str(output_path)
            logger.info(f"Cover letter saved: {output_path}")
        except Exception as e:
            logger.warning(f"Cover letter generation failed: {e}")

        return ApplicationRecord(
            job=job,
            match_score=match_result.get("score", 0.5),
            match_reasons=match_result.get("reasons", []),
            tailored_resume_path=tailored_resume_path,
            cover_letter_path=cover_letter_path,
        )
