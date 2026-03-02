#!/usr/bin/env python3
"""
Job Hunter — Autonomous job search agent for senior engineering roles in the Middle East.

Commands:
  run        Run a single search cycle
  schedule   Start the recurring scheduler (runs every 6h by default)
  status     Show database statistics
  top        Show top-scored jobs
  test-email Send a test email to verify configuration
  score      Score a single job URL (for testing)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()


def load_config(config_path: str = "config.yaml") -> dict:
    """Load and return config.yaml."""
    try:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        click.echo(f"Warning: {config_path} not found, using defaults", err=True)
        return {}
    except yaml.YAMLError as e:
        click.echo(f"Error parsing {config_path}: {e}", err=True)
        sys.exit(1)


def check_env() -> list[str]:
    """Check required environment variables. Returns list of missing vars."""
    required = ["ANTHROPIC_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    return missing


@click.group()
@click.option("--config", default="config.yaml", help="Path to config.yaml")
@click.option("--dry-run", is_flag=True, help="Scrape and score without saving or emailing")
@click.pass_context
def cli(ctx, config, dry_run):
    """Job Hunter — Autonomous senior engineering job search agent."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)
    ctx.obj["dry_run"] = dry_run


@cli.command()
@click.pass_context
def run(ctx):
    """Run a single full search cycle (scrape → filter → score → notify)."""
    config = ctx.obj["config"]
    dry_run = ctx.obj["dry_run"]

    missing = check_env()
    if missing:
        click.echo(f"Error: Missing environment variables: {', '.join(missing)}", err=True)
        click.echo("Copy .env.example to .env and fill in your API keys.", err=True)
        sys.exit(1)

    from src.agent.orchestrator import JobHunterOrchestrator
    orchestrator = JobHunterOrchestrator(config=config, dry_run=dry_run)

    click.echo("Starting job search run...")
    if dry_run:
        click.echo("DRY RUN MODE — no data will be saved or emails sent")

    async def _run():
        stats = await orchestrator.run()
        click.echo("\n=== Run Complete ===")
        click.echo(f"Scraped:   {stats['total_scraped']}")
        click.echo(f"New:       {stats['total_new']}")
        click.echo(f"Scored:    {stats['total_scored']}")
        click.echo(f"Notified:  {stats['total_notified']}")
        click.echo(f"Duration:  {stats.get('duration_seconds', 0):.1f}s")
        if stats["errors"]:
            click.echo(f"Errors:    {len(stats['errors'])}")
            for err in stats["errors"][:3]:
                click.echo(f"  - {err}", err=True)

    asyncio.run(_run())


@cli.command()
@click.pass_context
def schedule(ctx):
    """Start the recurring job search scheduler (every N hours)."""
    config = ctx.obj["config"]
    dry_run = ctx.obj["dry_run"]

    missing = check_env()
    if missing:
        click.echo(f"Error: Missing environment variables: {', '.join(missing)}", err=True)
        sys.exit(1)

    hours = config.get("scheduler", {}).get("interval_hours", 6)
    click.echo(f"Starting scheduler — will run every {hours} hours")
    click.echo("Press Ctrl+C to stop")

    from src.agent.orchestrator import JobHunterOrchestrator
    from src.agent.scheduler import JobHunterScheduler

    orchestrator = JobHunterOrchestrator(config=config, dry_run=dry_run)
    scheduler = JobHunterScheduler(orchestrator=orchestrator, config=config)
    scheduler.start()


@cli.command()
@click.pass_context
def status(ctx):
    """Show database statistics and recent runs."""
    config = ctx.obj["config"]

    from src.storage.database import Database
    db = Database(url=config.get("database", {}).get("url"))
    db.init_db()
    stats = db.get_stats()

    click.echo("\n=== Job Hunter Status ===")
    click.echo(f"Total jobs scraped:    {stats['total_jobs']}")
    click.echo(f"Total jobs scored:     {stats['scored_jobs']}")
    click.echo(f"High quality (≥80):    {stats['high_quality_jobs']}")
    click.echo(f"Notifications sent:    {stats['notifications_sent']}")

    if stats["recent_runs"]:
        click.echo("\nRecent runs:")
        for run in stats["recent_runs"]:
            click.echo(
                f"  {run['run_at'][:16]}  {run['source']:15s}  "
                f"found={run['jobs_found']}  new={run['jobs_new']}"
            )


