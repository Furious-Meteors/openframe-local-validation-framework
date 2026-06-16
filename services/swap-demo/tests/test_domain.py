from __future__ import annotations

import pytest
from domain.swap_item import SwapItem


def test_swap_item_optional_description():
    item = SwapItem(id="1", name="X")
    assert item.description is None


def test_swap_item_id_required():
    with pytest.raises(Exception):
        SwapItem(name="X")


def test_swap_item_no_infrastructure_imports():
    import inspect
    import domain.swap_item as m
    source = inspect.getsource(m)
    assert "asyncpg" not in source
    assert "motor" not in source
    assert "openframe.adapters" not in source
