"""Tests for the conflict analyzer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from depgraph.graph.analyzer import (
    detect_circular_dependencies,
    detect_conflicts,
    find_dependency_path,
    get_conflict_summary,
)
from depgraph.graph.builder import build_dependency_graph
from depgraph.parser.models import Package, Service
from depgraph.parser.toml_parser import scan_workspace

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_monorepo"


class TestDetectConflicts:
    """Test conflict detection logic."""

    def test_detects_version_conflict(self):
        """Two services pinning different exact versions = critical conflict."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint="==2.28.0"),
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

        conflicts = detect_conflicts(services)
        assert len(conflicts) == 1
        assert conflicts[0].package_name == "requests"
        assert conflicts[0].severity == "critical"
        assert "svc-a" in conflicts[0].services
        assert "svc-b" in conflicts[0].services

    def test_no_conflict_same_version(self):
        """Two services using the same exact version = no conflict."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint="==2.28.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint="==2.28.0"),
                ],
            ),
        ]

        conflicts = detect_conflicts(services)
        assert len(conflicts) == 0

    def test_warning_on_overlapping_ranges(self):
        """Overlapping ranges with different pinned versions = warning."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint=">=2.25.0,<3.0.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="requests", version="2.30.0", constraint=">=2.28.0,<3.0.0"),
                ],
            ),
        ]

        conflicts = detect_conflicts(services)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "warning"

    def test_single_service_no_conflict(self):
        """A package used by only one service can't conflict."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint="==2.28.0"),
                ],
            ),
        ]

        conflicts = detect_conflicts(services)
        assert len(conflicts) == 0

    def test_critical_non_overlapping_ranges(self):
        """Non-overlapping ranges = critical conflict."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="numpy", version="1.22.0", constraint=">=1.21.0,<1.23.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="numpy", version="1.24.0", constraint=">=1.23.0"),
                ],
            ),
        ]

        conflicts = detect_conflicts(services)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "critical"

    def test_conflicts_sorted_by_severity(self):
        """Critical conflicts should appear before warnings."""
        services = [
            Service(
                name="svc-a",
                path="/a",
                dependencies=[
                    Package(name="requests", version="2.28.0", constraint="==2.28.0"),
                    Package(name="flask", version="2.0.0", constraint=">=2.0.0,<3.0.0"),
                ],
            ),
            Service(
                name="svc-b",
                path="/b",
                dependencies=[
                    Package(name="requests", version="2.25.1", constraint="==2.25.1"),
                    Package(name="flask", version="2.3.0", constraint=">=2.0.0,<3.0.0"),
                ],
            ),
        ]

        conflicts = detect_conflicts(services)
        if len(conflicts) >= 2:
            assert conflicts[0].severity == "critical"


class TestDetectConflictsWithFixtures:
    """Integration tests using the sample monorepo fixtures."""

    def test_fixture_scan_detects_conflicts(self):
        services = scan_workspace(str(FIXTURES_DIR))
        assert len(services) == 3

        conflicts = detect_conflicts(services)
        # Should find at least requests conflict (2.28.0 vs 2.25.1)
        assert len(conflicts) > 0

        pkg_names = {c.package_name for c in conflicts}
        assert "requests" in pkg_names

    def test_requests_conflict_is_critical(self):
        services = scan_workspace(str(FIXTURES_DIR))
        conflicts = detect_conflicts(services)

        requests_conflicts = [c for c in conflicts if c.package_name == "requests"]
        assert len(requests_conflicts) == 1
        assert requests_conflicts[0].severity == "critical"


class TestGetConflictSummary:
    """Test conflict summary generation."""

    def test_summary_counts(self):
        from depgraph.parser.models import Conflict

        conflicts = [
            Conflict(package_name="pkg-a", severity="critical"),
            Conflict(package_name="pkg-b", severity="warning"),
            Conflict(package_name="pkg-c", severity="critical"),
        ]

        summary = get_conflict_summary(conflicts)
        assert summary["critical"] == 2
        assert summary["warning"] == 1
        assert summary["total"] == 3

    def test_empty_summary(self):
        summary = get_conflict_summary([])
        assert summary["critical"] == 0
        assert summary["warning"] == 0
        assert summary["total"] == 0


class TestDetectCircularDependencies:
    """Test circular dependency detection."""

    def test_no_cycles_in_fixtures(self):
        services = scan_workspace(str(FIXTURES_DIR))
        graph = build_dependency_graph(services)
        cycles = detect_circular_dependencies(graph)
        # The fixture shouldn't have cycles
        assert len(cycles) == 0
