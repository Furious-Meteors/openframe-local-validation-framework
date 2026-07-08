"""Architecture tests — hexagonal boundary verification."""
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
    """No asyncpg or redis.asyncio imports outside the adapter layer."""
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = " ".join(_get_imports(f))
        assert "asyncpg" not in imports
        # "redis" import is only acceptable as openframe.adapters.db.redis
        bare_redis = any(
            i == "redis" or i.startswith("redis.")
            for i in _get_imports(f)
        )
        assert not bare_redis, f"{f.name} imports bare redis driver"


def test_bootstrap_imports_both_adapter_families():
    """
    bootstrap/app.py must import from both adapter packages — its
    ItemsCachedApp.configure() is what wires the two-adapter registry.
    """
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = " ".join(_get_imports(app_module))
    assert "openframe.adapters.db.postgres" in imports
    assert "openframe.adapters.db.redis" in imports


def test_bootstrap_uses_application_bootstrap():
    """Stage 2 wiring — must use ApplicationBootstrap, not raw PluginRegistry."""
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = " ".join(_get_imports(app_module))
    assert "openframe.core.runtime" in imports


def test_dependencies_does_not_import_adapter_packages_directly():
    """
    dependencies.py reads ports through _app.get(Capability.X) — it must
    not import adapter packages itself; that belongs to app.py's configure().
    """
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = " ".join(_get_imports(deps))
    assert "openframe.adapters" not in imports


def test_only_bootstrap_imports_adapters():
    """
    No file outside bootstrap/ and adapters/ should import from
    openframe.adapters — routes and services are infrastructure-free.
    """
    for f in (SERVICE_ROOT / "entrypoints").rglob("*.py"):
        imports = _get_imports(f)
        assert not any("openframe.adapters" in i for i in imports), \
            f"entrypoint {f.name} imports from openframe.adapters"
