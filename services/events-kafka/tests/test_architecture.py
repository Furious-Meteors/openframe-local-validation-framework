"""
Architecture tests — hexagonal boundary verification.

Only bootstrap/app.py is allowed to import from openframe.adapters (besides
the outbound adapter files). Domain and application layers must be
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


def test_service_has_no_adapter_imports():
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = _get_imports(f)
        assert not any("openframe.adapters" in i for i in imports), \
            f"{f.name} imports from openframe.adapters"


def test_service_has_no_aiokafka_imports():
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = " ".join(_get_imports(f))
        assert "aiokafka" not in imports, \
            f"{f.name} imports aiokafka directly"


def test_bootstrap_imports_openframe_adapters():
    """bootstrap/app.py MUST import from openframe.adapters."""
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = _get_imports(app_module)
    assert any("openframe.adapters" in i for i in imports), \
        "bootstrap/app.py should import from openframe.adapters"


def test_bootstrap_uses_application_bootstrap():
    """bootstrap/app.py MUST use ApplicationBootstrap."""
    app_module = SERVICE_ROOT / "bootstrap" / "app.py"
    imports = _get_imports(app_module)
    assert any("openframe.core.runtime" in i for i in imports), \
        "bootstrap/app.py should import openframe.core.runtime"


def test_dependencies_imports_only_outbound_adapters():
    """
    dependencies.py constructs OrderEventConsumer directly (see its module
    docstring for why KafkaPlugin.make_consumer() can't be used), so it
    imports the outbound consumer module — but must not import from
    openframe.adapters.* packages itself.
    """
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = " ".join(_get_imports(deps))
    assert "openframe.adapters" not in imports


def test_outbound_producer_imports_openframe_adapters():
    """The outbound producer MUST subclass from openframe.adapters."""
    adapter_file = SERVICE_ROOT / "adapters" / "outbound" / "order_producer.py"
    imports = _get_imports(adapter_file)
    assert any("openframe.adapters" in i for i in imports), \
        "order_producer.py should import from openframe.adapters"


def test_outbound_consumer_imports_openframe_adapters():
    """The outbound consumer MUST subclass from openframe.adapters."""
    adapter_file = SERVICE_ROOT / "adapters" / "outbound" / "order_consumer.py"
    imports = _get_imports(adapter_file)
    assert any("openframe.adapters" in i for i in imports), \
        "order_consumer.py should import from openframe.adapters"
