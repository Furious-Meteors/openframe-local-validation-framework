from __future__ import annotations

import pytest
from src.domain.item import Item


def test_item_default_status():
    item = Item(id="1", name="Widget")
    assert item.status == "active"


def test_item_default_created_at_is_none():
    item = Item(id="1", name="Widget")
    assert item.created_at is None


def test_item_id_required():
    with pytest.raises(Exception):
        Item(name="Widget")


def test_item_no_infrastructure_imports():
    import src.domain.item as m, inspect
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    assert "asyncpg" not in source
    assert "redis" not in source
