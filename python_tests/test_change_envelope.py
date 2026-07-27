from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_brain.change_envelope import (
    RawChange,
    WORKTREE,
    build_git_envelope,
    canonical_envelope_id,
    filter_changes,
    merge_envelopes,
    parse_name_status_z,
    validate_envelope,
)
from project_brain.index_audit import IndexPolicy


class ChangeEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.repository = temporary_root / "repository"
        self.repository.mkdir()
        self.policy = temporary_root / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "test-policy",
                    "exclude": {
                        "directoryNames": ["Library", "Temp"],
                        "pathPrefixes": [],
                    },
                    "lanes": {
                        "code": {"extensions": [".cs"]},
                        "unitySerialized": {
                            "extensions": [".prefab", ".unity"]
                        },
                        "assetIdentity": {"extensions": [".meta"]},
                    },
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )
        self.git("init")
        self.git("config", "user.email", "test@project-brain.invalid")
        self.git("config", "user.name", "Project Brain Test")

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

    def write(self, relative_path: str, content: str) -> None:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def seed_commit(self) -> None:
        self.write(
            "Assets/Old.prefab",
            "--- !u!1 &1\nGameObject:\n  m_Name: Old\n",
        )
        self.write(
            "Assets/Old.prefab.meta",
            "guid: 11111111111111111111111111111111\n",
        )
        self.write(
            "Assets/Main.unity",
            "--- !u!1 &1\nGameObject:\n  m_Name: Main\n",
        )
        self.write(
            "Assets/Main.unity.meta",
            "guid: 22222222222222222222222222222222\n",
        )
        self.git("add", ".")
        self.git("commit", "-m", "baseline")

    def test_parses_null_delimited_rename_records(self) -> None:
        changes = parse_name_status_z(
            b"R100\0Assets/Old.prefab\0Assets/New.prefab\0"
            b"M\0Assets/Main.unity\0"
        )
        self.assertEqual("renamed", changes[0].status)
        self.assertEqual("Assets/Old.prefab", changes[0].old_path)
        self.assertEqual("Assets/New.prefab", changes[0].path)
        self.assertEqual("modified", changes[1].status)

    def test_filters_generated_paths_and_normalizes_boundary_renames(self) -> None:
        policy = IndexPolicy(
            {
                "schemaVersion": 1,
                "exclude": {
                    "directoryNames": ["Library", "Temp"],
                    "pathPrefixes": ["ignored"],
                },
                "lanes": {},
                "gates": {},
            }
        )
        changes = filter_changes(
            [
                RawChange("added", "Unity/Library/cache.bin"),
                RawChange("added", "Unity/Library.meta"),
                RawChange("added", "ignored.meta"),
                RawChange("modified", "ignored/report.json"),
                RawChange(
                    "renamed",
                    "Unity/Assets/Visible.prefab",
                    "Unity/Temp/Hidden.prefab",
                ),
                RawChange(
                    "renamed",
                    "Unity/Temp/Hidden2.prefab",
                    "Unity/Assets/Visible2.prefab",
                ),
                RawChange("modified", "Unity/Assets/Kept.prefab"),
            ],
            policy,
        )

        self.assertEqual(
            [
                RawChange("modified", "Unity/Assets/Kept.prefab"),
                RawChange("added", "Unity/Assets/Visible.prefab"),
                RawChange("deleted", "Unity/Assets/Visible2.prefab"),
            ],
            changes,
        )

    def test_collects_rename_untracked_guid_hash_and_invalidations(self) -> None:
        self.seed_commit()
        self.git("mv", "Assets/Old.prefab", "Assets/New.prefab")
        self.git("mv", "Assets/Old.prefab.meta", "Assets/New.prefab.meta")
        self.write(
            "Assets/Main.unity",
            "--- !u!1 &1\nGameObject:\n  m_Name: Changed\n",
        )
        self.write("Assets/Player.cs", "class Player {}\n")
        self.write(
            "Assets/Player.cs.meta",
            "guid: 33333333333333333333333333333333\n",
        )

        first = build_git_envelope(
            self.repository,
            "fixture",
            "HEAD",
            WORKTREE,
            self.policy,
        )
        second = build_git_envelope(
            self.repository,
            "fixture",
            "HEAD",
            WORKTREE,
            self.policy,
        )

        validate_envelope(first)
        self.assertEqual(first["envelopeId"], second["envelopeId"])
        by_path = {change["path"]: change for change in first["changes"]}
        renamed = by_path["Assets/New.prefab"]
        self.assertEqual("renamed", renamed["status"])
        self.assertEqual("Assets/Old.prefab", renamed["oldPath"])
        self.assertEqual(
            "11111111111111111111111111111111",
            renamed["unityGuid"],
        )
        self.assertIn(
            "unity.identity-lineage",
            renamed["invalidates"],
        )

        script = by_path["Assets/Player.cs"]
        self.assertEqual("added", script["status"])
        self.assertEqual(
            "33333333333333333333333333333333",
            script["unityGuid"],
        )
        self.assertEqual(64, len(script["contentHash"]))
        self.assertIn("roslyn.symbol-catalog", script["invalidates"])

        scene = by_path["Assets/Main.unity"]
        self.assertEqual("modified", scene["status"])
        self.assertIn("unity.serialized-objects", scene["invalidates"])

    def test_merge_coalesces_modify_and_rename_chains(self) -> None:
        def envelope(
            generated: str,
            changes: list[dict[str, object]],
        ) -> dict[str, object]:
            document: dict[str, object] = {
                "schemaVersion": 1,
                "envelopeId": "",
                "projectId": "fixture",
                "source": "unity-asset-postprocessor",
                "generatedUtc": generated,
                "baseRevision": None,
                "targetRevision": "UNITY_EDITOR",
                "policyVersion": "test",
                "changes": changes,
            }
            document["envelopeId"] = canonical_envelope_id(document)
            return document

        common = {
            "unityGuid": "1" * 32,
            "contentHash": "2" * 64,
            "lane": "unitySerialized",
            "invalidates": ["unity.serialized-objects"],
        }
        first = envelope(
            "2026-01-01T00:00:00Z",
            [
                {
                    **common,
                    "status": "added",
                    "path": "Assets/New.prefab",
                    "oldPath": None,
                },
                {
                    **common,
                    "status": "renamed",
                    "path": "Assets/B.prefab",
                    "oldPath": "Assets/A.prefab",
                },
            ],
        )
        second = envelope(
            "2026-01-01T00:01:00Z",
            [
                {
                    **common,
                    "status": "modified",
                    "path": "Assets/New.prefab",
                    "oldPath": None,
                    "contentHash": "3" * 64,
                },
                {
                    **common,
                    "status": "renamed",
                    "path": "Assets/C.prefab",
                    "oldPath": "Assets/B.prefab",
                },
            ],
        )

        merged = merge_envelopes([second, first])
        by_path = {item["path"]: item for item in merged["changes"]}

        self.assertEqual("added", by_path["Assets/New.prefab"]["status"])
        self.assertEqual("3" * 64, by_path["Assets/New.prefab"]["contentHash"])
        self.assertEqual("renamed", by_path["Assets/C.prefab"]["status"])
        self.assertEqual(
            "Assets/A.prefab",
            by_path["Assets/C.prefab"]["oldPath"],
        )
        self.assertEqual(
            merged["envelopeId"],
            merge_envelopes([second, first])["envelopeId"],
        )


if __name__ == "__main__":
    unittest.main()
