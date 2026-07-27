from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_brain.evidence_store import ingest, query_evidence


class EvidenceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "evidence.sqlite"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_ingest_is_idempotent_and_preserves_identity_provenance(self) -> None:
        records = [
            {
                "eventName": "basket.capacity.changed",
                "identityId": "roslyn:basket",
                "timestampUtc": "2026-07-25T00:00:00Z",
                "confidence": 0.95,
                "value": 7,
            }
        ]

        first = ingest(
            self.database,
            "runtime",
            "runtime://fixture/session-1",
            records,
        )
        second = ingest(
            self.database,
            "runtime",
            "runtime://fixture/session-1",
            records,
        )
        found = query_evidence(
            self.database,
            identity_id="roslyn:basket",
        )

        self.assertEqual(1, first["inserted"])
        self.assertEqual(0, second["inserted"])
        self.assertEqual(1, len(found))
        self.assertEqual("runtime", found[0]["sourceKind"])
        self.assertEqual(0.95, found[0]["confidence"])
        self.assertEqual(["roslyn:basket"], found[0]["identityIds"])

    def test_external_guid_links_to_unity_asset_identity(self) -> None:
        ingest(
            self.database,
            "external-evidence",
            "external://fixture/type/1",
            [
                {
                    "claim": "recovered-type-name",
                    "result": {
                        "assetGuid": "A" * 32,
                    },
                    "name": "RecoveredBasket",
                }
            ],
        )

        found = query_evidence(
            self.database,
            identity_id=f"asset:{'a' * 32}",
            claim="recovered",
        )

        self.assertEqual(1, len(found))
        self.assertEqual(0.65, found[0]["confidence"])


if __name__ == "__main__":
    unittest.main()
