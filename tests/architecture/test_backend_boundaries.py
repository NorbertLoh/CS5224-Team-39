"""Keep reusable operations, adapters and workers independent of HTTP routers."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_non_http_packages_do_not_import_api_modules():
    violations = []
    for package in ("services", "integrations", "workers"):
        for path in (ROOT / "services").glob(f"*/app/{package}/**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                    if node.module == "app":
                        modules.extend("app." + alias.name for alias in node.names)
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                if any(module == "app.api" or module.startswith("app.api.") for module in modules):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "Non-HTTP code imports route modules: " + ", ".join(violations)
