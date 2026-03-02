"""Unit tests for src/storage/vector_store.py"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch, call

import pytest

from src.storage.vector_store import VectorStore


@pytest.fixture
def mock_collection():
    """Mock ChromaDB collection."""
    collection = MagicMock()
    collection.count.return_value = 0
    collection.get.return_value = {"ids": [], "metadatas": [], "documents": []}
    collection.add = MagicMock()
    collection.query.return_value = {
        "ids": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    collection.delete = MagicMock()
    return collection


@pytest.fixture
def mock_chroma_client(mock_collection):
    """Mock ChromaDB PersistentClient."""
    client = MagicMock()
    client.get_or_create_collection.return_value = mock_collection
    client.delete_collection = MagicMock()
    return client


@pytest.fixture
def vector_store(mock_chroma_client, tmp_path):
    """VectorStore with mocked ChromaDB client."""
    with patch("src.storage.vector_store.chromadb.PersistentClient", return_value=mock_chroma_client):
        with patch("src.storage.vector_store.SentenceTransformerEmbeddingFunction", return_value=MagicMock()):
            store = VectorStore(
                persist_directory=str(tmp_path / "chroma"),
                collection_name="test_jobs",
            )
    store.collection = mock_chroma_client.get_or_create_collection.return_value
    return store


@pytest.fixture
def sample_job():
    return {
        "source": "linkedin",
        "title": "Director of Engineering",
        "company": "Acme Corp",
        "location": "Dubai, UAE",
        "url": "https://linkedin.com/jobs/view/director-123",
        "description": "Leading cloud platform engineering team.",
        "salary_raw": "AED 1,200,000",
    }


class TestMakeDocId:
    """Test _make_doc_id() method."""

    def test_returns_md5_hash(self, vector_store):
        url = "https://example.com/job/123"
        expected = hashlib.md5(url.encode()).hexdigest()
        assert vector_store._make_doc_id(url) == expected

    def test_same_url_same_id(self, vector_store):
        url = "https://example.com/job/456"
        assert vector_store._make_doc_id(url) == vector_store._make_doc_id(url)

    def test_different_urls_different_ids(self, vector_store):
        assert vector_store._make_doc_id("https://a.com/1") != vector_store._make_doc_id("https://b.com/2")


class TestAddJob:
    """Test add_job() method."""

    def test_adds_new_job_returns_true(self, vector_store, mock_collection, sample_job):
        mock_collection.get.return_value = {"ids": []}
        result = vector_store.add_job(sample_job)
        assert result is True
        mock_collection.add.assert_called_once()

    def test_duplicate_job_returns_false(self, vector_store, mock_collection, sample_job):
        doc_id = vector_store._make_doc_id(sample_job["url"])
        mock_collection.get.return_value = {"ids": [doc_id]}
        result = vector_store.add_job(sample_job)
        assert result is False
        mock_collection.add.assert_not_called()

    def test_add_job_includes_metadata(self, vector_store, mock_collection, sample_job):
        mock_collection.get.return_value = {"ids": []}
        vector_store.add_job(sample_job)
        call_kwargs = mock_collection.add.call_args[1]
        meta = call_kwargs["metadatas"][0]
        assert meta["title"] == "Director of Engineering"
        assert meta["company"] == "Acme Corp"
        assert meta["location"] == "Dubai, UAE"

    def test_add_job_truncates_long_url_in_metadata(self, vector_store, mock_collection):
        long_url_job = {
            "url": "https://example.com/job/" + "x" * 600,
            "title": "Director",
            "company": "C",
            "location": "Dubai",
            "description": "Test",
            "salary_raw": None,
        }
        mock_collection.get.return_value = {"ids": []}
        vector_store.add_job(long_url_job)
        call_kwargs = mock_collection.add.call_args[1]
        assert len(call_kwargs["metadatas"][0]["url"]) <= 500

    def test_add_job_returns_false_on_exception(self, vector_store, mock_collection, sample_job):
        mock_collection.get.return_value = {"ids": []}
        mock_collection.add.side_effect = Exception("ChromaDB error")
        result = vector_store.add_job(sample_job)
        assert result is False


class TestFindSimilar:
    """Test find_similar() method."""

    def test_returns_empty_list_for_empty_collection(self, vector_store, mock_collection):
        mock_collection.count.return_value = 0
        result = vector_store.find_similar("Director of Engineering Dubai")
        assert result == []

    def test_returns_jobs_list(self, vector_store, mock_collection):
        doc_id = "abc123"
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "ids": [[doc_id]],
            "metadatas": [[{"title": "Director", "company": "C", "location": "Dubai", "url": "https://e.com", "source": "linkedin", "salary_raw": ""}]],
            "distances": [[0.1]],
        }
        results = vector_store.find_similar("Director of Engineering", n_results=5)
        assert len(results) == 1
        assert results[0]["title"] == "Director"

    def test_result_includes_similarity(self, vector_store, mock_collection):
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "ids": [["abc"]],
            "metadatas": [[{"title": "D", "company": "C", "location": "Dubai", "url": "https://e.com", "source": "l", "salary_raw": ""}]],
            "distances": [[0.2]],
        }
        results = vector_store.find_similar("test query")
        assert "similarity" in results[0]
        assert results[0]["similarity"] == pytest.approx(0.8)  # 1 - 0.2

    def test_returns_empty_on_exception(self, vector_store, mock_collection):
        mock_collection.count.return_value = 1
        mock_collection.query.side_effect = Exception("query failed")
        result = vector_store.find_similar("test")
        assert result == []


class TestFindSimilarToCandidate:
    """Test find_similar_to_candidate() method."""

    def test_calls_find_similar(self, vector_store, mock_collection, candidate_profile):
        mock_collection.count.return_value = 0
        vector_store.find_similar_to_candidate(candidate_profile)
        # Should ultimately call collection.query (but with count=0, returns empty)

    def test_builds_query_from_profile(self, vector_store, mock_collection, candidate_profile):
        query = vector_store._build_candidate_query(candidate_profile)
        assert "Director" in query
        assert "Dubai" in query or "UAE" in query


class TestBuildDocText:
    """Test _build_doc_text() method."""

    def test_includes_title(self, vector_store, sample_job):
        text = vector_store._build_doc_text(sample_job)
        assert "Director of Engineering" in text

    def test_includes_company(self, vector_store, sample_job):
        text = vector_store._build_doc_text(sample_job)
        assert "Acme Corp" in text

    def test_includes_location(self, vector_store, sample_job):
        text = vector_store._build_doc_text(sample_job)
        assert "Dubai" in text

    def test_truncates_long_description(self, vector_store):
        job = {
            "title": "D",
            "company": "C",
            "location": "Dubai",
            "salary_raw": "",
            "description": "x" * 5000,
        }
        text = vector_store._build_doc_text(job)
        desc_part = text.split("Description: ")[-1] if "Description: " in text else ""
        assert len(desc_part) <= 2100


class TestDeleteJob:
    """Test delete_job() method."""

    def test_deletes_job(self, vector_store, mock_collection, sample_job):
        vector_store.delete_job(sample_job["url"])
        mock_collection.delete.assert_called_once()

    def test_delete_does_not_raise_on_exception(self, vector_store, mock_collection, sample_job):
        mock_collection.delete.side_effect = Exception("delete failed")
        # Should not raise
        vector_store.delete_job(sample_job["url"])


class TestCount:
    """Test count() method."""

    def test_returns_collection_count(self, vector_store, mock_collection):
        mock_collection.count.return_value = 42
        assert vector_store.count() == 42


class TestReset:
    """Test reset() method."""

    def test_reset_deletes_and_recreates_collection(self, vector_store, mock_chroma_client, mock_collection):
        vector_store.reset()
        mock_chroma_client.delete_collection.assert_called_once_with("test_jobs")
        mock_chroma_client.get_or_create_collection.assert_called()
