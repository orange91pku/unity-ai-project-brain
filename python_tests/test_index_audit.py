from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_brain.index_audit import audit


class IndexAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.root = temporary_root / "repository"
        self.root.mkdir()
        self.policy = temporary_root / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "exclude": {
                        "directoryNames": ["Library", "PackageCache", "Temp"],
                        "pathPrefixes": ["_pull"],
                    },
                    "lanes": {
                        "code": {"extensions": [".cs"]},
                        "assetIdentity": {"extensions": [".meta"]},
                    },
                    "gates": {
                        "forbiddenAcceptedDirectoryNames": [
                            "Library",
                            "PackageCache",
                            "Temp",
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str = "x") -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_excludes_nested_unity_cache_and_classifies_source(self) -> None:
        self.write("game/Assets/Scripts/Player.cs", "class Player {}")
        self.write("game/Assets/Scripts/Player.cs.meta", "guid: abc")
        self.write("game/Library/PackageCache/vendor/Generated.cs", "class Noise {}")
        self.write("_pull/copied.cs", "class Copy {}")

        result = audit(self.root, self.policy)

        self.assertEqual(2, result.accepted.files)
        self.assertEqual(2, result.excluded.files)
        self.assertEqual(1, result.lanes["code"].files)
        self.assertEqual(1, result.lanes["assetIdentity"].files)
        self.assertFalse(result.gate_violations)

    def test_exclusion_is_case_insensitive(self) -> None:
        self.write("game/library/noise.cs")
        self.write("game/TEMP/noise.cs")

        result = audit(self.root, self.policy)

        self.assertEqual(0, result.accepted.files)
        self.assertEqual(2, result.excluded.files)


if __name__ == "__main__":
    unittest.main()
