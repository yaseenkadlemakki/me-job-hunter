# Job Hunter — Autonomous Senior Engineering Job Search Agent

An autonomous, production-grade job search agent that continuously monitors LinkedIn, Indeed, Bayt, GulfTalent, and Naukrigulf for senior engineering leadership roles (Director/VP/Head/CTO) in the Middle East (UAE, Saudi Arabia), scores them using Claude AI, and sends real-time email alerts for top matches.

## Features

- **5 job board scrapers**: LinkedIn, Indeed (UAE/SA), Bayt, GulfTalent, Naukrigulf
- **AI-powered scoring**: Claude claude-3-5-haiku-20241022 scores each job across 5 dimensions (skills, seniority, industry, comp, location) with weighted final score (0-100)
- **Smart pre-filtering**: Location-aware, seniority-aware filters eliminate noise before calling the LLM
- **Semantic deduplication**: ChromaDB vector store prevents duplicate processing
- **HTML email alerts**: Beautiful job notifications with score breakdown + positioning strategy
- **Persistent storage**: SQLite (upgradeable to PostgreSQL) for all jobs, scores, and notifications
- **Scheduled runs**: APScheduler runs every 6 hours automatically
- **Docker-ready**: One-command deploy with docker-compose

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yaseen-job-hunter/job-hunter
cd job-hunter
cp .env.example .env
```

### 2. Configure API Keys

Edit `.env`:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GMAIL_APP_PASSWORD=your_16_char_app_password
GMAIL_FROM=yaseenkadlemakki@gmail.com
GMAIL_TO=yaseenkadlemakki@gmail.com
```

#### Getting an Anthropic API Key
1. Go to https://console.anthropic.com/
2. Create an account and generate an API key
3. Paste it as `ANTHROPIC_API_KEY` in `.env`

#### Getting a Gmail App Password
1. Enable 2-Factor Authentication on your Gmail account
2. Go to https://myaccount.google.com/apppasswords
3. Click "Select app" → "Other (custom name)" → "Job Hunter"
4. Click "Generate" — copy the 16-character password (no spaces)
5. Paste it as `GMAIL_APP_PASSWORD` in `.env`

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 4. Run

```bash
# Single search cycle
python main.py run

# Start recurring scheduler (every 6 hours)
python main.py schedule

# Check status
python main.py status

# Show top matches
python main.py top --limit 20 --min-score 80

# Send test email
python main.py test-email

# Score a specific job URL
python main.py score "https://www.linkedin.com/jobs/view/12345"
```

## Configuration

Edit `config.yaml` to customize:

```yaml
filters:
  min_relevance_score: 80        # Minimum score to trigger email alert
  target_locations:              # Job locations to search
    - "Dubai"
    - "Abu Dhabi"
    - "Riyadh"
  target_titles:                 # Seniority keywords to match
    - "Director"
    - "VP Engineering"
    - "Head of Engineering"
  excluded_locations:            # Never show jobs from these locations
    - "Israel"

scoring_weights:
  skill_overlap: 0.30            # 30% weight on skill match
  seniority_alignment: 0.25     # 25% weight on seniority fit
  industry_alignment: 0.15      # 15% weight on industry relevance
  compensation_confidence: 0.15  # 15% weight on compensation estimate
  location_relevance: 0.15      # 15% weight on location quality

scheduler:
  interval_hours: 6             # Run every 6 hours
  max_jobs_per_run: 50          # Max jobs to process per run
```

## Docker Deployment

### Local Docker

```bash
cp .env.example .env
# Edit .env with your API keys

docker-compose up -d
docker-compose logs -f job-hunter
```

### AWS Deployment (EC2)

```bash
# 1. Launch EC2 instance (t3.medium recommended)
# 2. Install Docker
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl start docker && sudo usermod -aG docker ubuntu

# 3. Clone repo and configure
git clone https://github.com/yaseen-job-hunter/job-hunter
cd job-hunter
cp .env.example .env
nano .env  # Add your API keys

# 4. Start
docker compose up -d

# 5. View logs
docker compose logs -f
```

### DigitalOcean Droplet

```bash
# 1. Create a $6/mo Basic Droplet (Ubuntu 22.04)
# 2. SSH in
# 3. Install Docker: curl -fsSL https://get.docker.com | sh
# 4. Clone + configure + start (same as above)
```

## Database

The app uses SQLite by default (`data/job_hunter.db`). For production, switch to PostgreSQL:

```bash
# In .env:
DATABASE_URL=postgresql://user:password@host:5432/job_hunter
```

Tables:
- `jobs` — all scraped job postings
- `scored_jobs` — AI scores for each job
- `notifications` — email notification log
- `scraping_logs` — per-run statistics

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --tb=short  # shorter traceback
```

## Project Structure

```
job-hunter/
├── main.py                    # CLI entry point
├── config.yaml                # Configurable filters and weights
├── .env.example               # Environment variables template
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── agent/
│   │   ├── orchestrator.py    # Main agent run loop
│   │   └── scheduler.py       # APScheduler setup
│   ├── connectors/
│   │   ├── base.py            # Abstract base connector
│   │   ├── linkedin.py        # LinkedIn Jobs scraper
│   │   ├── indeed.py          # Indeed UAE/SA scraper
│   │   ├── bayt.py            # Bayt.com scraper
│   │   ├── gulftarget.py      # GulfTalent scraper
│   │   └── naukrigulf.py      # Naukrigulf scraper
│   ├── matching/
│   │   ├── embeddings.py      # Sentence-transformer embeddings
│   │   ├── scorer.py          # Claude AI scoring engine
│   │   └── filters.py         # Pre-LLM location/seniority filters
│   ├── parsers/
│   │   ├── resume_parser.py   # Candidate profile loader
│   │   └── job_parser.py      # HTML cleaning, salary extraction
│   ├── storage/
│   │   ├── database.py        # SQLAlchemy models + CRUD
│   │   └── vector_store.py    # ChromaDB vector store
│   ├── notifications/
│   │   └── email_service.py   # Gmail SMTP with HTML templates
│   └── utils/
│       ├── rate_limiter.py    # Per-site async rate limiting
│       └── logger.py          # Structured logging
└── tests/
    ├── test_scorer.py
    ├── test_filters.py
    └── test_connectors.py
```

## How It Works

1. **Scrape**: Each connector launches a headless Chromium browser (Playwright), searches for director/VP/head-level engineering roles across multiple pages, and returns structured job data.

2. **Filter**: Fast rule-based pre-filter checks title seniority and location before any LLM calls.

3. **Score**: Claude claude-3-5-haiku-20241022 evaluates each job on 5 dimensions, returning a weighted score (0-100).

4. **Notify**: Jobs scoring >= 80/100 trigger an HTML email with full analysis and positioning advice.

5. **Store**: All jobs, scores, and notifications are persisted to SQLite for deduplication and review.

6. **Repeat**: APScheduler re-runs the full cycle every 6 hours.

## Troubleshooting

**Playwright browser not installed:**
```bash
playwright install chromium
playwright install-deps chromium  # Linux only
```

**Gmail authentication fails:**
- Ensure 2FA is enabled on the Gmail account
- Use an App Password, not your regular Gmail password
- Check GMAIL_FROM matches the Gmail account that generated the App Password

**Anthropic API rate limits:**
- The scorer uses claude-3-5-haiku-20241022 for speed and cost efficiency
- Retry logic is built-in (3 attempts with exponential backoff)

**SQLite locked:**
- Ensure only one instance is running at a time
- For concurrent access, switch to PostgreSQL

## License

MIT
