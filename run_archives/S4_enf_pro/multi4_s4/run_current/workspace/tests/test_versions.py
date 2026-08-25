"""
Tests for version constraint consistency across the monorepo.
"""
import configparser
import os
import re
import pytest


def _parse_setup_cfg(path: str) -> dict:
    """Parse a setup.cfg and return metadata + dependencies."""
    config = configparser.ConfigParser()
    config.read(path)
    result = {
        "name": config.get("metadata", "name", fallback="unknown"),
        "version": config.get("metadata", "version", fallback="0.0.0"),
        "deps": [],
    }
    if config.has_option("options", "install_requires"):
        raw = config.get("options", "install_requires")
        for line in raw.strip().splitlines():
            line = line.strip()
            if line:
                result["deps"].append(line)
    return result


class TestVersionPins:
    """Bug 2: utils must pin core>=1.2, not core==1.0."""

    def test_utils_core_pin_not_stale(self):
        """utils/setup.cfg must require core>=1.2."""
        cfg = _parse_setup_cfg("utils/setup.cfg")
        core_deps = [d for d in cfg["deps"] if d.startswith("core")]
        assert len(core_deps) == 1, f"Expected 1 core dep, got {core_deps}"
        dep = core_deps[0]
        # Must NOT be ==1.0 (stale pin)
        assert "==1.0" not in dep, (
            f"utils still has stale pin: {dep}. "
            f"Change to core>=1.2"
        )
        # Must be >= the correct version
        assert ">=" in dep, (
            f"utils core dep must use >=, got: {dep}"
        )

    def test_all_versions_satisfiable(self):
        """All version constraints must be satisfiable together."""
        packages = {}
        for pkg in ["core", "models", "api", "worker", "utils"]:
            cfg_path = f"{pkg}/setup.cfg"
            if os.path.exists(cfg_path):
                packages[pkg] = _parse_setup_cfg(cfg_path)

        # Check each dependency is satisfiable
        for pkg_name, pkg_info in packages.items():
            for dep in pkg_info["deps"]:
                # Parse dependency spec
                match = re.match(r"([a-zA-Z_]+)(.*)", dep)
                if not match:
                    continue
                dep_name = match.group(1)
                dep_spec = match.group(2).strip()

                if dep_name in packages:
                    dep_version = packages[dep_name]["version"]
                    dep_parts = [int(x) for x in dep_version.split(".")]

                    if dep_spec.startswith(">="):
                        min_ver = dep_spec[2:]
                        min_parts = [int(x) for x in min_ver.split(".")]
                        assert dep_parts >= min_parts, (
                            f"{pkg_name} requires {dep}, but {dep_name} is v{dep_version}"
                        )
                    elif dep_spec.startswith("=="):
                        pin_ver = dep_spec[2:]
                        pin_parts = [int(x) for x in pin_ver.split(".")]
                        assert dep_parts[:len(pin_parts)] == pin_parts, (
                            f"{pkg_name} requires {dep}, but {dep_name} is v{dep_version}"
                        )
