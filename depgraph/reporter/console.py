"""Rich-powered console output for scan results and simulations."""

from __future__ import annotations

import io
import os
import sys
from typing import Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from depgraph.parser.models import Conflict, Service, SimulationResult


# Force UTF-8 on Windows to support Rich box-drawing characters
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except AttributeError:
        pass

console = Console()


def print_scan_results(
    services: List[Service],
    conflicts: List[Conflict],
) -> None:
    """Print a complete scan report to the terminal.

    Includes:
        - Header panel with scan summary
        - Service list with dependency counts
        - Conflict details table (if any)
        - Summary with actionable next steps
    """
    # ── Header Panel ──
    _print_header(services, conflicts)

    # ── Services Found ──
    _print_services(services)

    # ── Conflicts ──
    if conflicts:
        _print_conflicts(conflicts)
    else:
        console.print()
        console.print(
            Panel(
                "[bold green][PASS] No dependency conflicts detected![/]\n\n"
                "All services have compatible dependency versions.",
                title="[bold green]All Clear[/]",
                border_style="green",
                padding=(1, 2),
            )
        )

    console.print()


def print_simulation_results(result: SimulationResult) -> None:
    """Print upgrade simulation results to the terminal."""
    # Header
    console.print()
    title = f"Upgrade Simulation: {result.package} -> {result.new_version}"
    console.print(
        Panel(
            title,
            style="bold cyan",
            padding=(0, 2),
        )
    )

    if not result.affected_services:
        console.print(
            f"\n  [dim]No services use [bold]{result.package}[/bold]. "
            f"No impact from this upgrade.[/dim]\n"
        )
        return

    # Impact table
    table = Table(
        title="Impact Analysis",
        show_header=True,
        header_style="bold",
        border_style="blue",
        padding=(0, 1),
    )
    table.add_column("Service", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Current Constraint")
    table.add_column("Details")

    for service_name in result.compatible_services:
        table.add_row(
            service_name,
            "[bold green][OK] Compatible[/]",
            _get_constraint_for_service(service_name, result),
            "No changes needed",
        )

    for breaking in result.breaking_services:
        table.add_row(
            breaking["service"],
            "[bold red][!!] Breaking[/]",
            breaking.get("current_constraint", ""),
            breaking.get("reason", ""),
        )

    console.print()
    console.print(table)

    # Recommendation
    console.print()
    if result.breaking_services:
        rec_style = "yellow" if result.compatible_services else "red"
    else:
        rec_style = "green"

    console.print(
        Panel(
            result.recommendation,
            title="[bold]Recommendation[/]",
            border_style=rec_style,
            padding=(1, 2),
        )
    )
    console.print()


def _print_header(services: List[Service], conflicts: List[Conflict]) -> None:
    """Print the scan header panel."""
    critical = sum(1 for c in conflicts if c.severity == "critical")
    warnings = sum(1 for c in conflicts if c.severity == "warning")

    if critical > 0:
        status_color = "red"
        status_icon = "[bold red][!!][/bold red]"
        status_text = "CONFLICTS DETECTED"
    elif warnings > 0:
        status_color = "yellow"
        status_icon = "[bold yellow][!][/bold yellow]"
        status_text = "WARNINGS FOUND"
    else:
        status_color = "green"
        status_icon = "[bold green][OK][/bold green]"
        status_text = "ALL CLEAR"

    header_text = (
        f"{status_icon} [bold]{status_text}[/bold]\n\n"
        f"  Services scanned:  [bold]{len(services)}[/bold]\n"
        f"  Total conflicts:   [bold]{len(conflicts)}[/bold]\n"
        f"  Critical:          [bold red]{critical}[/bold red]\n"
        f"  Warnings:          [bold yellow]{warnings}[/bold yellow]"
    )

    console.print()
    console.print(
        Panel(
            header_text,
            title="[bold]DepGraph Scan Results[/]",
            border_style=status_color,
            padding=(1, 2),
        )
    )


def _print_services(services: List[Service]) -> None:
    """Print the list of discovered services."""
    table = Table(
        title="Discovered Services",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Service", style="bold")
    table.add_column("Direct Deps", justify="center")
    table.add_column("Path", style="dim")

    for i, service in enumerate(services, 1):
        direct = len(service.direct_dependencies)
        table.add_row(
            str(i),
            service.name,
            str(direct),
            service.path,
        )

    console.print()
    console.print(table)


def _print_conflicts(conflicts: List[Conflict]) -> None:
    """Print detailed conflict information."""
    console.print()
    console.print("[bold]Conflicts:[/bold]")
    console.print()

    for i, conflict in enumerate(conflicts, 1):
        severity_badge = (
            "[bold white on red] CRITICAL [/]"
            if conflict.severity == "critical"
            else "[bold black on yellow] WARNING [/]"
        )

        # Conflict header
        console.print(f"  {severity_badge}  [bold]{conflict.package_name}[/bold]")
        console.print()

        # Version table for this conflict
        table = Table(
            show_header=True,
            header_style="bold",
            border_style="red" if conflict.severity == "critical" else "yellow",
            padding=(0, 1),
            show_edge=False,
        )
        table.add_column("Service", style="bold")
        table.add_column("Version / Constraint")

        for service_name, version in conflict.versions.items():
            table.add_row(service_name, version)

        console.print(table)

        # Explanation
        console.print(f"\n  [dim]>> {conflict.explanation}[/dim]")

        # Transitive chain (if present)
        if conflict.transitive_chain:
            tree = Tree("[dim]Dependency chain:[/dim]")
            for service_name, chain in conflict.transitive_chain.items():
                branch = tree.add(f"[bold]{service_name}[/bold]")
                for step in chain:
                    branch.add(f"[dim]->[/dim] {step}")
            console.print(tree)

        if i < len(conflicts):
            console.print("\n  " + "[dim]-[/dim]" * 40 + "\n")


def _get_constraint_for_service(
    service_name: str, result: SimulationResult
) -> str:
    """Helper to get the constraint string for a service from breaking list."""
    for b in result.breaking_services:
        if b["service"] == service_name:
            return b.get("current_constraint", "")
    return "-"
