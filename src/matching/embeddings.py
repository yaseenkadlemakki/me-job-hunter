"""Generate and manage job embeddings using sentence-transformers."""

from __future__ import annotations

import numpy as np
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger("embeddings")

_model = None


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded sentence-transformer model: all-MiniLM-L6-v2")
        except Exception as e:
            logger.error(f"Failed to load sentence-transformer: {e}")
            raise
    return _model


def embed_text(text: str) -> np.ndarray:
    """Generate a 384-dim embedding for text."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding


def embed_job(job_data: dict) -> np.ndarray:
    """Generate embedding for a job posting."""
    parts = [
        f"Title: {job_data.get('title', '')}",
        f"Company: {job_data.get('company', '')}",
        f"Location: {job_data.get('location', '')}",
        f"Description: {(job_data.get('description') or '')[:1000]}",
    ]
    text = " ".join(p for p in parts if p.split(": ", 1)[1])
    return embed_text(text)


def embed_candidate(profile: dict) -> np.ndarray:
    """Generate embedding for the candidate profile."""
    skills = ", ".join(profile.get("skills", []))
    industries = ", ".join(profile.get("industries", []))
    text = (
        f"Role: {profile.get('current_role', '')} at {profile.get('current_company', '')}. "
        f"Skills: {skills}. "
        f"Industries: {industries}. "
        f"Summary: {profile.get('summary', '')} "
        f"Target: Director VP Head Engineering Platform Infrastructure DevOps Dubai UAE"
    )
    return embed_text(text)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two normalized vectors."""
    return float(np.dot(a, b))


def compute_semantic_similarity(job_data: dict, candidate_profile: dict) -> float:
    """Return semantic similarity score (0-100) between job and candidate."""
    try:
        job_emb = embed_job(job_data)
        cand_emb = embed_candidate(candidate_profile)
        sim = cosine_similarity(job_emb, cand_emb)
        # Convert from [-1, 1] to [0, 100]
        score = (sim + 1) / 2 * 100
        return round(score, 1)
    except Exception as e:
        logger.warning(f"Semantic similarity failed: {e}")
        return 50.0  # neutral fallback
