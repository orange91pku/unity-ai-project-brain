from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_brain.context_api import ContextService
from project_brain.evidence_store import ingest
from project_brain.unity_graph import build_graph


SCRIPT_GUID = "11111111111111111111111111111111"
PREFAB_GUID = "22222222222222222222222222222222"


class ContextApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.repository = root / "repository"
        self.unity_project = self.repository / "Unity"
        assets = self.unity_project / "Assets"
        (assets / "Scripts").mkdir(parents=True)
        self.graph = root / "graph.sqlite"
        self.evidence = root / "evidence.sqlite"
        self.policy = root / "policy.json"
        self.catalog = root / "catalog.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "test",
                    "exclude": {
                        "directoryNames": ["Library"],
                        "pathPrefixes": [],
                    },
                    "lanes": {},
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )
        (assets / "Scripts/Player.cs").write_text(
            "class Player {}\n",
            encoding="utf-8",
        )
        (assets / "Scripts/Player.cs.meta").write_text(
            f"guid: {SCRIPT_GUID}\n",
            encoding="utf-8",
        )
        (assets / "Player.prefab").write_text(
            "%YAML 1.1\n"
            "--- !u!1 &1\n"
            "GameObject:\n"
            "  m_Component:\n"
            "  - component: {fileID: 2}\n"
            "  m_Name: Player Root\n"
            "--- !u!114 &2\n"
            "MonoBehaviour:\n"
            "  m_GameObject: {fileID: 1}\n"
            f"  m_Script: {{fileID: 11500000, guid: {SCRIPT_GUID}, type: 3}}\n",
            encoding="utf-8",
        )
        (assets / "Player.prefab.meta").write_text(
            f"guid: {PREFAB_GUID}\n",
            encoding="utf-8",
        )
        self.catalog.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "keyFormat": "test",
                    "roslynVersion": "test",
                    "symbols": [
                        {
                            "symbolId": "roslyn:player",
                            "roslynKey": "T:Player",
                            "documentationId": "T:Player",
                            "kind": "Type",
                            "subkind": "Class",
                            "assemblyName": "Assembly-CSharp",
                            "name": "Player",
                            "qualifiedName": "Player",
                            "namespaceName": "",
                            "metadataName": "Player",
                            "containingSymbolId": None,
                            "containingRoslynKey": None,
                            "containingTypeMetadataName": None,
                            "accessibility": "Public",
                            "isStatic": False,
                            "isScriptFile": True,
                            "isUnityObject": True,
                            "isMonoBehaviour": True,
                            "isScriptableObject": False,
                            "isPartial": False,
                            "baseTypes": ["UnityEngine.MonoBehaviour"],
                            "declarations": [
                                {
                                    "projectRelativePath": "Assets/Scripts/Player.cs",
                                    "line": 1,
                                    "column": 1,
                                    "spanStart": 0,
                                    "spanLength": 15,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init"],
            cwd=self.repository,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@project-brain.invalid"],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Project Brain Test"],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=self.repository,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.graph,
            self.catalog,
        )
        ingest(
            self.evidence,
            "runtime",
            "runtime://test/session",
            [
                {
                    "claim": "player.spawned",
                    "identityId": "roslyn:player",
                    "confidence": 0.9,
                }
            ],
        )
        self.service = ContextService(
            self.graph,
            self.evidence,
            self.repository,
            self.unity_project,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_resolve_context_impact_and_history_share_identity(self) -> None:
        resolved = self.service.resolve("Player")
        player = resolved["result"]["items"][0]
        context = self.service.context("roslyn:player", depth=2)
        impact = self.service.impact("roslyn:player", "rename")
        history = self.service.history("roslyn:player")

        self.assertEqual("roslyn:player", player["identityId"])
        self.assertTrue(
            any(
                item["claim"] == "player.spawned"
                for item in context["result"]["evidence"]
            )
        )
        self.assertIn(
            "unity-missing-script",
            impact["result"]["requiredGates"],
        )
        self.assertEqual(
            "Unity/Assets/Scripts/Player.cs",
            history["result"]["path"],
        )
        self.assertEqual(1, len(history["result"]["commits"]))


if __name__ == "__main__":
    unittest.main()
