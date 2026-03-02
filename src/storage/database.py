"""SQLAlchemy models and database operations."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text,
    DateTime, ForeignKey, Boolean, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError

from src.utils.logger import setup_logger

logger = setup_logger("database")


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    title = Column(String(300), nullable=False)
    company = Column(String(300), nullable=False)
    location = Column(String(300))
    url = Column(String(2000), nullable=False, unique=True)
    description = Column(Text)
    salary_raw = Column(String(500))
    salary_estimated_aed = Column(Float)
    posted_date = Column(DateTime)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="new")

    scores = relationship("ScoredJob", back_populates="job", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_source", "source"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_scraped_at", "scraped_at"),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title='{self.title}' company='{self.company}'>"


class ScoredJob(Base):
    __tablename__ = "scored_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    relevance_score = Column(Float, nullable=False)
    skill_score = Column(Float)
    seniority_score = Column(Float)
    industry_score = Column(Float)
    comp_score = Column(Float)
    location_score = Column(Float)
    explanation = Column(Text)
    positioning_strategy = Column(Text)
    scored_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="scores")

    __table_args__ = (
        Index("ix_scored_jobs_relevance", "relevance_score"),
        Index("ix_scored_jobs_job_id", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<ScoredJob job_id={self.job_id} score={self.relevance_score:.1f}>"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    email_to = Column(String(300))
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    job = relationship("Job", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_job_id", "job_id"),
        Index("ix_notifications_sent_at", "sent_at"),
    )


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow)
    jobs_found = Column(Integer, default=0)
    jobs_new = Column(Integer, default=0)
    jobs_scored = Column(Integer, default=0)
    jobs_notified = Column(Integer, default=0)
    errors = Column(Text)
    duration_seconds = Column(Float)

    __table_args__ = (
        Index("ix_scraping_logs_source", "source"),
        Index("ix_scraping_logs_run_at", "run_at"),
    )


class Database:
    """Database access layer."""

    def __init__(self, url: str = None):
        db_url = url or os.getenv("DATABASE_URL", "sqlite:///./data/job_hunter.db")

        # Ensure data directory exists for SQLite
        if db_url.startswith("sqlite"):
            db_path = db_url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        self.engine = create_engine(db_url, echo=False, connect_args=connect_args)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized")

    @contextmanager
    def session(self):
        """Provide a transactional scope around a series of operations."""
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def job_exists(self, url: str) -> bool:
        with self.session() as s:
            return s.query(Job).filter(Job.url == url).first() is not None

    def save_job(self, job_data: dict) -> Optional[Job]:
        """Save a job to the database. Returns None if duplicate."""
        try:
            with self.session() as s:
                job = Job(
                    source=job_data.get("source", "unknown"),
                    title=job_data.get("title", ""),
                    company=job_data.get("company", ""),
                    location=job_data.get("location", ""),
                    url=job_data.get("url", ""),
                    description=job_data.get("description", ""),
                    salary_raw=job_data.get("salary_raw"),
                    salary_estimated_aed=job_data.get("salary_estimated_aed"),
                    posted_date=job_data.get("posted_date"),
                    status="new",
                )
                s.add(job)
                s.flush()
                s.expunge(job)
                return job
        except IntegrityError:
            logger.debug(f"Duplicate job skipped: {job_data.get('url')}")
            return None

    def save_score(self, job_id: int, score_data: dict) -> ScoredJob:
        with self.session() as s:
            scored = ScoredJob(
                job_id=job_id,
                relevance_score=score_data.get("final_score", 0),
                skill_score=score_data.get("skill_overlap", 0),
                seniority_score=score_data.get("seniority_alignment", 0),
                industry_score=score_data.get("industry_alignment", 0),
                comp_score=score_data.get("compensation_confidence", 0),
                location_score=score_data.get("location_relevance", 0),
                explanation=score_data.get("explanation", ""),
                positioning_strategy=score_data.get("positioning_strategy", ""),
            )
            s.add(scored)
            s.flush()
            s.expunge(scored)
            return scored

    def save_notification(self, job_id: int, email_to: str, success: bool = True, error: str = None) -> None:
        with self.session() as s:
            notif = Notification(
                job_id=job_id,
                email_to=email_to,
                success=success,
                error_message=error,
            )
            s.add(notif)

    def save_scraping_log(self, log_data: dict) -> None:
        with self.session() as s:
            log = ScrapingLog(
                source=log_data.get("source", "unknown"),
                jobs_found=log_data.get("jobs_found", 0),
                jobs_new=log_data.get("jobs_new", 0),
                jobs_scored=log_data.get("jobs_scored", 0),
                jobs_notified=log_data.get("jobs_notified", 0),
                errors=log_data.get("errors"),
                duration_seconds=log_data.get("duration_seconds"),
            )
            s.add(log)

    def get_job_by_url(self, url: str) -> Optional[Job]:
        with self.session() as s:
            job = s.query(Job).filter(Job.url == url).first()
            if job:
                s.expunge(job)
            return job

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        with self.session() as s:
            job = s.query(Job).filter(Job.id == job_id).first()
            if job:
                s.expunge(job)
            return job

    def get_top_jobs(self, limit: int = 20, min_score: float = 80.0) -> list[dict]:
        """Return top-scored jobs with their scores."""
        with self.session() as s:
            results = (
                s.query(Job, ScoredJob)
                .join(ScoredJob, Job.id == ScoredJob.job_id)
                .filter(ScoredJob.relevance_score >= min_score)
                .order_by(ScoredJob.relevance_score.desc())
                .limit(limit)
                .all()
            )
            output = []
            for job, score in results:
                output.append({
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": job.url,
                    "source": job.source,
                    "salary_raw": job.salary_raw,
                    "relevance_score": score.relevance_score,
                    "explanation": score.explanation,
                    "scraped_at": job.scraped_at.isoformat() if job.scraped_at else None,
                })
            return output

    def get_stats(self) -> dict:
        """Return overall statistics."""
        with self.session() as s:
            total_jobs = s.query(Job).count()
            scored_jobs = s.query(ScoredJob).count()
            high_quality = s.query(ScoredJob).filter(ScoredJob.relevance_score >= 80).count()
            notifications_sent = s.query(Notification).filter(Notification.success == True).count()
            recent_logs = (
                s.query(ScrapingLog)
                .order_by(ScrapingLog.run_at.desc())
                .limit(5)
                .all()
            )
            return {
                "total_jobs": total_jobs,
                "scored_jobs": scored_jobs,
                "high_quality_jobs": high_quality,
                "notifications_sent": notifications_sent,
                "recent_runs": [
                    {
                        "source": log.source,
                        "run_at": log.run_at.isoformat() if log.run_at else None,
                        "jobs_found": log.jobs_found,
                        "jobs_new": log.jobs_new,
                    }
                    for log in recent_logs
                ],
            }

    def update_job_status(self, job_id: int, status: str) -> None:
        with self.session() as s:
            s.query(Job).filter(Job.id == job_id).update({"status": status})
