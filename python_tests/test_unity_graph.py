from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from project_brain.unity_graph import build_graph, validate_graph


SCRIPT_GUID = "11111111111111111111111111111111"
PREFAB_GUID = "22222222222222222222222222222222"
SCENE_GUID = "33333333333333333333333333333333"


class UnityGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.repository = temporary_root / "repository"
        self.unity_project = self.repository / "Unity"
        self.assets = self.unity_project / "Assets"
        self.assets.mkdir(parents=True)
        self.database = temporary_root / "graph.sqlite"
        self.catalog = temporary_root / "symbol-catalog.json"
        self.policy = temporary_root / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "test",
                    "exclude": {
                        "directoryNames": ["Library", "Temp"],
                        "pathPrefixes": [],
                    },
                    "lanes": {},
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        path = self.unity_project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def seed_project(self) -> None:
        self.write("Assets/Scripts/Player.cs", "class Player {}")
        self.write(
            "Assets/Scripts/Player.cs.meta",
            f"fileFormatVersion: 2\nguid: {SCRIPT_GUID}\n",
        )
        self.write(
            "Assets/Player.prefab.meta",
            f"fileFormatVersion: 2\nguid: {PREFAB_GUID}\n",
        )
        self.write(
            "Assets/Player.prefab",
            f"""%YAML 1.1
--- !u!1 &1
GameObject:
  m_Component:
  - component: {{fileID: 2}}
  - component: {{fileID: 3}}
  m_Name: Player Root
--- !u!4 &2
Transform:
  m_GameObject: {{fileID: 1}}
  m_Father: {{fileID: 0}}
--- !u!114 &3
MonoBehaviour:
  m_GameObject: {{fileID: 1}}
  m_Script: {{fileID: 11500000, guid: {SCRIPT_GUID}, type: 3}}
  m_Name:
--- !u!1 &4
GameObject:
  m_Component:
  - component: {{fileID: 5}}
  m_Name: Child
--- !u!4 &5
Transform:
  m_GameObject: {{fileID: 4}}
  m_Father: {{fileID: 2}}
""",
        )
        self.write(
            "Assets/Main.unity.meta",
            f"fileFormatVersion: 2\nguid: {SCENE_GUID}\n",
        )
        self.write(
            "Assets/Main.unity",
            f"""%YAML 1.1
--- !u!1001 &20
PrefabInstance:
  m_SourcePrefab: {{fileID: 100100000, guid: {PREFAB_GUID}, type: 3}}
--- !u!1 &10 stripped
GameObject:
  m_CorrespondingSourceObject: {{fileID: 1, guid: {PREFAB_GUID}, type: 3}}
  m_PrefabInstance: {{fileID: 20}}
  m_Name: Player Instance
""",
        )
        self.catalog.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "keyFormat": "roslyn-public-semantic-v1",
                    "roslynVersion": "test",
                    "symbols": [
                        {
                            "symbolId": "roslyn:player",
                            "roslynKey": "doc-v1:Assembly-CSharp:T:Player",
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
                            "baseTypes": ["global::UnityEngine.MonoBehaviour"],
                            "declarations": [
                                {
                                    "projectRelativePath": "Assets/Scripts/Player.cs",
                                    "line": 1,
                                    "column": 1,
                                    "spanStart": 0,
                                    "spanLength": 15,
                                }
                            ],
                        },
                        {
                            "symbolId": "roslyn:move",
                            "roslynKey": "doc-v1:Assembly-CSharp:M:Player.Move",
                            "documentationId": "M:Player.Move",
                            "kind": "Method",
                            "subkind": "Ordinary",
                            "assemblyName": "Assembly-CSharp",
                            "name": "Move",
                            "qualifiedName": "Player.Move()",
                            "namespaceName": "",
                            "metadataName": None,
                            "containingSymbolId": "roslyn:player",
                            "containingRoslynKey": "doc-v1:Assembly-CSharp:T:Player",
                            "containingTypeMetadataName": "Player",
                            "accessibility": "Public",
                            "isStatic": False,
                            "isScriptFile": False,
                            "isUnityObject": True,
                            "isMonoBehaviour": True,
                            "isScriptableObject": False,
                            "isPartial": False,
                            "baseTypes": [],
                            "declarations": [
                                {
                                    "projectRelativePath": "Assets/Scripts/Player.cs",
                                    "line": 1,
                                    "column": 1,
                                    "spanStart": 0,
                                    "spanLength": 4,
                                }
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_builds_asset_component_script_prefab_and_hierarchy_links(self) -> None:
        self.seed_project()

        stats = build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.database,
            self.catalog,
        )

        self.assertEqual(3, stats["localAssets"])
        self.assertEqual(7, stats["objects"])
        self.assertEqual(1, stats["scriptLinks"])
        self.assertEqual(1, stats["resolvedLocalScriptLinks"])
        self.assertEqual(1, stats["prefabSourceLinks"])
        self.assertEqual(1, stats["gameObjectParentLinks"])
        self.assertEqual(2, stats["codeSymbols"])
        self.assertEqual(1, stats["resolvedComponentSymbolLinks"])
        self.assertEqual(0, stats["unresolvedLocalComponentScriptLinks"])
        self.assertEqual(64, len(stats["graphFingerprint"]))

        connection = sqlite3.connect(self.database)
        try:
            relations = {
                row[0]
                for row in connection.execute("SELECT DISTINCT relation FROM edges")
            }
            script_path = connection.execute(
                "SELECT path FROM assets WHERE guid = ?", (SCRIPT_GUID,)
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual("Assets/Scripts/Player.cs", script_path)
        self.assertIn("GAME_OBJECT_HAS_COMPONENT", relations)
        self.assertIn("COMPONENT_USES_SCRIPT", relations)
        self.assertIn("PREFAB_INSTANCE_SOURCE", relations)
        self.assertIn("CORRESPONDS_TO_SOURCE_OBJECT", relations)
        self.assertIn("GAME_OBJECT_PARENT", relations)

        second_database = self.database.with_name("graph-second.sqlite")
        second_stats = build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            second_database,
            self.catalog,
        )
        self.assertEqual(
            stats["graphFingerprint"], second_stats["graphFingerprint"]
        )
        self.assertTrue(validate_graph(self.database)["passed"])

    def test_excludes_nested_generated_directories(self) -> None:
        self.write(
            "Assets/Library/Noise.prefab.meta",
            "guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
        )
        self.write(
            "Assets/Library/Noise.prefab",
            "--- !u!1 &1\nGameObject:\n  m_Name: Noise\n",
        )

        stats = build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.database,
        )

        self.assertEqual(0, stats["assets"])
        self.assertEqual(0, stats["objects"])


if __name__ == "__main__":
    unittest.main()
