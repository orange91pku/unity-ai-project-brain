from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from project_brain.unity_graph import build_graph
from project_brain.visual_context import SCHEMA, export_visual_context


TEXTURE_GUID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PREFAB_GUID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class VisualContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.unity_project = self.repository / "Unity"
        self.assets = self.unity_project / "Assets"
        self.assets.mkdir(parents=True)
        self.database = Path(self.temporary.name) / "graph.sqlite3"
        self.policy = Path(self.temporary.name) / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "visual-context-test",
                    "exclude": {"directoryNames": [], "pathPrefixes": []},
                    "lanes": {},
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative_path: str, content: str | bytes) -> None:
        path = self.unity_project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    def seed(self) -> bytes:
        texture = b"synthetic-png-content"
        self.write("Assets/UI/icon.png", texture)
        self.write(
            "Assets/UI/icon.png.meta",
            f"fileFormatVersion: 2\nguid: {TEXTURE_GUID}\n",
        )
        self.write(
            "Assets/UI/Panel.prefab.meta",
            f"fileFormatVersion: 2\nguid: {PREFAB_GUID}\n",
        )
        self.write(
            "Assets/UI/Panel.prefab",
            f"""%YAML 1.1
--- !u!1 &1
GameObject:
  m_Component:
  - component: {{fileID: 2}}
  m_Name: Canvas
--- !u!4 &2
Transform:
  m_GameObject: {{fileID: 1}}
  m_Father: {{fileID: 0}}
--- !u!1 &3
GameObject:
  m_Component:
  - component: {{fileID: 4}}
  - component: {{fileID: 5}}
  m_Name: Icon
--- !u!4 &4
Transform:
  m_GameObject: {{fileID: 3}}
  m_Father: {{fileID: 2}}
--- !u!114 &5
MonoBehaviour:
  m_GameObject: {{fileID: 3}}
  m_Sprite: {{fileID: 21300000, guid: {TEXTURE_GUID}, type: 3}}
""",
        )
        return texture

    def test_exports_visual_asset_usage_file_id_and_hierarchy(self) -> None:
        texture = self.seed()
        build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.database,
        )

        context = export_visual_context(
            self.database,
            self.repository,
            self.unity_project,
            "example.hungry-ant",
        )

        self.assertEqual(SCHEMA, context["schema"])
        self.assertEqual("example.hungry-ant", context["projectId"])
        self.assertEqual(64, len(context["indexFingerprint"]))
        self.assertEqual(1, context["summary"]["visualAssets"])
        self.assertEqual(1, context["summary"]["usageRecords"])
        self.assertEqual(0, context["summary"]["unresolvedFileIds"])
        self.assertEqual(
            hashlib.sha256(texture).hexdigest(),
            context["assets"][0]["contentHash"],
        )
        usage = context["usages"][0]
        self.assertEqual(TEXTURE_GUID, usage["unityGuid"])
        self.assertEqual("21300000", usage["fileId"])
        self.assertEqual("Assets/UI/Panel.prefab", usage["ownerPath"])
        self.assertEqual("Canvas/Icon", usage["hierarchyPath"])
        self.assertEqual("MonoBehaviour", usage["componentType"])
        self.assertEqual("m_Sprite", usage["propertyName"])
        self.assertEqual(1, usage["referenceCount"])


if __name__ == "__main__":
    unittest.main()
