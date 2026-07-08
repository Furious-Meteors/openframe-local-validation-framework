"""
Architecture tests — hexagonal boundary verification.

Only bootstrap/dependencies.py and bootstrap/app.py are allowed to import
from openframe.adapters. Domain and application layers must be
infrastructure-free.
"""
from __future__ import annotations

import ast
import pathlib

SERVICE_ROOT = pathlib.Path(__file__).parent.parent / "src"


def _get_imports(filepath: pathlib.Path) -> list[str]:
    tree = ast.parse(filepath.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_domain_has_no_adapter_imports():
    for f in (SERVICE_ROOT / "domain").rglob("*.py"):
        imports = _get_imports(f)
        assert not any("openframe.adapters" in i for i in imports), \
            f"{f.name} imports from openframe.adapters"


def test_application_has_no_adapter_imports():
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = _get_imports(f)
        assert not any("openframe.adapters" in i for i in imports), \
            f"{f.name} imports from openframe.adapters"


def test_application_has_no_driver_imports():
    """No motor, redis, or aiokafka imports outside the adapter layer."""
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = " ".join(_get_imports(f))
        assert "motor" not in imports
        assert "aiokafka" not in imports


def test_bootstrap_imports_all_three_adapter_families():
    """
    bootstrap/app.py must import from all three adapter packages — its
    ResearchPipelineApp.configure() is what wires the three-adapter registry.
    """
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = " ".join(_get_imports(app_module))
    assert "openframe.adapters.db.mongo" in imports
    assert "openframe.adapters.db.redis" in imports
    assert "openframe.adapters.queue.kafka" in imports


def test_bootstrap_uses_application_bootstrap():
    """Stage 2 wiring — must use ApplicationBootstrap, not three separate lru_cache calls."""
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = " ".join(_get_imports(app_module))
    assert "openframe.core.runtime" in imports


def test_dependencies_does_not_import_adapter_packages_directly():
    """
    dependencies.py reads ports through _app.get(Capability.X) — it must not
    import adapter packages itself; that belongs to app.py's configure().
    """
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = " ".join(_get_imports(deps))
    assert "openframe.adapters" not in imports
