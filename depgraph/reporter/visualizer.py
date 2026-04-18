"""D3.js interactive dependency graph visualizer."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx

from depgraph.graph.builder import export_graph_data
from depgraph.parser.models import Conflict


def generate_visualization(
    graph: nx.DiGraph,
    conflicts: List[Conflict],
    output_path: str = "depgraph_report.html",
    auto_open: bool = True,
) -> str:
    """Generate a self-contained HTML file with D3.js force-directed graph.

    Features:
        - Service nodes: large colored circles
        - Package nodes: smaller circles, colored by conflict status
        - Conflict edges: highlighted in red
        - Interactive: zoom, pan, hover for details, click to highlight chains

    Args:
        graph: NetworkX dependency graph.
        conflicts: List of detected conflicts (to highlight in visualization).
        output_path: Where to save the HTML file.
        auto_open: Whether to open the file in the default browser.

    Returns:
        Absolute path to the generated HTML file.
    """
    graph_data = export_graph_data(graph)

    # Mark conflicting packages
    conflict_packages = {c.package_name for c in conflicts}
    conflict_severities = {
        c.package_name: c.severity for c in conflicts
    }

    for node in graph_data["nodes"]:
        node["is_conflict"] = node["id"] in conflict_packages
        node["conflict_severity"] = conflict_severities.get(node["id"], "")

    # Mark conflict edges
    for link in graph_data["links"]:
        link["is_conflict"] = link["target"] in conflict_packages

    html_content = _build_html(graph_data)

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")

    if auto_open:
        webbrowser.open(f"file://{output}")

    return str(output)


def _build_html(graph_data: Dict[str, Any]) -> str:
    """Build the complete self-contained HTML with embedded D3.js."""
    graph_json = json.dumps(graph_data, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DepGraph — Dependency Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            overflow: hidden;
        }}

        #header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 100;
            background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
            border-bottom: 1px solid #21262d;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            backdrop-filter: blur(10px);
        }}

        #header h1 {{
            font-size: 18px;
            font-weight: 600;
            background: linear-gradient(135deg, #58a6ff, #bc8cff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .legend {{
            display: flex;
            gap: 16px;
            font-size: 12px;
            align-items: center;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}

        #graph {{
            width: 100vw;
            height: 100vh;
            padding-top: 50px;
        }}

        .tooltip {{
            position: absolute;
            padding: 10px 14px;
            background: #1c2128;
            border: 1px solid #30363d;
            border-radius: 8px;
            font-size: 12px;
            color: #c9d1d9;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.15s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            max-width: 300px;
            z-index: 200;
        }}

        .tooltip .pkg-name {{
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 4px;
        }}

        .tooltip .type-badge {{
            display: inline-block;
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 6px;
        }}

        .tooltip .type-service {{ background: #1f6feb33; color: #58a6ff; }}
        .tooltip .type-package {{ background: #23883533; color: #3fb950; }}
        .tooltip .type-conflict {{ background: #f8514933; color: #f85149; }}

        .link {{
            stroke-opacity: 0.3;
        }}

        .link.conflict {{
            stroke-opacity: 0.7;
        }}

        .node-label {{
            font-size: 11px;
            fill: #8b949e;
            pointer-events: none;
            text-anchor: middle;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>⬡ DepGraph — Dependency Visualization</h1>
        <div class="legend">
            <div class="legend-item">
                <div class="legend-dot" style="background: #58a6ff;"></div>
                <span>Service</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #3fb950;"></div>
                <span>Package</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #f85149;"></div>
                <span>Critical Conflict</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background: #d29922;"></div>
                <span>Warning</span>
            </div>
        </div>
    </div>

    <div id="graph"></div>
    <div class="tooltip" id="tooltip"></div>

    <script>
    const graphData = {graph_json};

    const width = window.innerWidth;
    const height = window.innerHeight;

    const svg = d3.select("#graph")
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    const g = svg.append("g");

    // Zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on("zoom", (event) => g.attr("transform", event.transform));

    svg.call(zoom);

    // Force simulation
    const simulation = d3.forceSimulation(graphData.nodes)
        .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(d => getNodeRadius(d) + 5));

    // Draw links
    const link = g.append("g")
        .selectAll("line")
        .data(graphData.links)
        .join("line")
        .attr("class", d => "link" + (d.is_conflict ? " conflict" : ""))
        .attr("stroke", d => d.is_conflict ? "#f85149" : "#21262d")
        .attr("stroke-width", d => d.is_conflict ? 2 : 1);

    // Draw nodes
    const node = g.append("g")
        .selectAll("circle")
        .data(graphData.nodes)
        .join("circle")
        .attr("r", d => getNodeRadius(d))
        .attr("fill", d => getNodeColor(d))
        .attr("stroke", d => d.is_conflict ? "#f85149" : "transparent")
        .attr("stroke-width", d => d.is_conflict ? 2 : 0)
        .style("cursor", "pointer")
        .call(d3.drag()
            .on("start", dragStarted)
            .on("drag", dragged)
            .on("end", dragEnded));

    // Node labels
    const label = g.append("g")
        .selectAll("text")
        .data(graphData.nodes)
        .join("text")
        .attr("class", "node-label")
        .attr("dy", d => getNodeRadius(d) + 14)
        .text(d => d.id);

    // Tooltip
    const tooltip = d3.select("#tooltip");

    node.on("mouseover", (event, d) => {{
        tooltip.style("opacity", 1);
        let content = `<div class="pkg-name">${{d.id}}</div>`;

        if (d.type === "service") {{
            content += `<span class="type-badge type-service">Service</span>`;
            content += `<div>Dependencies: ${{d.dep_count || 0}}</div>`;
        }} else if (d.is_conflict) {{
            content += `<span class="type-badge type-conflict">${{d.conflict_severity}}</span>`;
            if (d.versions) {{
                content += `<div style="margin-top:6px">`;
                for (const [svc, ver] of Object.entries(d.versions)) {{
                    content += `<div>${{svc}}: <code>${{ver}}</code></div>`;
                }}
                content += `</div>`;
            }}
        }} else {{
            content += `<span class="type-badge type-package">Package</span>`;
            if (d.versions && Object.keys(d.versions).length) {{
                content += `<div style="margin-top:6px">`;
                for (const [svc, ver] of Object.entries(d.versions)) {{
                    content += `<div>${{svc}}: <code>${{ver}}</code></div>`;
                }}
                content += `</div>`;
            }}
        }}

        tooltip.html(content);
    }})
    .on("mousemove", (event) => {{
        tooltip
            .style("left", (event.pageX + 15) + "px")
            .style("top", (event.pageY - 10) + "px");
    }})
    .on("mouseout", () => {{
        tooltip.style("opacity", 0);
    }});

    // Click to highlight connected nodes
    node.on("click", (event, d) => {{
        const connected = new Set();
        connected.add(d.id);
        graphData.links.forEach(l => {{
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            if (sourceId === d.id) connected.add(targetId);
            if (targetId === d.id) connected.add(sourceId);
        }});

        node.style("opacity", n => connected.has(n.id) ? 1 : 0.15);
        link.style("opacity", l => {{
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            return connected.has(sourceId) && connected.has(targetId) ? 0.8 : 0.05;
        }});
        label.style("opacity", n => connected.has(n.id) ? 1 : 0.1);
    }});

    // Double-click to reset
    svg.on("dblclick.zoom", () => {{
        node.style("opacity", 1);
        link.style("opacity", d => d.is_conflict ? 0.7 : 0.3);
        label.style("opacity", 1);
    }});

    // Tick function
    simulation.on("tick", () => {{
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("cx", d => d.x)
            .attr("cy", d => d.y);

        label
            .attr("x", d => d.x)
            .attr("y", d => d.y);
    }});

    function getNodeRadius(d) {{
        if (d.type === "service") return 18;
        if (d.is_conflict) return 12;
        return 7;
    }}

    function getNodeColor(d) {{
        if (d.type === "service") return "#58a6ff";
        if (d.is_conflict && d.conflict_severity === "critical") return "#f85149";
        if (d.is_conflict && d.conflict_severity === "warning") return "#d29922";
        return "#3fb950";
    }}

    function dragStarted(event, d) {{
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }}

    function dragged(event, d) {{
        d.fx = event.x;
        d.fy = event.y;
    }}

    function dragEnded(event, d) {{
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }}
    </script>
</body>
</html>"""
