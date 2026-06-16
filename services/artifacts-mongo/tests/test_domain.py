from __future__ import annotations

import pytest
from src.domain.artifact import EmbeddingStatus, ResearchArtifact


def test_artifact_default_embedding_status():
    a = ResearchArtifact(id="1", title="Paper", source="arxiv")
    assert a.embedding_status == EmbeddingStatus.PENDING


def test_artifact_default_tags_empty():
    a = ResearchArtifact(id="1", title="Paper", source="arxiv")
    assert a.tags == []


def test_artifact_with_tags():
    a = ResearchArtifact(id="1", title="Paper", source="arxiv", tags=["nlp", "ml"])
    assert "nlp" in a.tags


def test_embedding_status_values():
    assert EmbeddingStatus.PENDING.value    == "pending"
    assert EmbeddingStatus.PROCESSING.value == "processing"
    assert EmbeddingStatus.READY.value      == "ready"
    assert EmbeddingStatus.FAILED.value     == "failed"


def test_artifact_id_required():
    with pytest.raises(Exception):
        ResearchArtifact(title="Paper", source="arxiv")


def test_artifact_no_infrastructure_imports():
    import inspect
    import src.domain.artifact as m
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    assert "motor" not in source
    assert "pymongo" not in source
