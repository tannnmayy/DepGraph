"""Tests for the graph builder module."""

from __future__ import annotations

from pathlib import Path

import pytest

from depgraph.graph.builder import build_dependency_graph, export_graph_data, get_dependency_chain
from depgraph.parser.models import Package, Service


def _make_services() -> list[Service]:
    """Create test services with known dependencies."""
    return [
        Service(
            name="service-a",
            path="/repo/service-a",
            dependencies=[
                Package(name="requests", version="2.28.0", constraint="==2.28.0", source="direct"),
                Package(name="pandas", version="1.5.3", constraint="==1.5.3", source="direct",
                        depends_on=["numpy"]),
            ],
        ),
        Service(
            name="service-b",
            path="/repo/service-b",
            dependencies=[
                Package(name="requests", version="2.25.1", constraint="==2.25.1", source="direct"),
                Package(name="flask", version="2.3.0", constraint=">=2.3.0", source="direct"),
            ],
        ),
    ]


class TestBuildDependencyGraph:
    """Test graph construction."""

    def test_graph_has_service_nodes(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        assert "service-a" in graph.nodes
        assert "service-b" in graph.nodes
        assert graph.nodes["service-a"]["type"] == "service"

    def test_graph_has_package_nodes(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        assert "requests" in graph.nodes
        assert "pandas" in graph.nodes
        assert "flask" in graph.nodes
        assert graph.nodes["requests"]["type"] == "package"

    def test_graph_has_edges(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        # service -> package edges
        assert graph.has_edge("service-a", "requests")
        assert graph.has_edge("service-a", "pandas")
        assert graph.has_edge("service-b", "requests")
        assert graph.has_edge("service-b", "flask")

    def test_transitive_edges(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        # pandas -> numpy (transitive)
        assert graph.has_edge("pandas", "numpy")

    def test_package_versions_tracked(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        versions = graph.nodes["requests"]["versions"]
        assert versions["service-a"] == "2.28.0"
        assert versions["service-b"] == "2.25.1"

    def test_empty_services(self):
        graph = build_dependency_graph([])
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0


class TestExportGraphData:
    """Test graph serialization for D3.js."""

    def test_export_structure(self):
        services = _make_services()
        graph = build_dependency_graph(services)
        data = export_graph_data(graph)

        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) > 0
        assert len(data["links"]) > 0

    def test_node_types(self):
        services = _make_services()
        graph = build_dependency_graph(services)
        data = export_graph_data(graph)

        service_nodes = [n for n in data["nodes"] if n["type"] == "service"]
        package_nodes = [n for n in data["nodes"] if n["type"] == "package"]

        assert len(service_nodes) == 2
        assert len(package_nodes) >= 3  # requests, pandas, flask, numpy


class TestGetDependencyChain:
    """Test path finding in the graph."""

    def test_direct_path(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        paths = get_dependency_chain(graph, "service-a", "requests")
        assert len(paths) >= 1
        assert paths[0] == ["service-a", "requests"]

    def test_transitive_path(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        paths = get_dependency_chain(graph, "service-a", "numpy")
        assert len(paths) >= 1
        # service-a -> pandas -> numpy
        assert ["service-a", "pandas", "numpy"] in paths

    def test_no_path(self):
        services = _make_services()
        graph = build_dependency_graph(services)

        paths = get_dependency_chain(graph, "service-b", "numpy")
        assert paths == []
