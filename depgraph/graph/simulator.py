"""Upgrade simulation engine for 'what-if' analysis."""

from __future__ import annotations

from typing import Dict, List, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from depgraph.parser.models import Package, Service, SimulationResult


def simulate_upgrade(
    services: List[Service],
    package_name: str,
    new_version: str,
) -> SimulationResult:
    """Simulate upgrading a package to a new version across all services.

    For each service that uses the package:
        1. Check if the new version satisfies the service's constraint.
        2. Classify the service as breaking or compatible.
        3. Generate an actionable recommendation.

    Args:
        services: List of all parsed services.
        package_name: Name of the package to upgrade.
        new_version: Target version string (e.g., "2.0.0").

    Returns:
        SimulationResult with impact analysis.
    """
    normalized_name = package_name.lower().replace("-", "_")

    try:
        target_version = Version(new_version)
    except InvalidVersion:
        return SimulationResult(
            package=package_name,
            new_version=new_version,
            recommendation=f"Invalid version format: {new_version}",
        )

    affected: List[str] = []
    breaking: List[Dict[str, str]] = []
    compatible: List[str] = []

    for service in services:
        pkg = service.get_package(normalized_name)
        if not pkg:
            continue

        affected.append(service.name)

        if not pkg.constraint:
            # No constraint — always compatible
            compatible.append(service.name)
            continue

        try:
            spec = SpecifierSet(pkg.constraint)
        except InvalidSpecifier:
            # Can't parse constraint — mark as needing review
            breaking.append(
                {
                    "service": service.name,
                    "current_constraint": pkg.constraint,
                    "current_version": pkg.version,
                    "reason": f"Cannot parse constraint: {pkg.constraint}",
                }
            )
            continue

        if target_version in spec:
            compatible.append(service.name)
        else:
            breaking.append(
                {
                    "service": service.name,
                    "current_constraint": pkg.constraint,
                    "current_version": pkg.version,
                    "reason": f"Version {new_version} does not satisfy {pkg.constraint}",
                }
            )

    # Generate recommendation
    recommendation = _generate_recommendation(
        package_name, new_version, affected, breaking, compatible
    )

    return SimulationResult(
        package=package_name,
        new_version=new_version,
        affected_services=affected,
        breaking_services=breaking,
        compatible_services=compatible,
        recommendation=recommendation,
    )


def suggest_upgrade_path(
    services: List[Service], package_name: str
) -> Optional[str]:
    """Find a version range that satisfies the most services.

    Collects all version constraints for a package across services and
    attempts to find the intersection.

    Args:
        services: List of all parsed services.
        package_name: Name of the package.

    Returns:
        A suggested version constraint string, or None if no common range exists.
    """
    normalized_name = package_name.lower().replace("-", "_")
    constraints: List[str] = []

    for service in services:
        pkg = service.get_package(normalized_name)
        if pkg and pkg.constraint:
            constraints.append(pkg.constraint)

    if not constraints:
        return None

    # Try to combine all constraints into one SpecifierSet
    combined = ",".join(constraints)
    try:
        combined_spec = SpecifierSet(combined)
        return str(combined_spec) if str(combined_spec) else None
    except InvalidSpecifier:
        return None


def _generate_recommendation(
    package_name: str,
    new_version: str,
    affected: List[str],
    breaking: List[Dict[str, str]],
    compatible: List[str],
) -> str:
    """Generate a human-readable upgrade recommendation."""
    if not affected:
        return f"No services use {package_name}. Upgrade has no impact."

    if not breaking:
        return (
            f"[SAFE] Safe to upgrade! All {len(compatible)} service(s) using "
            f"{package_name} are compatible with version {new_version}."
        )

    if not compatible:
        return (
            f"[BREAKING] Breaking change! All {len(breaking)} service(s) using "
            f"{package_name} would break with version {new_version}. "
            f"Update version constraints in all services before upgrading."
        )

    return (
        f"[PARTIAL] Partial compatibility. {len(compatible)} service(s) compatible, "
        f"{len(breaking)} service(s) would break. Update constraints in "
        f"breaking services: {', '.join(b['service'] for b in breaking)}."
    )
