"""DepGraph CLI -- Main entry point for the dependency analyzer."""

from __future__ import annotations

import io
import os
import sys
import time

import click
from rich.console import Console

from depgraph.graph.analyzer import detect_conflicts, get_conflict_summary
from depgraph.graph.builder import build_dependency_graph
from depgraph.graph.simulator import simulate_upgrade, suggest_upgrade_path
from depgraph.parser.lock_parser import detect_and_parse_lockfile
from depgraph.parser.toml_parser import scan_workspace
from depgraph.reporter.console import print_scan_results, print_simulation_results
from depgraph.reporter.json_export import export_json
from depgraph.reporter.visualizer import generate_visualization

# Use a UTF-8 wrapper on Windows to avoid encoding errors with Rich
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="depgraph")
def cli():
    """DepGraph -- Python dependency conflict analyzer for monorepos.

    Scans your workspace to detect dependency version conflicts
    across microservices BEFORE they break your CI/CD pipeline.
    """
    pass


@cli.command()
@click.argument("workspace_path", type=click.Path(exists=True))
@click.option(
    "--format",
    "output_format",
    default="console",
    type=click.Choice(["console", "json"]),
    help="Output format.",
)
@click.option(
    "--severity",
    default="all",
    type=click.Choice(["all", "critical", "warning"]),
    help="Filter conflicts by severity.",
)
@click.option(
    "--output",
    "output_file",
    default=None,
    type=click.Path(),
    help="Write output to file (for JSON format).",
)
def scan(workspace_path, output_format, severity, output_file):
    """Scan workspace and detect dependency conflicts.

    WORKSPACE_PATH is the root directory of your monorepo.

    \b
    Examples:
        depgraph scan ./my-monorepo
        depgraph scan ./my-monorepo --format json --output report.json
        depgraph scan ./my-monorepo --severity critical
    """
    start_time = time.time()

    # Step 1: Scan workspace for services
    click.echo("  Scanning workspace for services...")
    services = scan_workspace(workspace_path)

    if not services:
        console.print("\n[yellow][!] No Python services found in workspace.[/]")
        console.print("[dim]Make sure services have pyproject.toml files with dependencies.[/dim]\n")
        sys.exit(0)

    # Step 2: Parse lockfiles for transitive dependencies
    click.echo("  Parsing lockfiles...")
    for service in services:
        lock_packages = detect_and_parse_lockfile(service.path)
        if lock_packages:
            # Merge lock packages: mark direct deps that appear in lock as having exact versions
            lock_map = {p.name: p for p in lock_packages}
            for dep in service.dependencies:
                if dep.name in lock_map:
                    lock_pkg = lock_map[dep.name]
                    dep.version = lock_pkg.version
                    dep.depends_on = lock_pkg.depends_on

            # Add transitive deps not in direct deps
            direct_names = {d.name for d in service.dependencies}
            for lock_pkg in lock_packages:
                if lock_pkg.name not in direct_names:
                    service.dependencies.append(lock_pkg)

    # Step 3: Detect conflicts
    click.echo("  Analyzing dependencies...")
    conflicts = detect_conflicts(services)

    # Apply severity filter
    if severity != "all":
        conflicts = [c for c in conflicts if c.severity == severity]

    elapsed = time.time() - start_time

    # Step 4: Output results
    if output_format == "json":
        json_str = export_json(
            services, conflicts,
            output_path=output_file,
            workspace_path=workspace_path,
        )
        if not output_file:
            click.echo(json_str)
        else:
            console.print(f"\n[green][OK] JSON report written to {output_file}[/]\n")
    else:
        print_scan_results(services, conflicts)
        console.print(f"  [dim]Completed in {elapsed:.2f}s[/dim]\n")

    # Exit code for CI/CD
    summary = get_conflict_summary(conflicts)
    if summary["critical"] > 0:
        sys.exit(2)
    elif summary["warning"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


@cli.command()
@click.argument("workspace_path", type=click.Path(exists=True))
@click.option("--package", required=True, help="Package name to upgrade.")
@click.option("--version", "target_version", required=True, help="Target version.")
def simulate(workspace_path, package, target_version):
    """Simulate upgrading a package to see its impact.

    \b
    Examples:
        depgraph simulate ./my-monorepo --package requests --version 2.31.0
        depgraph simulate ./my-monorepo --package pandas --version 2.0.0
    """
    # Scan workspace
    click.echo("  Scanning workspace...")
    services = scan_workspace(workspace_path)

    if not services:
        console.print("\n[yellow][!] No Python services found in workspace.[/]\n")
        sys.exit(0)

    # Parse lockfiles
    click.echo("  Parsing lockfiles...")
    for service in services:
        lock_packages = detect_and_parse_lockfile(service.path)
        if lock_packages:
            lock_map = {p.name: p for p in lock_packages}
            for dep in service.dependencies:
                if dep.name in lock_map:
                    dep.version = lock_map[dep.name].version

    # Run simulation
    click.echo("  Running simulation...")
    result = simulate_upgrade(services, package, target_version)

    print_simulation_results(result)

    # Suggest upgrade path
    suggestion = suggest_upgrade_path(services, package)
    if suggestion:
        console.print(
            f"  [dim]>> Suggested version range that satisfies all services: "
            f"[bold]{suggestion}[/bold][/dim]\n"
        )


@cli.command()
@click.argument("workspace_path", type=click.Path(exists=True))
@click.option(
    "--output",
    "output_file",
    default="depgraph_report.html",
    type=click.Path(),
    help="Output HTML file path.",
)
@click.option(
    "--no-open",
    is_flag=True,
    default=False,
    help="Don't auto-open the visualization in browser.",
)
def visualize(workspace_path, output_file, no_open):
    """Generate an interactive D3.js dependency graph.

    Opens a self-contained HTML file in your default browser.

    \b
    Examples:
        depgraph visualize ./my-monorepo
        depgraph visualize ./my-monorepo --output graph.html --no-open
    """
    # Scan and parse
    click.echo("  Scanning workspace...")
    services = scan_workspace(workspace_path)

    if not services:
        console.print("\n[yellow][!] No Python services found in workspace.[/]\n")
        sys.exit(0)

    click.echo("  Parsing lockfiles...")
    for service in services:
        lock_packages = detect_and_parse_lockfile(service.path)
        if lock_packages:
            lock_map = {p.name: p for p in lock_packages}
            for dep in service.dependencies:
                if dep.name in lock_map:
                    dep.version = lock_map[dep.name].version
                    dep.depends_on = lock_map[dep.name].depends_on
            direct_names = {d.name for d in service.dependencies}
            for lock_pkg in lock_packages:
                if lock_pkg.name not in direct_names:
                    service.dependencies.append(lock_pkg)

    # Build graph and detect conflicts
    click.echo("  Building dependency graph...")
    graph = build_dependency_graph(services)
    conflicts = detect_conflicts(services)

    # Generate visualization
    click.echo("  Generating visualization...")
    output = generate_visualization(
        graph, conflicts,
        output_path=output_file,
        auto_open=not no_open,
    )

    console.print(f"\n[green][OK] Visualization saved to [bold]{output}[/bold][/]")
    console.print(f"  [dim]Nodes: {graph.number_of_nodes()} | Edges: {graph.number_of_edges()}[/dim]")

    if conflicts:
        console.print(f"  [yellow][!] {len(conflicts)} conflict(s) highlighted in graph[/]")
    console.print()


if __name__ == "__main__":
    cli()
