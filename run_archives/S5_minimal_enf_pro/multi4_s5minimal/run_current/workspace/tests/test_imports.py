"""
Tests for import validity and circular dependency detection.
"""
import importlib
import sys
import pytest


def _fresh_import(module_name: str):
    """Import a module fresh (remove from cache first)."""
    # Remove all related modules from cache
    to_remove = [k for k in sys.modules if k.startswith(module_name.split(".")[0])]
    for k in to_remove:
        del sys.modules[k]
    return importlib.import_module(module_name)


class TestNoCircularImports:
    """Bug 1: models must not import from api (circular dependency)."""

    def test_models_helpers_no_api_import(self):
        """models.helpers should import from utils.formatters, not api.formatters."""
        import ast
        with open("models/helpers.py") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module and node.module.startswith("api.")), (
                    f"{node.module} import in models/helpers.py creates "
                    f"circular dependency. Import from utils instead."
                )

    def test_models_imports_successfully(self):
        """After fixing the circular import, models should import cleanly."""
        # Clear module cache
        to_remove = [k for k in list(sys.modules.keys())
                     if k.startswith(("models", "api", "core", "utils"))]
        for k in to_remove:
            del sys.modules[k]
        mod = importlib.import_module("models.helpers")
        assert hasattr(mod, "serialize_entity")
        assert hasattr(mod, "format_response")

    def test_dependency_graph_acyclic(self):
        """Verify no circular dependencies exist in the import graph."""
        import ast
        packages = ["core", "models", "api", "worker", "utils"]
        # Build adjacency list from imports
        graph = {pkg: set() for pkg in packages}
        for pkg in packages:
            for suffix in ["__init__", "helpers", "entities", "endpoints", "formatters",
                           "tasks", "processing", "base"]:
                path = f"{pkg}/{suffix}.py"
                try:
                    with open(path) as f:
                        source = f.read()
                except FileNotFoundError:
                    continue
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        dep_pkg = node.module.split(".")[0]
                        if dep_pkg in packages and dep_pkg != pkg:
                            graph[pkg].add(dep_pkg)

        # Detect cycles using DFS
        visited = set()
        in_stack = set()
        def has_cycle(node):
            visited.add(node)
            in_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor in in_stack:
                    return True
                if neighbor not in visited and has_cycle(neighbor):
                    return True
            in_stack.discard(node)
            return False

        for pkg in packages:
            if pkg not in visited:
                assert not has_cycle(pkg), (
                    f"Circular dependency detected involving {pkg}. "
                    f"Graph: {{k: sorted(v) for k, v in graph.items()}}"
                )


class TestMovedFunction:
    """Bug 3: worker must import process_item from utils, not core."""

    def test_worker_imports_from_utils(self):
        """worker/tasks.py should import from utils.processing, not core.processing."""
        import ast
        with open("worker/tasks.py") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.names and any(a.name == "process_item" for a in node.names):
                    assert node.module == "utils.processing", (
                        f"process_item must be imported from "
                        f"utils.processing, not {node.module}"
                    )

    def test_worker_task_runs(self):
        """After fixing the import, the worker task should execute."""
        to_remove = [k for k in list(sys.modules.keys())
                     if k.startswith(("worker", "core", "utils"))]
        for k in to_remove:
            del sys.modules[k]
        mod = importlib.import_module("worker.tasks")
        result = mod.run_batch([{"id": 1, "type": "test"}])
        assert len(result) == 1
        assert result[0]["processed"] is True
