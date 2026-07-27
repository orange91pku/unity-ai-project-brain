#!/usr/bin/env python3
"""Ingest and query provenance-preserving Unity Brain evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


SOURCE_KINDS = {
    "runtime",
    "external-evidence",
    "unity-gate",
    "git-history",
}
DEFAULT_CONFIDENCE = {
    "runtime": 0.9,
    "external-evidence": 0.65,
    "unity-gate": 1.0,
    "git-history": 1.0,
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            claim TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            observed_utc TEXT,
            commit_hash TEXT,
            content_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evidence_links (
            evidence_id TEXT NOT NULL,
            identity_id TEXT NOT NULL,
            PRIMARY KEY(evidence_id, identity_id),
            FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS evidence_claim_idx
            ON evidence(claim, source_kind);
        CREATE INDEX IF NOT EXISTS evidence_links_identity_idx
            ON evidence_links(identity_id, evidence_id);
        """
    )


def read_input_records(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.casefold() == ".jsonl":
        return [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
    document = json.loads(text)
    if isinstance(document, list):
        return document
    if not isinstance(document, dict):
        return [{"value": document}]
    for key in ("evidence", "events", "records", "results"):
        value = document.get(key)
        if isinstance(value, list):
            return value
    return [document]


def strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item)]
    return [str(value)]


def identity_ids_for(record: dict[str, Any]) -> list[str]:
    identities: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            if key in {
                "identityIds",
                "identityId",
                "symbolId",
                "assetId",
                "objectId",
            }:
                identities.extend(strings(child))
            elif key in {"unityGuid", "assetGuid", "guid"}:
                if isinstance(child, str) and len(child) == 32:
                    identities.append(f"asset:{child.casefold()}")
            if isinstance(child, (dict, list)):
                visit(child)

    visit(record)
    return sorted(set(identities))


def first_text(record: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def normalize_record(
    record: Any,
    source_kind: str,
    source_uri: str,
) -> dict[str, Any]:
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"Unsupported evidence source kind: {source_kind}")
    payload = record if isinstance(record, dict) else {"value": record}
    claim = first_text(
        payload,
        ("claim", "eventName", "event", "name", "status", "type"),
    ) or f"{source_kind}.observation"
    confidence_value = payload.get(
        "confidence",
        DEFAULT_CONFIDENCE[source_kind],
    )
    try:
        confidence = float(confidence_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid evidence confidence: {confidence_value}") from error
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"Evidence confidence must be in [0,1]: {confidence}")

    observed_utc = first_text(
        payload,
        (
            "observedUtc",
            "checkedAtUtc",
            "startedUtc",
            "timestampUtc",
            "timestamp",
            "time",
        ),
    )
    commit_hash = first_text(payload, ("commitHash", "commit", "revision"))
    identities = identity_ids_for(payload)
    payload_json = canonical_json(payload)
    identity_material = canonical_json(
        {
            "sourceKind": source_kind,
            "sourceUri": source_uri,
            "claim": claim,
            "payload": payload,
        }
    )
    evidence_id = (
        "evidence:"
        + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()
    )
    return {
        "schemaVersion": 1,
        "evidenceId": evidence_id,
        "sourceKind": source_kind,
        "sourceUri": source_uri,
        "claim": claim,
        "identityIds": identities,
        "confidence": confidence,
        "observedUtc": observed_utc,
        "commitHash": commit_hash,
        "payload": payload,
        "_payloadJson": payload_json,
        "_contentHash": hashlib.sha256(
            payload_json.encode("utf-8")
        ).hexdigest(),
    }


