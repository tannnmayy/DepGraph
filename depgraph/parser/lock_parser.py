"""Parser for poetry.lock and uv.lock lockfiles."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from depgraph.parser.models import Package


def parse_poetry_lock(path: str) -> List[Package]:
    """Parse a poetry.lock file to extract resolved package versions.

    Poetry.lock uses TOML format with [[package]] array of tables.
    Each entry has: name, version, description, category, optional,
    and [package.dependencies] for transitive dependencies.

    Args:
        path: Path to the poetry.lock file.

    Returns:
        List of Package objects with exact resolved versions.
    """
    lock_path = Path(path)
    if not lock_path.exists():
        return []

    try:
        with open(lock_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []

    packages: List[Package] = []
    raw_packages = data.get("package", [])

    for pkg_data in raw_packages:
        name = pkg_data.get("name", "")
        version = pkg_data.get("version", "")

        if not name or not version:
            continue

        # Extract transitive dependencies
        deps_section = pkg_data.get("dependencies", {})
        depends_on: List[str] = []

        for dep_name, dep_spec in deps_section.items():
            # dep_spec can be a string (">=1.0") or dict ({"version": ">=1.0", "optional": true})
            depends_on.append(dep_name.lower().replace("-", "_"))

        packages.append(
            Package(
                name=name,
                version=version,
                constraint=f"=={version}",
                source="transitive",
                depends_on=depends_on,
            )
        )

    return packages


def parse_uv_lock(path: str) -> List[Package]:
    """Parse a uv.lock file to extract resolved package versions.

    uv.lock is TOML-based with [[package]] entries similar to poetry.lock.
    Each entry includes: name, version, source, and dependencies.

    Args:
        path: Path to the uv.lock file.

    Returns:
        List of Package objects with exact resolved versions.
    """
    lock_path = Path(path)
    if not lock_path.exists():
        return []

    try:
        with open(lock_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []

    packages: List[Package] = []
    raw_packages = data.get("package", [])

    for pkg_data in raw_packages:
        name = pkg_data.get("name", "")
        version = pkg_data.get("version", "")

        if not name or not version:
            continue

        # uv.lock stores dependencies as a list of dicts or strings
        deps_section = pkg_data.get("dependencies", [])
        depends_on: List[str] = []

        if isinstance(deps_section, list):
            for dep in deps_section:
                if isinstance(dep, dict):
                    dep_name = dep.get("name", "")
                elif isinstance(dep, str):
                    # Parse "package_name>=1.0" format
                    dep_name = re.split(r"[><=!~\s;]", dep)[0]
                else:
                    continue
                if dep_name:
                    depends_on.append(dep_name.lower().replace("-", "_"))

        packages.append(
            Package(
                name=name,
                version=version,
                constraint=f"=={version}",
                source="transitive",
                depends_on=depends_on,
            )
        )

    return packages


def detect_and_parse_lockfile(service_dir: str) -> List[Package]:
    """Auto-detect and parse the lockfile in a service directory.

    Checks for poetry.lock first, then uv.lock.

    Args:
        service_dir: Path to the service directory.

    Returns:
        List of Package objects from the lockfile, or empty list if none found.
    """
    service_path = Path(service_dir)

    poetry_lock = service_path / "poetry.lock"
    if poetry_lock.exists():
        return parse_poetry_lock(str(poetry_lock))

    uv_lock = service_path / "uv.lock"
    if uv_lock.exists():
        return parse_uv_lock(str(uv_lock))

    return []
