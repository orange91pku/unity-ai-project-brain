from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_brain.change_envelope import WORKTREE, build_git_envelope
from project_brain.incremental_graph import apply_incremental, build_plan
from project_brain.unity_graph import build_graph


GUID = "11111111111111111111111111111111"


class IncrementalGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.repository = root / "repository"
        self.unity_project = self.repository / "Unity"
        self.assets = self.unity_project / "Assets"
        self.assets.mkdir(parents=True)
        self.policy = root / "policy.json"
        self.database = root / "graph.sqlite"
        self.clean_database = root / "clean.sqlite"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "test",
                    "exclude": {
                        "directoryNames": ["Library"],
                        "pathPrefixes": [],
                    },
                    "lanes": {
                        "unitySerialized": {
                            "extensions": [".prefab", ".unity"]
                        }
                    },
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )
        self.write_prefab("Before")
        self.git("init")
        self.git("config", "user.email", "test@project-brain.invalid")
        self.git("config", "user.name", "Project Brain Test")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def write_prefab(self, name: str) -> None:
        (self.assets / "Thing.prefab").write_text(
            "%YAML 1.1\n"
            "--- !u!1 &1\n"
            "GameObject:\n"
            f"  m_Name: {name}\n",
            encoding="utf-8",
        )
        (self.assets / "Thing.prefab.meta").write_text(
            f"guid: {GUID}\n",
            encoding="utf-8",
        )

    def test_incremental_modified_prefab_matches_clean_rebuild(self) -> None:
        build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.database,
        )
        self.write_prefab("After")
        envelope = build_git_envelope(
            self.repository,
            "fixture",
            "HEAD",
            WORKTREE,
            self.policy,
        )

        plan = build_plan(envelope)
        self.assertTrue(plan["canApplyIncrementally"])
        result = apply_incremental(
            self.repository,
            self.unity_project,
            self.database,
            envelope,
        )
        clean = build_graph(
            self.repository,
            self.unity_project,
            self.policy,
            self.clean_database,
        )

        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(
            clean["graphFingerprint"],
            result["graphFingerprint"],
        )

    def test_meta_change_requires_full_rebuild(self) -> None:
        self.write_prefab("Changed")
        (self.assets / "Thing.prefab.meta").write_text(
            "guid: 22222222222222222222222222222222\n",
            encoding="utf-8",
        )
        envelope = build_git_envelope(
            self.repository,
            "fixture",
            "HEAD",
            WORKTREE,
            self.policy,
        )

        plan = build_plan(envelope)
        self.assertTrue(plan["requiresFullRebuild"])

    def test_project_settings_asset_does_not_enter_assets_graph(self) -> None:
        envelope = {
            "schemaVersion": 1,
            "envelopeId": "",
            "projectId": "fixture",
            "source": "git-diff",
            "generatedUtc": "2026-01-01T00:00:00+00:00",
            "baseRevision": "a",
            "targetRevision": "b",
            "policyVersion": "test",
            "changes": [
                {
                    "status": "modified",
                    "path": "Unity/ProjectSettings/Settings.asset",
                    "oldPath": None,
                    "unityGuid": None,
                    "contentHash": "0" * 64,
                    "lane": "unitySerialized",
                    "invalidates": [
                        "gitnexus.path",
                        "unity.project-settings",
                        "unity.serialized-objects",
                    ],
                }
            ],
        }
        from project_brain.change_envelope import canonical_envelope_id

        envelope["envelopeId"] = canonical_envelope_id(envelope)
        plan = build_plan(envelope)

        self.assertTrue(plan["canApplyIncrementally"])
        self.assertEqual("ignore", plan["changes"][0]["action"])

    def test_unity_producer_path_is_already_project_relative(self) -> None:
        from project_brain.incremental_graph import (
            repository_path_to_unity_path,
        )

        self.assertEqual(
            "Assets/Thing.prefab",
            repository_path_to_unity_path(
                "Assets/Thing.prefab",
                self.repository,
                self.unity_project,
            ),
        )


if __name__ == "__main__":
    unittest.main()
