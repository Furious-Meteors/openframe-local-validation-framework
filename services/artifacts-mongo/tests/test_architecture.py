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


def test_service_has_no_motor_imports():
    for f in (SERVICE_ROOT / "application").rglob("*.py"):
        imports = _get_imports(f)
        assert "motor" not in " ".join(imports), \
            f"{f.name} imports motor directly"


def test_bootstrap_imports_openframe_adapters():
    deps = SERVICE_ROOT / "bootstrap" / "dependencies.py"
    imports = _get_imports(deps)
    assert any("openframe.adapters" in i for i in imports)


def test_outbound_adapter_imports_openframe_adapters():
    adapter_file = SERVICE_ROOT / "adapters" / "outbound" / "artifact_repository.py"
    imports = _get_imports(adapter_file)
    assert any("openframe.adapters" in i for i in imports)
