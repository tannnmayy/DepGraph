"""JSON export for CI/CD integration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from depgraph.parser.models import Conflict, Service


def export_json(
    services: List[Service],
    conflicts: List[Conflict],
    output_path: Optional[str] = None,
    workspace_path: str = "",
) -> str:
    """Export scan results as structured JSON.

    The JSON structure is designed for CI/CD integration:
        - Machine-readable conflict data
        - Timestamp for audit trail
        - Summary statistics for quick checks

    Args:
        services: List of scanned services.
        conflicts: List of detected conflicts.
        output_path: Optional file path to write JSON to.
        workspace_path: Path to the scanned workspace.

    Returns:
        JSON string of the scan results.
    """
    critical = sum(1 for c in conflicts if c.severity == "critical")
    warnings = sum(1 for c in conflicts if c.severity == "warning")

    result: Dict[str, Any] = {
        "depgraph_version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": workspace_path,
        "summary": {
            "services_scanned": len(services),
            "total_conflicts": len(conflicts),
            "critical": critical,
            "warnings": warnings,
            "status": "fail" if critical > 0 else ("warn" if warnings > 0 else "pass"),
        },
        "services": [
            {
                "name": s.name,
                "path": s.path,
                "python_version": s.python_version,
                "dependency_count": len(s.dependencies),
                "direct_dependencies": [
                    {
                        "name": d.name,
                        "version": d.version,
                        "constraint": d.constraint,
                    }
                    for d in s.direct_dependencies
                ],
            }
            for s in services
        ],
        "conflicts": [
            {
                "package": c.package_name,
                "severity": c.severity,
                "services": c.services,
                "versions": c.versions,
                "explanation": c.explanation,
                "transitive_chain": c.transitive_chain,
            }
            for c in conflicts
        ],
    }

    json_str = json.dumps(result, indent=2, ensure_ascii=False)

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_str, encoding="utf-8")

    return json_str
