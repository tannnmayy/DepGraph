"""Graph engine for dependency analysis."""

from depgraph.graph.builder import build_dependency_graph
from depgraph.graph.analyzer import detect_conflicts, detect_circular_dependencies
from depgraph.graph.simulator import simulate_upgrade

__all__ = [
    "build_dependency_graph",
    "detect_conflicts",
    "detect_circular_dependencies",
    "simulate_upgrade",
]
