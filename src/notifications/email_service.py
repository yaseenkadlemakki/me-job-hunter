"""Gmail SMTP email notification service."""

from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger("email_service")


def _comp_display(salary_raw: Optional[str], salary_aed: Optional[float]) -> str:
    """Format compensation for display."""
    parts = []
    if salary_raw:
        parts.append(salary_raw)
    if salary_aed:
        parts.append(f"~{salary_aed:,.0f} AED/yr")
    return " | ".join(parts) if parts else "Not disclosed"


class EmailService:
    """Send job alert emails via Gmail SMTP."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        notif_cfg = config.get("notifications", {}) if config else {}
        self.from_email = os.environ.get("GMAIL_FROM", "yaseenkadlemakki@gmail.com")
        self.to_email = os.environ.get("GMAIL_TO", "yaseenkadlemakki@gmail.com")
        self.app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.enabled = notif_cfg.get("send_email", True)

    def send_job_alert(self, job_data: dict, score_data: dict) -> bool:
        """Send a job alert email. Returns True on success."""
        if not self.enabled:
            logger.debug("Email notifications disabled")
            return False

        if not self.app_password:
            logger.warning("GMAIL_APP_PASSWORD not set — skipping email")
            return False

        subject = self._build_subject(job_data, score_data)
        html_body = self._build_html_body(job_data, score_data)
        text_body = self._build_text_body(job_data, score_data)

        try:
            return self._send(subject, html_body, text_body)
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    def send_test_email(self) -> bool:
        """Send a test email to verify configuration."""
        subject = "Job Hunter — Test Email"
        html = """
        <html><body>
        <h2>Job Hunter is configured correctly!</h2>
        <p>This test email confirms that Gmail SMTP is working.</p>
        <p><em>Sent at: {now}</em></p>
        </body></html>
        """.format(now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        text = f"Job Hunter test email — sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        return self._send(subject, html, text)

    def send_digest(self, jobs: list[dict]) -> bool:
        """Send a digest of top-scored jobs."""
        if not jobs:
            logger.info("No jobs to include in digest")
            return False

        subject = f"Job Hunter Daily Digest — {len(jobs)} Top Matches ({datetime.utcnow().strftime('%Y-%m-%d')})"
        html = self._build_digest_html(jobs)
        text = self._build_digest_text(jobs)
        return self._send(subject, html, text)

    def _build_subject(self, job_data: dict, score_data: dict) -> str:
        score = int(score_data.get("final_score", 0))
        title = job_data.get("title", "Unknown Role")
        company = job_data.get("company", "Unknown Company")
        location = job_data.get("location", "")
        return f"[Score: {score}/100] {title} at {company} — {location}"

    def _build_html_body(self, job_data: dict, score_data: dict) -> str:
        score = score_data.get("final_score", 0)
        score_color = "#27ae60" if score >= 90 else "#f39c12" if score >= 80 else "#e74c3c"

        skill_score = score_data.get("skill_overlap", 0)
        seniority_score = score_data.get("seniority_alignment", 0)
        industry_score = score_data.get("industry_alignment", 0)
        comp_score = score_data.get("compensation_confidence", 0)
        location_score = score_data.get("location_relevance", 0)

        comp_display = _comp_display(
            job_data.get("salary_raw"),
            job_data.get("salary_estimated_aed"),
        )

        description = (job_data.get("description") or "")[:1500]
        if len(job_data.get("description", "")) > 1500:
            description += "..."

        explanation = score_data.get("explanation", "")
        positioning = score_data.get("positioning_strategy", "")

        return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
  .container {{ max-width: 680px; margin: 20px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px; }}
  .header h1 {{ color: #fff; margin: 0; font-size: 22px; }}
  .score-badge {{ display: inline-block; background: {score_color}; color: white; padding: 8px 20px; border-radius: 20px; font-size: 28px; font-weight: 700; margin-top: 12px; }}
  .content {{ padding: 24px; }}
  .job-title {{ font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 0 0 8px; }}
  .company {{ font-size: 18px; color: #555; margin: 0 0 4px; }}
  .location {{ font-size: 16px; color: #777; margin: 0 0 16px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }}
  .meta-item {{ background: #f8f9fa; padding: 12px; border-radius: 6px; }}
  .meta-label {{ font-size: 11px; text-transform: uppercase; color: #999; font-weight: 600; }}
  .meta-value {{ font-size: 15px; color: #333; font-weight: 500; margin-top: 4px; }}
  .scores-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin: 20px 0; }}
  .score-item {{ text-align: center; padding: 12px; background: #f8f9fa; border-radius: 6px; }}
  .score-item .num {{ font-size: 24px; font-weight: 700; color: {score_color}; }}
  .score-item .lbl {{ font-size: 11px; color: #999; text-transform: uppercase; }}
  .section-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase; color: #999; letter-spacing: 1px; margin: 20px 0 8px; }}
  .explanation {{ background: #eaf6ff; border-left: 4px solid #3498db; padding: 12px 16px; border-radius: 0 6px 6px 0; color: #2c3e50; line-height: 1.6; }}
  .positioning {{ background: #eafaf1; border-left: 4px solid #27ae60; padding: 12px 16px; border-radius: 0 6px 6px 0; color: #2c3e50; line-height: 1.6; }}
  .description {{ background: #f8f9fa; padding: 16px; border-radius: 6px; font-size: 14px; line-height: 1.7; color: #444; white-space: pre-wrap; }}
  .cta {{ text-align: center; margin: 24px 0 16px; }}
  .cta a {{ display: inline-block; background: #0077b5; color: white; padding: 14px 32px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 16px; }}
  .footer {{ text-align: center; padding: 16px; color: #aaa; font-size: 12px; border-top: 1px solid #eee; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>New Job Match Found</h1>
    <div class="score-badge">{score:.0f}/100</div>
  </div>
  <div class="content">
    <h2 class="job-title">{job_data.get('title', 'N/A')}</h2>
    <p class="company">{job_data.get('company', 'N/A')}</p>
    <p class="location">📍 {job_data.get('location', 'N/A')}</p>

    <div class="meta-grid">
      <div class="meta-item">
        <div class="meta-label">Source</div>
        <div class="meta-value">{job_data.get('source', 'N/A').title()}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Compensation</div>
        <div class="meta-value">{comp_display}</div>
      </div>
    </div>

    <div class="section-title">Score Breakdown</div>
    <div class="scores-grid">
      <div class="score-item">
        <div class="num">{skill_score:.0f}</div>
        <div class="lbl">Skills</div>
      </div>
      <div class="score-item">
        <div class="num">{seniority_score:.0f}</div>
        <div class="lbl">Seniority</div>
      </div>
      <div class="score-item">
        <div class="num">{industry_score:.0f}</div>
        <div class="lbl">Industry</div>
      </div>
      <div class="score-item">
        <div class="num">{comp_score:.0f}</div>
        <div class="lbl">Comp</div>
      </div>
      <div class="score-item">
        <div class="num">{location_score:.0f}</div>
        <div class="lbl">Location</div>
      </div>
    </div>

    <div class="section-title">AI Analysis</div>
    <div class="explanation">{explanation}</div>

    <div class="section-title">Positioning Strategy</div>
    <div class="positioning">{positioning}</div>

    <div class="section-title">Job Description</div>
    <div class="description">{description}</div>

    <div class="cta">
      <a href="{job_data.get('url', '#')}">View Full Job Posting →</a>
    </div>
  </div>
  <div class="footer">
    Sent by Job Hunter Agent • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
  </div>
</div>
</body>
</html>
"""

    def _build_text_body(self, job_data: dict, score_data: dict) -> str:
        score = score_data.get("final_score", 0)
        comp_display = _comp_display(job_data.get("salary_raw"), job_data.get("salary_estimated_aed"))
        return (
            f"NEW JOB MATCH — Score: {score:.0f}/100\n"
            f"{'='*60}\n\n"
            f"Title: {job_data.get('title', 'N/A')}\n"
            f"Company: {job_data.get('company', 'N/A')}\n"
            f"Location: {job_data.get('location', 'N/A')}\n"
            f"Compensation: {comp_display}\n"
            f"Source: {job_data.get('source', 'N/A')}\n"
            f"URL: {job_data.get('url', 'N/A')}\n\n"
            f"Score Breakdown:\n"
            f"  Skills: {score_data.get('skill_overlap', 0):.0f}/100\n"
            f"  Seniority: {score_data.get('seniority_alignment', 0):.0f}/100\n"
            f"  Industry: {score_data.get('industry_alignment', 0):.0f}/100\n"
            f"  Comp: {score_data.get('compensation_confidence', 0):.0f}/100\n"
            f"  Location: {score_data.get('location_relevance', 0):.0f}/100\n\n"
            f"Analysis: {score_data.get('explanation', '')}\n\n"
            f"Positioning: {score_data.get('positioning_strategy', '')}\n\n"
            f"---\nSent by Job Hunter Agent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

    def _build_digest_html(self, jobs: list[dict]) -> str:
        rows = ""
        for j in jobs:
            score = j.get("relevance_score", 0)
            score_color = "#27ae60" if score >= 90 else "#f39c12" if score >= 80 else "#e74c3c"
            rows += f"""
            <tr>
              <td style="padding:12px;border-bottom:1px solid #eee;">
                <strong><a href="{j.get('url','#')}" style="color:#1a1a2e;text-decoration:none;">{j.get('title','')}</a></strong><br>
                <span style="color:#555;">{j.get('company','')}</span> · <span style="color:#777;">{j.get('location','')}</span>
              </td>
              <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;">
                <span style="background:{score_color};color:white;padding:4px 10px;border-radius:12px;font-weight:700;">{score:.0f}</span>
              </td>
            </tr>"""

        return f"""
<!DOCTYPE html><html><body style="font-family:sans-serif;background:#f5f5f5;padding:20px;">
<div style="max-width:680px;margin:auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1);">
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:20px;">
    <h1 style="color:white;margin:0;">Job Hunter Daily Digest</h1>
    <p style="color:#aaa;margin:4px 0 0;">{len(jobs)} top matches · {datetime.utcnow().strftime('%B %d, %Y')}</p>
  </div>
  <div style="padding:24px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>
        <th style="text-align:left;padding:8px;border-bottom:2px solid #eee;color:#999;font-size:12px;text-transform:uppercase;">Job</th>
        <th style="text-align:center;padding:8px;border-bottom:2px solid #eee;color:#999;font-size:12px;text-transform:uppercase;">Score</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>
</body></html>"""

    def _build_digest_text(self, jobs: list[dict]) -> str:
        lines = [f"Job Hunter Digest — {len(jobs)} matches — {datetime.utcnow().strftime('%Y-%m-%d')}", "="*60]
        for j in jobs:
            lines.append(
                f"\n[{j.get('relevance_score',0):.0f}/100] {j.get('title','')} @ {j.get('company','')}\n"
                f"  Location: {j.get('location','')}\n"
                f"  URL: {j.get('url','')}"
            )
        return "\n".join(lines)

    def _send(self, subject: str, html_body: str, text_body: str) -> bool:
        """Send email via Gmail SMTP."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = self.to_email

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.from_email, self.app_password)
                server.sendmail(self.from_email, self.to_email, msg.as_string())

            logger.info(f"Email sent: '{subject}' → {self.to_email}")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error(
                "Gmail authentication failed. Check GMAIL_APP_PASSWORD. "
                "See: https://myaccount.google.com/apppasswords"
            )
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False
