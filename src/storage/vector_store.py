"""ChromaDB vector store operations."""

from __future__ import annotations

import os
import json
import hashlib
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.utils.logger import setup_logger

try:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except Exception:
    SentenceTransformerEmbeddingFunction = None

logger = setup_logger("vector_store")


class VectorStore:
    """Persistent ChromaDB vector store for job postings."""

    def __init__(
        self,
        persist_directory: str = "./data/chroma",
        collection_name: str = "job_postings",
        embedding_function=None,
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        os.makedirs(persist_directory, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        # Use provided embedding function or default (sentence-transformers)
        if embedding_function is None:
            try:
                if SentenceTransformerEmbeddingFunction is not None:
                    embedding_function = SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )
                    logger.info("Using SentenceTransformer embeddings (all-MiniLM-L6-v2)")
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer: {e}. Using default embeddings.")
                embedding_function = None

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Vector store initialized: {collection_name} ({self.collection.count()} docs)")

    def _make_doc_id(self, url: str) -> str:
        """Create a stable document ID from URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def add_job(self, job_data: dict) -> bool:
        """Add a job to the vector store. Returns False if already exists."""
        doc_id = self._make_doc_id(job_data.get("url", ""))

        # Check if already exists
        existing = self.collection.get(ids=[doc_id])
        if existing["ids"]:
            logger.debug(f"Job already in vector store: {doc_id}")
            return False

        # Build document text for embedding
        doc_text = self._build_doc_text(job_data)

        metadata = {
            "url": job_data.get("url", "")[:500],
            "title": job_data.get("title", "")[:200],
            "company": job_data.get("company", "")[:200],
            "location": job_data.get("location", "")[:200],
            "source": job_data.get("source", "")[:50],
            "salary_raw": (job_data.get("salary_raw") or "")[:200],
        }

        try:
            self.collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[doc_id],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add job to vector store: {e}")
            return False

    def _build_doc_text(self, job_data: dict) -> str:
        """Build text representation of job for embedding."""
        parts = [
            f"Title: {job_data.get('title', '')}",
            f"Company: {job_data.get('company', '')}",
            f"Location: {job_data.get('location', '')}",
            f"Salary: {job_data.get('salary_raw', '')}",
            f"Description: {(job_data.get('description') or '')[:2000]}",
        ]
        return "\n".join(p for p in parts if p.split(": ", 1)[1])

    def find_similar(self, query_text: str, n_results: int = 10) -> list[dict]:
        """Find similar jobs using semantic search."""
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(n_results, max(1, self.collection.count())),
            )
            jobs = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    dist = results["distances"][0][i] if results["distances"] else None
                    jobs.append({
                        "doc_id": doc_id,
                        "similarity": 1 - (dist or 0),
                        **meta,
                    })
            return jobs
        except Exception as e:
            logger.error(f"Vector store query failed: {e}")
            return []

    def find_similar_to_candidate(self, candidate_profile: dict, n_results: int = 20) -> list[dict]:
        """Find jobs most similar to the candidate profile."""
        query = self._build_candidate_query(candidate_profile)
        return self.find_similar(query, n_results)

    def _build_candidate_query(self, profile: dict) -> str:
        """Build query text from candidate profile."""
        skills = ", ".join(profile.get("skills", []))
        industries = ", ".join(profile.get("industries", []))
        parts = [
            f"Role: {profile.get('current_role', '')}",
            f"Skills: {skills}",
            f"Industries: {industries}",
            f"Target: Director Engineering VP Platform Infrastructure DevOps",
            f"Location: Dubai UAE Middle East",
        ]
        return "\n".join(parts)

    def count(self) -> int:
        return self.collection.count()

    def delete_job(self, url: str) -> None:
        doc_id = self._make_doc_id(url)
        try:
            self.collection.delete(ids=[doc_id])
        except Exception as e:
            logger.error(f"Failed to delete job from vector store: {e}")

    def reset(self) -> None:
        """Delete and recreate the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector store reset")
