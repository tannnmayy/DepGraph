"""Conflict detection and dependency analysis engine."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import networkx as nx
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from depgraph.parser.models import Conflict, Package, Service


def detect_conflicts(services: List[Service]) -> List[Conflict]:
    """Detect dependency version conflicts across all services.

    Algorithm:
        1. Group all packages by normalized name across all services.
        2. For each package used by 2+ services, check version constraint overlap.
        3. Classify as critical (no overlap) or warning (different versions but overlap).

    Args:
        services: List of parsed Service objects.

    Returns:
        List of Conflict objects, sorted by severity (critical first).
    """
    # Group packages by name: {package_name: [(service_name, Package), ...]}
    package_usages: Dict[str, List[Tuple[str, Package]]] = defaultdict(list)

    for service in services:
        for pkg in service.dependencies:
            package_usages[pkg.name].append((service.name, pkg))

    conflicts: List[Conflict] = []

    for pkg_name, usages in package_usages.items():
        # Only check packages used by multiple services
        if len(usages) < 2:
            continue

        conflict = _check_version_compatibility(pkg_name, usages)
        if conflict:
            conflicts.append(conflict)

    # Sort: critical first, then by package name
    conflicts.sort(key=lambda c: (0 if c.severity == "critical" else 1, c.package_name))
    return conflicts


def _check_version_compatibility(
    package_name: str,
    usages: List[Tuple[str, Package]],
) -> Optional[Conflict]:
    """Check if multiple version constraints for a package can coexist.

    Uses the packaging library's SpecifierSet to determine if there's any
    version that satisfies ALL constraints simultaneously.

    Args:
        package_name: The package being checked.
        usages: List of (service_name, Package) tuples.

    Returns:
        A Conflict object if versions are incompatible, None otherwise.
    """
    service_names = [s for s, _ in usages]
    versions_dict: Dict[str, str] = {}

    for service_name, pkg in usages:
        versions_dict[service_name] = pkg.version or pkg.constraint or "unspecified"

    # Collect all constraints
    specifiers: List[Tuple[str, SpecifierSet]] = []
    exact_versions: List[Tuple[str, str]] = []

    for service_name, pkg in usages:
        constraint = pkg.constraint
        if not constraint:
            continue

        try:
            spec = SpecifierSet(constraint)
            specifiers.append((service_name, spec))
        except InvalidSpecifier:
            continue

        # Track exact versions (== constraints)
        if pkg.version:
            exact_versions.append((service_name, pkg.version))

    if not specifiers:
        return None

    # Check 1: If we have exact versions, check if they all match
    if len(exact_versions) >= 2:
        unique_versions = set(v for _, v in exact_versions)
        if len(unique_versions) > 1:
            # Different exact versions pinned — check if any version satisfies ALL constraints
            is_critical = _no_common_version(specifiers, exact_versions)

            if is_critical:
                version_strs = [f"{s}: {v}" for s, v in exact_versions]
                return Conflict(
                    package_name=package_name,
                    services=service_names,
                    versions=versions_dict,
                    severity="critical",
                    explanation=(
                        f"No single version satisfies all constraints. "
                        f"Services pin different exact versions: {', '.join(version_strs)}"
                    ),
                )
            else:
                return Conflict(
                    package_name=package_name,
                    services=service_names,
                    versions=versions_dict,
                    severity="warning",
                    explanation=(
                        f"Services use different versions but constraints may overlap. "
                        f"Consider aligning versions."
                    ),
                )

    # Check 2: Range-only constraints — check if specifier sets overlap
    if len(specifiers) >= 2:
        is_critical = _no_common_version(specifiers, exact_versions)

        if is_critical:
            constraint_strs = [f"{s}: {spec}" for s, spec in specifiers]
            return Conflict(
                package_name=package_name,
                services=service_names,
                versions=versions_dict,
                severity="critical",
                explanation=(
                    f"Version constraints are mutually exclusive: "
                    f"{', '.join(constraint_strs)}"
                ),
            )

        # Check for version drift (different versions pinned, but constraints overlap)
        if exact_versions and len(set(v for _, v in exact_versions)) > 1:
            return Conflict(
                package_name=package_name,
                services=service_names,
                versions=versions_dict,
                severity="warning",
                explanation=(
                    f"Services resolve to different versions. "
                    f"Constraints overlap but consider aligning for consistency."
                ),
            )

    return None


def _no_common_version(
    specifiers: List[Tuple[str, SpecifierSet]],
    exact_versions: List[Tuple[str, str]],
) -> bool:
    """Determine if there's no version that satisfies all specifiers at once.

    Tests known exact versions against all constraints. If none satisfies
    every constraint, it's a critical conflict.
    """
    # Gather candidate versions to test
    candidate_versions: List[str] = []
    for _, ver in exact_versions:
        candidate_versions.append(ver)

    # Also generate some candidates from specifier bounds
    # This is a heuristic — for production, you'd query PyPI
    if not candidate_versions:
        # Without exact versions, we can't definitively prove no overlap
        # Try a range of common versions
        candidate_versions = [
            f"{major}.{minor}.{patch}"
            for major in range(0, 10)
            for minor in range(0, 30)
            for patch in range(0, 5)
        ]

    for version_str in candidate_versions:
        try:
            version = Version(version_str)
        except InvalidVersion:
            continue

        # Check if this version satisfies ALL specifiers
        all_satisfied = all(version in spec for _, spec in specifiers)
        if all_satisfied:
            return False  # Found a common version — not critical

    return True  # No common version found


def detect_circular_dependencies(graph: nx.DiGraph) -> List[List[str]]:
    """Detect circular dependency chains in the graph.

    Args:
        graph: The dependency graph from builder.

    Returns:
        List of cycles, where each cycle is a list of node names.
    """
    try:
        cycles = list(nx.simple_cycles(graph))
        return cycles
    except nx.NetworkXError:
        return []


def find_dependency_path(
    graph: nx.DiGraph, source: str, target: str
) -> List[List[str]]:
    """Find all paths from source to target in the dependency graph.

    Args:
        graph: The dependency graph.
        source: Source node name.
        target: Target node name.

    Returns:
        List of paths (each path is a list of node names).
    """
    target_normalized = target.lower().replace("-", "_")
    try:
        return list(nx.all_simple_paths(graph, source, target_normalized, cutoff=10))
    except (nx.NodeNotFound, nx.NetworkXError):
        return []


def get_conflict_summary(conflicts: List[Conflict]) -> Dict[str, int]:
    """Get a summary count of conflicts by severity.

    Returns:
        Dict with "critical", "warning", and "total" counts.
    """
    critical = sum(1 for c in conflicts if c.severity == "critical")
    warning = sum(1 for c in conflicts if c.severity == "warning")
    return {
        "critical": critical,
        "warning": warning,
        "total": len(conflicts),
    }