def ingest(
    database_path: Path,
    source_kind: str,
    source_uri: str,
    records: Iterable[Any],
) -> dict[str, Any]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    inserted = 0
    linked = 0
    normalized_records: list[dict[str, Any]] = []
    try:
        initialize_database(connection)
        for raw_record in records:
            record = normalize_record(raw_record, source_kind, source_uri)
            normalized_records.append(record)
            existed = connection.execute(
                "SELECT 1 FROM evidence WHERE evidence_id = ?",
                (record["evidenceId"],),
            ).fetchone() is not None
            cursor = connection.execute(
                """
                INSERT INTO evidence(
                    evidence_id, source_kind, source_uri, claim, payload_json,
                    confidence, observed_utc, commit_hash, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    observed_utc = COALESCE(
                        excluded.observed_utc,
                        evidence.observed_utc
                    ),
                    commit_hash = COALESCE(
                        excluded.commit_hash,
                        evidence.commit_hash
                    )
                """,
                (
                    record["evidenceId"],
                    record["sourceKind"],
                    record["sourceUri"],
                    record["claim"],
                    record["_payloadJson"],
                    record["confidence"],
                    record["observedUtc"],
                    record["commitHash"],
                    record["_contentHash"],
                ),
            )
            inserted += 0 if existed else max(cursor.rowcount, 0)
            for identity_id in record["identityIds"]:
                link_cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO evidence_links(
                        evidence_id, identity_id
                    ) VALUES (?, ?)
                    """,
                    (record["evidenceId"], identity_id),
                )
                linked += max(link_cursor.rowcount, 0)
        connection.commit()
    finally:
        connection.close()
    return {
        "success": True,
        "database": str(database_path.resolve()),
        "sourceKind": source_kind,
        "received": len(normalized_records),
        "inserted": inserted,
        "linked": linked,
        "evidenceIds": [record["evidenceId"] for record in normalized_records],
    }


def query_evidence(
    database_path: Path,
    *,
    identity_id: str | None = None,
    claim: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not database_path.is_file():
        return []
    connection = sqlite3.connect(database_path)
    try:
        initialize_database(connection)
        conditions: list[str] = []
        parameters: list[Any] = []
        joins = ""
        if identity_id:
            joins = (
                " JOIN evidence_links l"
                " ON l.evidence_id = e.evidence_id"
            )
            conditions.append("l.identity_id = ?")
            parameters.append(identity_id)
        if claim:
            conditions.append(
                "(lower(e.claim) LIKE lower(?)"
                " OR lower(e.payload_json) LIKE lower(?))"
            )
            pattern = f"%{claim}%"
            parameters.extend((pattern, pattern))
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(max(1, min(limit, 500)))
        rows = connection.execute(
            f"""
            SELECT e.evidence_id, e.source_kind, e.source_uri, e.claim,
                   e.payload_json, e.confidence, e.observed_utc,
                   e.commit_hash
            FROM evidence e
            {joins}
            {where}
            ORDER BY COALESCE(e.observed_utc, '') DESC, e.evidence_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            identities = [
                link[0]
                for link in connection.execute(
                    """
                    SELECT identity_id FROM evidence_links
                    WHERE evidence_id = ? ORDER BY identity_id
                    """,
                    (row[0],),
                )
            ]
            results.append(
                {
                    "evidenceId": row[0],
                    "sourceKind": row[1],
                    "sourceUri": row[2],
                    "claim": row[3],
                    "payload": json.loads(row[4]),
                    "confidence": row[5],
                    "observedUtc": row[6],
                    "commitHash": row[7],
                    "identityIds": identities,
                }
            )
        return results
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--database", type=Path, required=True)
    ingest_parser.add_argument("--kind", choices=sorted(SOURCE_KINDS), required=True)
    ingest_parser.add_argument("--source-uri")
    ingest_parser.add_argument("input", type=Path)
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--database", type=Path, required=True)
    query_parser.add_argument("--identity")
    query_parser.add_argument("--claim")
    query_parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "ingest":
            result = ingest(
                args.database.resolve(),
                args.kind,
                args.source_uri or args.input.resolve().as_uri(),
                read_input_records(args.input),
            )
        else:
            result = {
                "success": True,
                "evidence": query_evidence(
                    args.database.resolve(),
                    identity_id=args.identity,
                    claim=args.claim,
                    limit=args.limit,
                ),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
