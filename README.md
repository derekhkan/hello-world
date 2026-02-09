# Job Application Agent

Automated job application agent that searches across top job boards, tailors your resume and cover letter using AI, and submits applications on your behalf.

## Supported Job Boards

- **LinkedIn** - Job search + Easy Apply automation
- **Indeed** - Job search + Indeed Apply automation
- **Glassdoor** - Job search + Easy Apply automation
- **ZipRecruiter** - Job search + One-Click Apply automation

## Features

- **Multi-board search** - Searches all major job boards in one run
- **AI-powered matching** - Scores jobs against your profile using GPT-4o
- **Resume tailoring** - Generates job-specific resume versions
- **Cover letter generation** - Creates personalized cover letters for each application
- **Browser automation** - Handles form filling and submission via Selenium
- **Deduplication** - Tracks seen jobs to avoid reapplying
- **Application tracking** - SQLite database with full status history
- **Daily limits** - Configurable max applications per day
- **Email notifications** - Get notified on submissions, failures, and daily summaries
- **Export** - Export application history to CSV or JSON

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Configure

Run the interactive setup:

```bash
job-agent init
```

Or copy the sample config:

```bash
mkdir -p ~/.job-agent
cp config/sample_config.yaml ~/.job-agent/config.yaml
# Edit with your details
```

### 3. Set Environment Variables

```bash
cp .env.example .env
# Fill in your API keys and credentials
```

### 4. Run

```bash
# Search and score jobs (no applications submitted)
job-agent run --dry-run

# Search and auto-apply to matched jobs
job-agent run --auto-apply

# Only search, view results
job-agent search

# View application dashboard
job-agent status

# Export to CSV
job-agent export --format csv
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `job-agent init` | Interactive profile and preferences setup |
| `job-agent run` | Run the full search-score-apply pipeline |
| `job-agent search` | Search for jobs without applying |
| `job-agent status` | View application tracking dashboard |
| `job-agent export` | Export application data (CSV/JSON) |
| `job-agent summary` | Send daily summary email |

### Options

```
job-agent run --min-score 0.5     # Only apply to 50%+ matches
job-agent run --dry-run           # Preview without submitting
job-agent run --auto-apply        # Enable auto-submission
job-agent status --status submitted
job-agent status --board linkedin
job-agent export --format json -o ~/apps.json
```

## Architecture

```
job_agent/
├── cli.py              # Click-based CLI interface
├── orchestrator.py     # Pipeline coordination
├── config.py           # Configuration management
├── models.py           # Pydantic data models
├── scrapers/
│   ├── base.py         # Base scraper with rate limiting
│   ├── linkedin.py     # LinkedIn scraper
│   ├── indeed.py       # Indeed scraper
│   ├── glassdoor.py    # Glassdoor scraper
│   └── ziprecruiter.py # ZipRecruiter scraper
├── engines/
│   ├── tailoring.py    # AI resume/cover letter engine
│   └── applicator.py   # Selenium submission engine
└── utils/
    ├── database.py     # SQLite tracking database
    └── notifications.py # Email notification service
```

## Pipeline Flow

```
1. DISCOVER  - Search all configured job boards
2. DEDUPLICATE - Skip jobs already seen within window
3. SCORE     - AI-powered match scoring against your profile
4. FILTER    - Remove jobs below minimum score threshold
5. TAILOR    - Generate job-specific resume + cover letter
6. APPLY     - Submit via browser automation (with rate limits)
7. TRACK     - Record status in database
8. NOTIFY    - Send email notifications
```

## Configuration

Configuration is stored in `~/.job-agent/config.yaml`. See `config/sample_config.yaml` for a complete example with all options.

Key configuration sections:
- **profile** - Your personal info, skills, experience, education
- **search** - Keywords, locations, job types, salary requirements
- **llm** - OpenAI API settings for AI-powered features
- **browser** - Headless mode, timeouts, proxy settings
- **notifications** - Email alert configuration

## Requirements

- Python 3.10+
- Chrome/Chromium (for Selenium-based applications)
- OpenAI API key (for resume tailoring and job matching)
