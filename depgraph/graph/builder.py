"""Build NetworkX directed graph from parsed service dependencies."""

from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from depgraph.parser.models import Package, Service


def build_dependency_graph(services: List[Service]) -> nx.DiGraph:
    """Build a directed dependency graph from a list of services.

    Graph structure:
        - Service nodes: type="service", with service metadata
        - Package nodes: keyed as "package_name" (unique per package),
          type="package", with version info per service
        - Edges: service -> package (direct deps),
                 package -> package (transitive deps from lockfiles)

    Args:
        services: List of parsed Service objects.

    Returns:
        A NetworkX DiGraph representing all dependency relationships.
    """
    graph = nx.DiGraph()

    for service in services:
        # Add service node
        graph.add_node(
            service.name,
            type="service",
            path=service.path,
            python_version=service.python_version,
            dep_count=len(service.dependencies),
        )

        for pkg in service.dependencies:
            pkg_node = pkg.name

            # Add or update package node
            if graph.has_node(pkg_node):
                # Append this service's version info
                node_data = graph.nodes[pkg_node]
                versions = node_data.get("versions", {})
                versions[service.name] = pkg.version or pkg.constraint
                node_data["versions"] = versions
            else:
                graph.add_node(
                    pkg_node,
                    type="package",
                    versions={service.name: pkg.version or pkg.constraint},
                )

            # Add edge: service -> package
            graph.add_edge(
                service.name,
                pkg_node,
                relationship="depends_on",
                constraint=pkg.constraint,
                version=pkg.version,
                source=pkg.source,
            )

            # Add transitive dependency edges
            for dep_name in pkg.depends_on:
                dep_node = dep_name.lower().replace("-", "_")
                if not graph.has_node(dep_node):
                    graph.add_node(dep_node, type="package", versions={})
                graph.add_edge(
                    pkg_node,
                    dep_node,
                    relationship="requires",
                    source="transitive",
                )

    return graph


def export_graph_data(graph: nx.DiGraph) -> Dict[str, Any]:
    """Export graph to a JSON-serializable dictionary for D3.js visualization.

    Returns:
        Dict with "nodes" and "links" lists suitable for D3 force-directed graph.
    """
    nodes = []
    for node_id, data in graph.nodes(data=True):
        node_entry = {
            "id": node_id,
            "type": data.get("type", "unknown"),
        }
        if data.get("type") == "service":
            node_entry["dep_count"] = data.get("dep_count", 0)
            node_entry["path"] = data.get("path", "")
        elif data.get("type") == "package":
            node_entry["versions"] = data.get("versions", {})

        nodes.append(node_entry)

    links = []
    for source, target, data in graph.edges(data=True):
        links.append(
            {
                "source": source,
                "target": target,
                "relationship": data.get("relationship", ""),
                "constraint": data.get("constraint", ""),
                "version": data.get("version", ""),
            }
        )

    return {"nodes": nodes, "links": links}


def get_dependency_chain(
    graph: nx.DiGraph, source: str, target: str
) -> List[List[str]]:
    """Find all dependency paths from source to target in the graph.

    Args:
        graph: The dependency graph.
        source: Source node (typically a service name).
        target: Target node (typically a package name).

    Returns:
        List of paths (each path is a list of node names).
    """
    target_normalized = target.lower().replace("-", "_")

    try:
        return list(nx.all_simple_paths(graph, source, target_normalized))
    except (nx.NodeNotFound, nx.NetworkXError):
        return []
