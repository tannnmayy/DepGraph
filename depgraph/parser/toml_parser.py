"""Parser for pyproject.toml files (Poetry and PEP 621 formats)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from depgraph.parser.models import Package, Service


# Directories to skip during workspace scanning
_SKIP_DIRS = {
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    "node_modules",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
}


def _parse_pep508_constraint(requirement: str) -> Tuple[str, str]:
    """Parse a PEP 508 requirement string into (name, constraint).

    Examples:
        "requests>=2.28.0,<3.0" -> ("requests", ">=2.28.0,<3.0")
        "numpy" -> ("numpy", "")
        "pandas[sql]>=2.0" -> ("pandas", ">=2.0")
    """
    # Strip extras like [sql], environment markers like ; python_version
    requirement = requirement.strip()

    # Remove environment markers
    requirement = requirement.split(";")[0].strip()

    # Match name (with optional extras) and version constraint
    match = re.match(r"^([a-zA-Z0-9_.-]+)(?:\[.*?\])?\s*(.*)", requirement)
    if not match:
        return requirement, ""

    name = match.group(1).strip()
    constraint = match.group(2).strip()
    return name, constraint


def _parse_poetry_version(version_spec) -> str:
    """Convert Poetry version specs to standard constraint strings.

    Handles:
        - Simple strings: "^2.28.0", "~1.5", ">=2.0,<3.0", "2.28.0"
        - Dict format: {version = "^2.28.0", optional = true}
        - Caret (^) and tilde (~) conversion
    """
    if isinstance(version_spec, dict):
        version_spec = version_spec.get("version", "")

    if not isinstance(version_spec, str):
        return ""

    version_spec = version_spec.strip()

    if not version_spec or version_spec == "*":
        return ""

    # Convert caret constraint: ^2.28.0 -> >=2.28.0,<3.0.0
    caret_match = re.match(r"^\^(\d+)\.(\d+)(?:\.(\d+))?$", version_spec)
    if caret_match:
        major = int(caret_match.group(1))
        minor = int(caret_match.group(2))
        patch = caret_match.group(3)
        if major > 0:
            return f">={major}.{minor}{('.' + patch) if patch else '.0'},<{major + 1}.0.0"
        elif minor > 0:
            return f">=0.{minor}{('.' + patch) if patch else '.0'},<0.{minor + 1}.0"
        else:
            patch_val = int(patch) if patch else 0
            return f">=0.0.{patch_val},<0.0.{patch_val + 1}"

    # Convert tilde constraint: ~1.5 -> >=1.5.0,<1.6.0
    tilde_match = re.match(r"^~(\d+)\.(\d+)(?:\.(\d+))?$", version_spec)
    if tilde_match:
        major = int(tilde_match.group(1))
        minor = int(tilde_match.group(2))
        return f">={major}.{minor}.0,<{major}.{minor + 1}.0"

    # Already a standard constraint (>=, <=, ==, !=, ~=)
    if any(version_spec.startswith(op) for op in (">=", "<=", "==", "!=", "~=", ">", "<")):
        return version_spec

    # Bare version: treat as ==
    if re.match(r"^\d+\.\d+(?:\.\d+)?$", version_spec):
        return f"=={version_spec}"

    return version_spec


def parse_pyproject(path: str) -> Optional[Service]:
    """Parse a pyproject.toml file and extract dependencies.

    Handles both Poetry format ([tool.poetry.dependencies]) and
    PEP 621 format ([project.dependencies]).

    Args:
        path: Path to the pyproject.toml file.

    Returns:
        A Service object with parsed dependencies, or None if parsing fails.
    """
    pyproject_path = Path(path)

    if not pyproject_path.exists():
        return None

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    service_dir = pyproject_path.parent
    dependencies: List[Package] = []
    service_name = ""
    python_version = ""

    # --- Try Poetry format first ---
    poetry_section = data.get("tool", {}).get("poetry", {})
    if poetry_section:
        service_name = poetry_section.get("name", "")
        poetry_deps = poetry_section.get("dependencies", {})

        for pkg_name, version_spec in poetry_deps.items():
            # Skip python itself
            if pkg_name.lower() == "python":
                if isinstance(version_spec, str):
                    python_version = version_spec
                elif isinstance(version_spec, dict):
                    python_version = version_spec.get("version", "")
                continue

            constraint = _parse_poetry_version(version_spec)
            # Extract exact version from constraint if it's ==X.Y.Z
            exact_version = ""
            eq_match = re.match(r"^==(.+)$", constraint)
            if eq_match:
                exact_version = eq_match.group(1)

            dependencies.append(
                Package(
                    name=pkg_name,
                    version=exact_version,
                    constraint=constraint,
                    source="direct",
                )
            )

    # --- Try PEP 621 format ---
    project_section = data.get("project", {})
    if project_section and not dependencies:
        service_name = project_section.get("name", service_name)
        python_version = project_section.get("requires-python", python_version)
        pep621_deps = project_section.get("dependencies", [])

        for req in pep621_deps:
            name, constraint = _parse_pep508_constraint(req)
            exact_version = ""
            eq_match = re.match(r"^==(.+)$", constraint)
            if eq_match:
                exact_version = eq_match.group(1)

            dependencies.append(
                Package(
                    name=name,
                    version=exact_version,
                    constraint=constraint,
                    source="direct",
                )
            )

    # Fallback service name to directory name
    if not service_name:
        service_name = service_dir.name

    return Service(
        name=service_name,
        path=str(service_dir),
        python_version=python_version,
        dependencies=dependencies,
    )


def scan_workspace(root_path: str) -> List[Service]:
    """Scan a workspace directory for all Python services.

    Recursively walks the directory tree looking for pyproject.toml files.
    Skips common non-project directories (.venv, node_modules, .git, etc.).
    Ignores the root-level pyproject.toml (assumed to be workspace config).

    Args:
        root_path: Path to the workspace root directory.

    Returns:
        List of Service objects found in the workspace.
    """
    root = Path(root_path).resolve()
    services: List[Service] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories we should skip
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        if "pyproject.toml" in filenames:
            pyproject_path = Path(dirpath) / "pyproject.toml"

            # Skip the root-level pyproject.toml (workspace config)
            if pyproject_path.parent.resolve() == root:
                continue

            service = parse_pyproject(str(pyproject_path))
            if service and service.dependencies:
                services.append(service)

    return services
