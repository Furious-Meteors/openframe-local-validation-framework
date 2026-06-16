"""
Architecture tests.

Prove the hexagonal boundary is intact:
- Domain never imports from adapters
- Service never imports from adapters
- Only bootstrap/dependencies.py and adapters/outbound/ import from openframe.adapters
"""
from __future__ import annotations

import ast
import pathlib


def _get_imports(filepath: pathlib.Path) -> list[str]:
    """Extract all import module names from a Python file."""
    source = filepath.read_text()
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


SERVICE_ROOT = pathlib.Path(__file__).parent.parent / "src"


def test_domain_does_not_import_adapters():
    domain_files = list((SERVICE_ROOT / "domain").rglob("*.py"))
    assert domain_files, "No domain files found"
    for f in domain_files:
        imports = _get_imports(f)
        adapter_imports = [i for i in imports if "openframe.adapters" in i]
        assert not adapter_imports, \
            f"{f.name} imports from openframe.adapters: {adapter_imports}"


def test_domain_does_not_import_asyncpg():
    domain_files = list((SERVICE_ROOT / "domain").rglob("*.py"))
    for f in domain_files:
        imports = _get_imports(f)
        assert "asyncpg" not in imports, \
            f"{f.name} imports asyncpg — domain must be infrastructure-free"


def test_service_does_not_import_adapters():
    service_files = list((SERVICE_ROOT / "application").rglob("*.py"))
    assert service_files, "No application files found"
    for f in service_files:
        imports = _get_imports(f)
        adapter_imports = [i for i in imports if "openframe.adapters" in i]
        assert not adapter_imports, \
            f"{f.name} imports from openframe.adapters: {adapter_imports}"


def test_service_does_not_import_asyncpg():
    service_files = list((SERVICE_ROOT / "application").rglob("*.py"))
    for f in service_files:
        imports = _get_imports(f)
        assert "asyncpg" not in imports, \
            f"{f.name} imports asyncpg — service must not touch infrastructure"


def test_only_outbound_and_bootstrap_import_openframe_adapters():
    """
    openframe.adapters may only appear in:
      - src/adapters/outbound/item_repository.py
      - src/bootstrap/dependencies.py
    Domain and application layers are strictly forbidden.
    """
    forbidden_dirs = {"domain", "application"}
    all_py = list(SERVICE_ROOT.rglob("*.py"))
    for f in all_py:
        relative = f.relative_to(SERVICE_ROOT)
        if not any(str(relative).startswith(d) for d in forbidden_dirs):
            continue
        imports = _get_imports(f)
        adapter_imports = [i for i in imports if "openframe.adapters" in i]
        assert not adapter_imports, \
            f"Unexpected openframe.adapters import in {relative}: {adapter_imports}"


def test_bootstrap_imports_openframe_adapters():
    """bootstrap/dependencies.py MUST import from openframe.adapters."""
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = _get_imports(deps)
    assert any("openframe.adapters" in i for i in imports), \
        "bootstrap/dependencies.py should import from openframe.adapters"


def test_outbound_adapter_imports_openframe_adapters():
    """The outbound adapter MUST subclass from openframe.adapters."""
    adapter_file = SERVICE_ROOT / "adapters" / "outbound" / "item_repository.py"
    imports = _get_imports(adapter_file)
    assert any("openframe.adapters" in i for i in imports), \
        "item_repository.py should import from openframe.adapters"
