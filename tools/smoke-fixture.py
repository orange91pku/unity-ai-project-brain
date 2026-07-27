#!/usr/bin/env python3
"""Build and query the public synthetic Unity fixture."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from project_brain.context_api import ContextService
from project_brain.unity_graph import build_graph, validate_graph


def main() -> int:
    repository = REPOSITORY_ROOT
    fixture = repository / "examples" / "unity-project" / "fixture"
    unity_project = fixture / "UnityProject"
    policy = repository / "config" / "index-policy.example.json"
    catalog = fixture / "symbol-catalog.json"

    with tempfile.TemporaryDirectory() as temporary_directory:
        graph = Path(temporary_directory) / "unity-graph.sqlite"
        stats = build_graph(
            fixture,
            unity_project,
            policy,
            graph,
            catalog,
        )
        validation = validate_graph(graph)
        service = ContextService(
            graph,
            None,
            fixture,
            unity_project,
        )
        resolved = service.resolve("Player")
        uses = service.uses("roslyn:player")

        checks = {
            "localAssets": stats["localAssets"] == 3,
            "scriptLinks": stats["scriptLinks"] == 1,
            "resolvedLocalScriptLinks":
                stats["resolvedLocalScriptLinks"] == 1,
            "prefabSourceLinks": stats["prefabSourceLinks"] == 1,
            "gameObjectParentLinks": stats["gameObjectParentLinks"] == 1,
            "codeSymbols": stats["codeSymbols"] == 2,
            "resolvedComponentSymbolLinks":
                stats["resolvedComponentSymbolLinks"] == 1,
            "graphIntegrity": validation["passed"],
            "resolve": any(
                item["identityId"] == "roslyn:player"
                for item in resolved["result"]["items"]
            ),
            "uses": bool(uses["result"]["uses"]),
        }
        result = {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
            "graphFingerprint": stats["graphFingerprint"],
        }
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
