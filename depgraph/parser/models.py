"""Data models for DepGraph dependency analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Package:
    """Represents a Python package dependency.

    Attributes:
        name: Normalized package name (e.g., "requests").
        version: Exact resolved version (e.g., "2.28.0"). Empty if only constraint is known.
        constraint: Version constraint string (e.g., ">=2.28.0,<3.0").
        source: Whether this is a "direct" or "transitive" dependency.
        depends_on: List of package names this package depends on (transitive chain).
    """

    name: str
    version: str = ""
    constraint: str = ""
    source: str = "direct"
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Normalize package name: lowercase, replace hyphens with underscores
        self.name = self.name.lower().replace("-", "_")


@dataclass
class Service:
    """Represents a microservice in the monorepo.

    Attributes:
        name: Service name (from pyproject.toml or directory name).
        path: Absolute path to the service directory.
        python_version: Python version constraint for the service.
        dependencies: List of direct and transitive Package dependencies.
    """

    name: str
    path: str
    python_version: str = ""
    dependencies: List[Package] = field(default_factory=list)

    def get_package(self, package_name: str) -> Optional[Package]:
        """Find a package by name in this service's dependencies."""
        normalized = package_name.lower().replace("-", "_")
        for dep in self.dependencies:
            if dep.name == normalized:
                return dep
        return None

    @property
    def direct_dependencies(self) -> List[Package]:
        """Return only direct dependencies."""
        return [d for d in self.dependencies if d.source == "direct"]

    @property
    def transitive_dependencies(self) -> List[Package]:
        """Return only transitive dependencies."""
        return [d for d in self.dependencies if d.source == "transitive"]


@dataclass
class Conflict:
    """Represents a dependency version conflict between services.

    Attributes:
        package_name: The conflicting package name.
        services: List of service names involved in the conflict.
        versions: Mapping of service_name -> version or constraint string.
        severity: "critical" (no version overlap) or "warning" (versions differ but overlap).
        explanation: Human-readable explanation of the conflict.
        transitive_chain: Optional trace showing how the conflict arises through transitive deps.
    """

    package_name: str
    services: List[str] = field(default_factory=list)
    versions: Dict[str, str] = field(default_factory=dict)
    severity: str = "warning"
    explanation: str = ""
    transitive_chain: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SimulationResult:
    """Result of simulating a package upgrade.

    Attributes:
        package: The package being upgraded.
        new_version: The target version.
        affected_services: Services that use this package.
        breaking_services: Services whose constraints are violated by the new version.
        compatible_services: Services compatible with the new version.
        recommendation: Human-readable upgrade recommendation.
    """

    package: str
    new_version: str
    affected_services: List[str] = field(default_factory=list)
    breaking_services: List[Dict[str, str]] = field(default_factory=list)
    compatible_services: List[str] = field(default_factory=list)
    recommendation: str = ""