@cli.command()
@click.option("--limit", default=20, help="Number of jobs to show")
@click.option("--min-score", default=80.0, help="Minimum score threshold")
@click.pass_context
def top(ctx, limit, min_score):
    """Show top-scored job matches from the database."""
    config = ctx.obj["config"]

    from src.storage.database import Database
    db = Database(url=config.get("database", {}).get("url"))
    db.init_db()
    jobs = db.get_top_jobs(limit=limit, min_score=min_score)

    if not jobs:
        click.echo(f"No jobs with score ≥ {min_score:.0f} found. Run 'job-hunter run' first.")
        return

    click.echo(f"\n=== Top {len(jobs)} Jobs (score ≥ {min_score:.0f}) ===\n")
    for j in jobs:
        click.echo(
            f"[{j['relevance_score']:.0f}/100] {j['title']} @ {j['company']}\n"
            f"  Location: {j['location']}  |  Source: {j['source']}\n"
            f"  URL: {j['url']}\n"
            f"  {j.get('explanation', '')[:100]}\n"
        )


@cli.command("test-email")
@click.pass_context
def test_email(ctx):
    """Send a test email to verify Gmail SMTP configuration."""
    config = ctx.obj["config"]

    if not os.environ.get("GMAIL_APP_PASSWORD"):
        click.echo("Error: GMAIL_APP_PASSWORD not set in .env", err=True)
        click.echo("See .env.example for setup instructions.", err=True)
        sys.exit(1)

    from src.notifications.email_service import EmailService
    svc = EmailService(config=config)
    click.echo(f"Sending test email to {svc.to_email}...")
    success = svc.send_test_email()
    if success:
        click.echo("Test email sent successfully!")
    else:
        click.echo("Failed to send test email. Check logs for details.", err=True)
        sys.exit(1)


@cli.command()
@click.argument("url")
@click.pass_context
def score(ctx, url):
    """Score a specific job URL (fetches and scores it immediately)."""
    config = ctx.obj["config"]
    dry_run = ctx.obj["dry_run"]

    missing = check_env()
    if missing:
        click.echo(f"Error: Missing environment variables: {', '.join(missing)}", err=True)
        sys.exit(1)

    from src.matching.scorer import Scorer
    from src.parsers.resume_parser import load_candidate_profile

    candidate = load_candidate_profile(config=config)
    scorer = Scorer(config=config)

    # Create a minimal job dict
    job = {"url": url, "title": "Unknown", "company": "Unknown", "location": "Unknown", "description": ""}

    # Try to fetch with Playwright
    async def _score():
        click.echo(f"Fetching job from: {url}")
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title_el = await page.query_selector("h1")
                if title_el:
                    job["title"] = (await title_el.text_content() or "").strip()
                body = await page.inner_text("body")
                job["description"] = body[:5000]
                await browser.close()
        except Exception as e:
            click.echo(f"Warning: Could not fetch job page: {e}", err=True)

        click.echo(f"Scoring: '{job['title']}'")
        result = await scorer.score(job, candidate)

        click.echo(f"\n=== Score Results ===")
        click.echo(f"Final Score:      {result['final_score']:.1f}/100")
        click.echo(f"Skill Overlap:    {result.get('skill_overlap', 0):.0f}/100")
        click.echo(f"Seniority:        {result.get('seniority_alignment', 0):.0f}/100")
        click.echo(f"Industry:         {result.get('industry_alignment', 0):.0f}/100")
        click.echo(f"Compensation:     {result.get('compensation_confidence', 0):.0f}/100")
        click.echo(f"Location:         {result.get('location_relevance', 0):.0f}/100")
        click.echo(f"\nAnalysis: {result.get('explanation', '')}")
        click.echo(f"\nPositioning: {result.get('positioning_strategy', '')}")

    asyncio.run(_score())


if __name__ == "__main__":
    cli()
