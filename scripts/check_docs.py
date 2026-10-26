"""Check local Markdown links, backend settings and documented route coverage.

Uses only the standard library; does not fetch external URLs or import app
settings/secrets. Anchor contents are deliberately outside this file check.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "storage", "uploads", "Dataset",
            ".pytest-tmp", "pytest_tmp", "playwright-report", "test-results", "demo-artifacts"}
LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)")
HTML_LINK = re.compile(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
DOCUMENTED_ROUTE = re.compile(r"`((?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?:\|(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS))*)\s+(/[^`\s]+)`")


def markdown_files(root: Path):
    for directory, children, files in os.walk(root):
        children[:] = sorted(name for name in children if name not in EXCLUDED)
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield Path(directory) / name


def link_errors(root: Path) -> tuple[list[str], int]:
    errors, count = [], 0
    for document in markdown_files(root):
        count += 1
        fence = None
        for number, line in enumerate(document.read_text(encoding="utf-8-sig").splitlines(), 1):
            delimiter = FENCE.match(line)
            if delimiter:
                marker = delimiter.group(1)
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence):
                    fence = None
                continue
            if fence:
                continue
            targets = LINK.findall(line) + HTML_LINK.findall(line)
            reference = REFERENCE.match(line)
            if reference:
                targets.append(reference.group(1))
            for target in targets:
                target = target.strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                path = unquote(parsed.path)
                resolved = ((root / path.lstrip("/")) if path.startswith("/") else document.parent / path).resolve()
                if not resolved.is_relative_to(root) or not resolved.exists():
                    errors.append(f"{document.relative_to(root)}:{number}: missing local target {target}")
    return errors, count


def configuration_errors(root: Path) -> list[str]:
    source = root / "backend/config/settings.py"
    reference = root / "docs/CONFIGURATION.md"
    if not source.exists():
        return []
    if not reference.exists():
        return ["docs/CONFIGURATION.md is missing"]
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    names = {node.target.id for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "Settings"
             for node in item.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", reference.read_text(encoding="utf-8-sig")))
    return [f"docs/CONFIGURATION.md: undocumented backend setting {name}" for name in sorted(names - documented)]


def _route_key(method: str, path: str) -> tuple[str, str]:
    # Route parameter names differ in explanatory examples; shape and method
    # still have to match. /health and /health/ are one documented operation.
    return method.upper(), re.sub(r"\{[^}]+\}", "{}", path.rstrip("/") or "/")


def route_inventory(root: Path) -> set[tuple[str, str]]:
    """Read literal include_router/decorator declarations without importing app."""
    app_path = root / "backend/app.py"
    if not app_path.exists():
        return set()
    app_tree = ast.parse(app_path.read_text(encoding="utf-8-sig"))
    aliases = {alias.asname or alias.name: alias.name
               for item in app_tree.body if isinstance(item, ast.ImportFrom) and item.module == "api.routes"
               for alias in item.names}
    routes = set()
    for call in ast.walk(app_tree):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "include_router" and call.args):
            continue
        router = call.args[0]
        if not (isinstance(router, ast.Attribute) and isinstance(router.value, ast.Name)):
            raise ValueError("Route coverage requires a named router import")
        prefix = next((item.value for item in call.keywords if item.arg == "prefix"), ast.Constant(""))
        if not isinstance(prefix, ast.Constant) or not isinstance(prefix.value, str):
            raise ValueError("Route coverage requires a literal router prefix")
        source = root / "backend/api/routes" / f"{aliases.get(router.value.id, router.value.id)}.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        for function in tree.body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in function.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr in METHODS and decorator.args):
                    continue
                path = decorator.args[0]
                if not isinstance(path, ast.Constant) or not isinstance(path.value, str):
                    raise ValueError(f"{source.name}: route coverage requires literal decorator paths")
                routes.add(_route_key(decorator.func.attr, prefix.value + path.value))
    return routes


def api_errors(root: Path) -> list[str]:
    if not (root / "backend/app.py").exists():
        return []
    reference = root / "docs/API_REFERENCE.md"
    if not reference.exists():
        return ["docs/API_REFERENCE.md is missing"]
    try:
        actual = route_inventory(root)
    except (ValueError, OSError) as exc:
        return [f"API route coverage: {exc}"]
    documented = {_route_key(method, path)
                  for methods, path in DOCUMENTED_ROUTE.findall(reference.read_text(encoding="utf-8-sig"))
                  for method in methods.split("|")}
    return ([f"docs/API_REFERENCE.md: undocumented route {method} {path}" for method, path in sorted(actual - documented)]
            + [f"docs/API_REFERENCE.md: stale route {method} {path}" for method, path in sorted(documented - actual)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository/document fixture root")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("root must be an existing directory")
    errors, count = link_errors(root)
    errors.extend(configuration_errors(root))
    errors.extend(api_errors(root))
    if errors:
        print("\n".join(errors))
        print(f"Documentation check failed: {len(errors)} error(s).")
        return 1
    print(f"Documentation checks passed: {count} Markdown files; local targets, backend settings and API routes covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
