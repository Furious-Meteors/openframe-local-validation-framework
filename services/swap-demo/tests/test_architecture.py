"""
Architecture tests — hexagonal boundary verification.

Proves that only the adapter layer and bootstrap touch openframe.adapters.
Domain and application layers are infrastructure-free.
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
    """No asyncpg or motor imports outside the adapter layer."""
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = " ".join(_get_imports(f))
        assert "asyncpg" not in imports
        assert "motor" not in imports


def test_adapters_use_openframe_postgres_or_mongo():
    """
    Both outbound adapters must subclass from openframe.adapters,
    not hand-roll their own connection handling.
    """
    postgres_file = SERVICE_ROOT / "adapters" / "outbound" / "postgres_swap_repository.py"
    mongo_file    = SERVICE_ROOT / "adapters" / "outbound" / "mongo_swap_repository.py"

    pg_imports    = " ".join(_get_imports(postgres_file))
    mongo_imports = " ".join(_get_imports(mongo_file))

    assert "openframe.adapters.db.postgres" in pg_imports, \
        "PostgresSwapRepository must import from openframe.adapters.db.postgres"
    assert "openframe.adapters.db.mongo" in mongo_imports, \
        "MongoSwapRepository must import from openframe.adapters.db.mongo"


def test_bootstrap_imports_both_adapter_families():
    """
    bootstrap/app.py must be the single file that imports from both
    adapter packages and wires ApplicationBootstrap's conditional
    registration.
    """
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = " ".join(_get_imports(app_module))
    assert "openframe.adapters.db.postgres" in imports
    assert "openframe.adapters.db.mongo" in imports
    assert "openframe.core.runtime" in imports


def test_dependencies_does_not_import_adapter_packages_directly():
    """
    dependencies.py reads the port through _app.get(Capability.PERSISTENCE)
    — it must not import adapter packages itself; that belongs to app.py's
    configure().
    """
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = " ".join(_get_imports(deps))
    assert "openframe.adapters" not in imports


def test_entrypoints_have_no_adapter_imports():
    """Routes and main never import from openframe.adapters directly."""
    for f in (SERVICE_ROOT / "entrypoints").rglob("*.py"):
        imports = _get_imports(f)
        assert not any("openframe.adapters" in i for i in imports), \
            f"entrypoint {f.name} imports from openframe.adapters"
