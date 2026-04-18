"""Tests for the upgrade simulator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from depgraph.graph.simulator import simulate_upgrade, suggest_upgrade_path
from depgraph.parser.models import Package, Service
from depgraph.parser.toml_parser import scan_workspace

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_monorepo"


class TestSimulateUpgrade:
    """Test upgrade simulation logic."""

    def test_compatible_upgrade(self):
        """Upgrade within constraint range = all compatible."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint=">=2.25.0,<3.0.0"),
                ],
            ),
        ]

        result = simulate_upgrade(services, "requests", "2.31.0")
        assert len(result.affected_services) == 1
        assert len(result.breaking_services) == 0
        assert "svc-a" in result.compatible_services
        assert "Safe to upgrade" in result.recommendation

    def test_breaking_upgrade(self):
        """Upgrade beyond constraint = breaking."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint=">=2.25.0,<2.30.0"),
                ],
            ),
        ]

        result = simulate_upgrade(services, "requests", "2.31.0")
        assert len(result.breaking_services) == 1
        assert result.breaking_services[0]["service"] == "svc-a"
        assert "Breaking change" in result.recommendation or "would break" in result.recommendation

    def test_partial_compatibility(self):
        """Some services compatible, some breaking."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint=">=2.28.0,<3.0.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="requests", version="2.25.1", constraint="==2.25.1"),
                ],
            ),
        ]

        result = simulate_upgrade(services, "requests", "2.31.0")
        assert len(result.affected_services) == 2
        assert "svc-a" in result.compatible_services
        assert len(result.breaking_services) == 1
        assert "Partial" in result.recommendation or "would break" in result.recommendation

    def test_no_services_affected(self):
        """Package not used by any service."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="flask", version="2.0.0", constraint=">=2.0.0"),
                ],
            ),
        ]

        result = simulate_upgrade(services, "requests", "2.31.0")
        assert len(result.affected_services) == 0
        assert "no impact" in result.recommendation.lower() or "No services" in result.recommendation

    def test_invalid_version(self):
        """Invalid version string should be handled gracefully."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint=">=2.28.0"),
                ],
            ),
        ]

        result = simulate_upgrade(services, "requests", "not-a-version")
        assert "Invalid" in result.recommendation


class TestSimulateWithFixtures:
    """Integration tests using sample monorepo."""

    def test_simulate_requests_upgrade(self):
        services = scan_workspace(str(FIXTURES_DIR))

        result = simulate_upgrade(services, "requests", "2.28.0")

        # ml-service and auth-service have ==2.28.0, analytics-api has ==2.25.1
        assert len(result.affected_services) == 3

        # analytics-api should break (has ==2.25.1)
        breaking_names = [b["service"] for b in result.breaking_services]
        assert "analytics-api" in breaking_names

    def test_simulate_pandas_upgrade(self):
        services = scan_workspace(str(FIXTURES_DIR))

        result = simulate_upgrade(services, "pandas", "2.0.0")

        # Only ml-service has pandas pinned to ==1.5.3, analytics-api has ==2.0.0
        assert len(result.affected_services) == 2


class TestSuggestUpgradePath:
    """Test version range suggestion."""

    def test_overlapping_constraints(self):
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", constraint=">=2.25.0,<3.0.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="requests", constraint=">=2.28.0,<3.0.0"),
                ],
            ),
        ]

        suggestion = suggest_upgrade_path(services, "requests")
        assert suggestion is not None
        # Combined should be >=2.28.0,<3.0.0
        assert "2.28.0" in suggestion

    def test_no_package_found(self):
        services = [
            Service(name="svc-a", path="/a", dependencies=[]),
        ]
        suggestion = suggest_upgrade_path(services, "nonexistent")
        assert suggestion is None
