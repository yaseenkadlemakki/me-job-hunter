"""Unit tests for src/matching/embeddings.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import src.matching.embeddings as embeddings_module
from src.matching.embeddings import (
    cosine_similarity,
    embed_candidate,
    embed_job,
    embed_text,
    compute_semantic_similarity,
)


@pytest.fixture(autouse=True)
def reset_model():
    """Reset the global model before each test."""
    original = embeddings_module._model
    yield
    embeddings_module._model = original


@pytest.fixture
def mock_sentence_transformer():
    """Mock SentenceTransformer model."""
    model = MagicMock()
    # Return normalized 384-dim vectors
    model.encode = MagicMock(
        side_effect=lambda text, normalize_embeddings=True: np.random.rand(384).astype(np.float32) / np.linalg.norm(np.random.rand(384))
    )
    return model


@pytest.fixture
def mock_model_identical():
    """Mock model that returns a fixed vector (for testing cosine_similarity)."""
    fixed_vec = np.ones(384, dtype=np.float32)
    fixed_vec /= np.linalg.norm(fixed_vec)

    model = MagicMock()
    model.encode = MagicMock(return_value=fixed_vec)
    return model


class TestEmbedText:
    """Test embed_text() function."""

    def test_returns_numpy_array(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        result = embed_text("Hello world")
        assert isinstance(result, np.ndarray)

    def test_returns_correct_dimensions(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        result = embed_text("Director of Engineering at Juniper Networks in Dubai")
        assert result.shape == (384,)

    def test_calls_encode(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        embed_text("test text")
        mock_sentence_transformer.encode.assert_called_once()

    def test_normalize_embeddings_true(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        embed_text("test")
        call_kwargs = mock_sentence_transformer.encode.call_args
        assert call_kwargs[1].get("normalize_embeddings", True) is True

    def test_loads_model_if_not_loaded(self, mock_sentence_transformer):
        embeddings_module._model = None
        with patch(
            "src.matching.embeddings.SentenceTransformer",
            return_value=mock_sentence_transformer
        ):
            result = embed_text("test")
            assert isinstance(result, np.ndarray)


class TestEmbedJob:
    """Test embed_job() function."""

    def test_returns_numpy_array(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        job = {
            "title": "Director of Engineering",
            "company": "Acme Corp",
            "location": "Dubai, UAE",
            "description": "Lead a team of engineers.",
        }
        result = embed_job(job)
        assert isinstance(result, np.ndarray)

    def test_uses_title_company_location_desc(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        job = {
            "title": "VP Engineering",
            "company": "Gulf Tech",
            "location": "Dubai",
            "description": "Great role",
        }
        embed_job(job)
        encoded_text = mock_sentence_transformer.encode.call_args[0][0]
        assert "VP Engineering" in encoded_text
        assert "Gulf Tech" in encoded_text
        assert "Dubai" in encoded_text

    def test_handles_empty_description(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        job = {"title": "Director", "company": "C", "location": "Dubai", "description": ""}
        result = embed_job(job)
        assert isinstance(result, np.ndarray)

    def test_truncates_long_description(self, mock_sentence_transformer):
        embeddings_module._model = mock_sentence_transformer
        job = {
            "title": "Director",
            "company": "C",
            "location": "Dubai",
            "description": "x" * 5000,
        }
        embed_job(job)
        encoded_text = mock_sentence_transformer.encode.call_args[0][0]
        # Description should be truncated to 1000 chars
        desc_part = encoded_text.split("Description: ")[-1] if "Description: " in encoded_text else ""
        assert len(desc_part) <= 1100  # some buffer


class TestEmbedCandidate:
    """Test embed_candidate() function."""

    def test_returns_numpy_array(self, mock_sentence_transformer, candidate_profile):
        embeddings_module._model = mock_sentence_transformer
        result = embed_candidate(candidate_profile)
        assert isinstance(result, np.ndarray)

    def test_includes_role_in_text(self, mock_sentence_transformer, candidate_profile):
        embeddings_module._model = mock_sentence_transformer
        embed_candidate(candidate_profile)
        encoded_text = mock_sentence_transformer.encode.call_args[0][0]
        assert "Director" in encoded_text

    def test_includes_skills_in_text(self, mock_sentence_transformer, candidate_profile):
        embeddings_module._model = mock_sentence_transformer
        embed_candidate(candidate_profile)
        encoded_text = mock_sentence_transformer.encode.call_args[0][0]
        assert "Kubernetes" in encoded_text or "AWS" in encoded_text


class TestCosineSimilarity:
    """Test cosine_similarity() function."""

    def test_identical_vectors_return_1(self):
        v = np.array([1.0, 0.0, 0.0])
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors_return_0(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors_return_minus_1(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_returns_float(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.5, 0.5])
        result = cosine_similarity(a, b)
        assert isinstance(result, float)


class TestComputeSemanticSimilarity:
    """Test compute_semantic_similarity() function."""

    def test_returns_float_between_0_and_100(self, mock_sentence_transformer, candidate_profile):
        embeddings_module._model = mock_sentence_transformer
        job = {"title": "Director", "company": "C", "location": "Dubai", "description": ""}
        result = compute_semantic_similarity(job, candidate_profile)
        assert isinstance(result, float)
        assert 0 <= result <= 100

    def test_same_text_similarity_near_100(self, candidate_profile):
        """Identical job and candidate profiles should have high similarity."""
        fixed_vec = np.ones(384, dtype=np.float32)
        fixed_vec /= np.linalg.norm(fixed_vec)

        model = MagicMock()
        model.encode = MagicMock(return_value=fixed_vec)
        embeddings_module._model = model

        job = {"title": "Director", "company": "C", "location": "Dubai", "description": ""}
        result = compute_semantic_similarity(job, candidate_profile)
        # With identical vectors, cosine_similarity = 1.0, so score = (1+1)/2*100 = 100
        assert abs(result - 100.0) < 1.0

    def test_returns_50_on_error(self, candidate_profile):
        """Returns 50.0 (neutral) if embedding fails."""
        embeddings_module._model = None
        with patch("src.matching.embeddings._get_model", side_effect=Exception("model error")):
            job = {"title": "Director", "company": "C", "location": "Dubai", "description": ""}
            result = compute_semantic_similarity(job, candidate_profile)
            assert result == 50.0
