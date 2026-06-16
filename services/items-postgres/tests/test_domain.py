"""
Tests for Item domain entity.

Domain has zero infrastructure imports.
These tests require only pydantic — no mocks, no adapters.
"""
from __future__ import annotations

import pytest
from src.domain.item import Item


def test_item_default_status():
    item = Item(id="1", name="Widget")
    assert item.status == "active"


def test_item_default_description_is_none():
    item = Item(id="1", name="Widget")
    assert item.description is None


def test_item_default_created_at_is_none():
    item = Item(id="1", name="Widget")
    assert item.created_at is None


def test_item_with_all_fields():
    item = Item(id="1", name="Widget", description="Desc", status="inactive")
    assert item.id == "1"
    assert item.name == "Widget"
    assert item.description == "Desc"
    assert item.status == "inactive"


def test_item_model_copy_preserves_fields(item_factory):
    item = item_factory(id="orig")
    copy = item.model_copy(update={"status": "inactive"})
    assert copy.id == "orig"
    assert copy.status == "inactive"


def test_item_id_required():
    with pytest.raises(Exception):
        Item(name="Widget")


def test_item_name_required():
    with pytest.raises(Exception):
        Item(id="1")


def test_item_no_infrastructure_imports():
    """Domain layer must not import from openframe.adapters."""
    import inspect
    import src.domain.item as domain_module
    source = inspect.getsource(domain_module)
    assert "openframe.adapters" not in source
    assert "asyncpg" not in source
    assert "motor" not in source
    assert "redis" not in source
