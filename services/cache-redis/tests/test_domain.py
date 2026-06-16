from __future__ import annotations

import pytest
from src.domain.session import Session


def test_session_default_metadata():
    s = Session(id="s1", user_id="u1")
    assert s.metadata == {}


def test_session_default_created_at_none():
    s = Session(id="s1", user_id="u1")
    assert s.created_at is None


def test_session_id_required():
    with pytest.raises(Exception):
        Session(user_id="u1")


def test_session_user_id_required():
    with pytest.raises(Exception):
        Session(id="s1")


def test_session_no_infrastructure_imports():
    import inspect
    import src.domain.session as m
    source = inspect.getsource(m)
    assert "redis" not in source
    assert "openframe.adapters" not in source
