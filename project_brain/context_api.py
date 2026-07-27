#!/usr/bin/env python3
"""Unified read-only Context API over Unity, Roslyn, evidence and Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from project_brain.evidence_store import query_evidence


API_VERSION = 1


def confidence_for(query: str, identity: str, name: str | None) -> float:
    if query.casefold() == identity.casefold():
        return 1.0
    if name and query.casefold() == name.casefold():
        return 0.95
    return 0.65


class ContextService:
    def __init__(
        self,
        graph_database: Path,
        evidence_database: Path | None,
        repository: Path,
        unity_project: Path,
    ) -> None:
        if not graph_database.is_file():
            raise ValueError(f"Graph database does not exist: {graph_database}")
        self.graph_database = graph_database
        self.evidence_database = evidence_database
        self.repository = repository
        self.unity_project = unity_project

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.graph_database.as_posix()}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def metadata(self, connection: sqlite3.Connection) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }

    def envelope(
        self,
        operation: str,
        result: Any,
        *,
        unresolved: list[dict[str, Any]] | None = None,
        truncated: bool = False,
    ) -> dict[str, Any]:
        connection = self.connect()
        try:
            metadata = self.metadata(connection)
        finally:
            connection.close()
        return {
            "schemaVersion": API_VERSION,
            "operation": operation,
            "index": {
                "graphFingerprint": metadata.get("graphFingerprint"),
                "gitRevision": metadata.get("gitRevision"),
                "policyName": metadata.get("policyName"),
                "symbolCatalogHash": metadata.get("symbolCatalogHash"),
            },
            "result": result,
            "unresolved": unresolved or [],
            "page": {
                "truncated": truncated,
            },
        }

    def resolve_items(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        pattern = f"%{query}%"
        guid_identity = (
            f"asset:{query.casefold()}"
            if len(query) == 32
            else query
        )
        connection = self.connect()
        try:
            assets = connection.execute(
                """
                SELECT asset_id, guid, path, kind, exists_locally, is_external
                FROM assets
                WHERE asset_id = ? COLLATE NOCASE
                   OR asset_id = ? COLLATE NOCASE
                   OR guid = ? COLLATE NOCASE
                   OR path = ? COLLATE NOCASE
                   OR path LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE WHEN asset_id = ? COLLATE NOCASE THEN 0
                         WHEN guid = ? COLLATE NOCASE THEN 1
                         WHEN path = ? COLLATE NOCASE THEN 2
                         ELSE 3 END,
                    path
                LIMIT ?
                """,
                (
                    query,
                    guid_identity,
                    query,
                    query.replace("\\", "/"),
                    pattern.replace("\\", "/"),
                    query,
                    query,
                    query.replace("\\", "/"),
                    limit,
                ),
            ).fetchall()
            objects = connection.execute(
                """
                SELECT o.object_id, o.name, o.type_name, o.source_path,
                       o.source_line, a.guid
                FROM objects o
                JOIN assets a ON a.asset_id = o.asset_id
                WHERE o.object_id = ? COLLATE NOCASE
                   OR o.name = ? COLLATE NOCASE
                   OR o.name LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE WHEN o.object_id = ? COLLATE NOCASE THEN 0
                         WHEN o.name = ? COLLATE NOCASE THEN 1
                         ELSE 2 END,
                    o.source_path, o.source_line
                LIMIT ?
                """,
                (query, query, pattern, query, query, limit),
            ).fetchall()
            symbols = connection.execute(
                """
                SELECT s.symbol_id, s.roslyn_key, s.kind, s.name,
                       s.qualified_name, s.assembly_name,
                       s.containing_symbol_id,
                       d.project_relative_path, d.line,
                       s.is_unity_object
                FROM code_symbols s
                LEFT JOIN symbol_declarations d
                  ON d.symbol_id = s.symbol_id
                 AND d.rowid = (
                     SELECT MIN(candidate.rowid)
                     FROM symbol_declarations candidate
                     WHERE candidate.symbol_id = s.symbol_id
                 )
                WHERE s.symbol_id = ? COLLATE NOCASE
                   OR s.roslyn_key = ? COLLATE NOCASE
                   OR s.name = ? COLLATE NOCASE
                   OR s.name LIKE ? COLLATE NOCASE
                   OR s.qualified_name LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE WHEN s.symbol_id = ? COLLATE NOCASE THEN 0
                         WHEN s.roslyn_key = ? COLLATE NOCASE THEN 1
                         WHEN s.name = ? COLLATE NOCASE THEN 2
                         ELSE 3 END,
                    s.qualified_name
                LIMIT ?
                """,
                (
                    query,
                    query,
                    query,
                    pattern,
                    pattern,
                    query,
                    query,
                    query,
                    limit,
                ),
            ).fetchall()
        finally:
            connection.close()

        items: list[dict[str, Any]] = []
        for row in assets:
            items.append(
                {
                    "identityId": row["asset_id"],
                    "identityKind": "UnityAsset",
                    "displayName": row["path"] or row["guid"],
                    "path": row["path"],
                    "guid": row["guid"],
                    "assetKind": row["kind"],
                    "existsLocally": bool(row["exists_locally"]),
                    "confidence": (
                        1.0
                        if row["guid"]
                        and query.casefold() == row["guid"].casefold()
                        else confidence_for(
                            query,
                            row["asset_id"],
                            row["path"],
                        )
                    ),
                    "provenance": {
                        "source": "unity-graph",
                        "table": "assets",
                    },
                }
            )
        for row in objects:
            items.append(
                {
                    "identityId": row["object_id"],
                    "identityKind": "UnityObject",
                    "displayName": row["name"] or row["type_name"],
                    "objectType": row["type_name"],
                    "path": row["source_path"],
                    "line": row["source_line"],
                    "assetGuid": row["guid"],
                    "confidence": confidence_for(
                        query,
                        row["object_id"],
                        row["name"],
                    ),
                    "provenance": {
                        "source": "unity-yaml",
                        "path": row["source_path"],
                        "line": row["source_line"],
                    },
                }
            )
        for row in symbols:
            items.append(
                {
                    "identityId": row["symbol_id"],
                    "identityKind": "CodeSymbol",
                    "displayName": row["qualified_name"],
                    "symbolKind": row["kind"],
                    "name": row["name"],
                    "qualifiedName": row["qualified_name"],
                    "assembly": row["assembly_name"],
                    "containingSymbolId": row["containing_symbol_id"],
                    "path": row["project_relative_path"],
                    "line": row["line"],
                    "isUnityObject": bool(row["is_unity_object"]),
                    "confidence": confidence_for(
                        query,
                        row["symbol_id"],
                        row["name"],
                    ),
                    "provenance": {
                        "source": "roslyn-symbol-catalog",
                        "roslynKey": row["roslyn_key"],
                        "path": row["project_relative_path"],
                        "line": row["line"],
                    },
                }
            )
        items.sort(
            key=lambda item: (
                -item["confidence"],
                item["identityKind"],
                item["displayName"] or "",
            )
        )
        return items[:limit]

    def resolve(self, query: str, limit: int = 20) -> dict[str, Any]:
        items = self.resolve_items(query, limit + 1)
        return self.envelope(
            "resolve",
            {"query": query, "items": items[:limit]},
            unresolved=(
                []
                if items
                else [{"query": query, "reason": "no-identity-match"}]
            ),
            truncated=len(items) > limit,
        )

    def require_identity(self, identity_or_query: str) -> dict[str, Any]:
        items = self.resolve_items(identity_or_query, 2)
        if not items:
            raise ValueError(f"Identity not found: {identity_or_query}")
        if (
            len(items) > 1
            and items[0]["confidence"] == items[1]["confidence"]
            and items[0]["confidence"] < 1.0
        ):
            raise ValueError(
                f"Ambiguous identity query: {identity_or_query}; use identityId"
            )
        return items[0]

    def edges_for(
        self,
        identity_id: str,
        *,
        direction: str = "both",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if direction in {"both", "out"}:
            clauses.append("source_id = ?")
            parameters.append(identity_id)
        if direction in {"both", "in"}:
            clauses.append("target_id = ?")
            parameters.append(identity_id)
        connection = self.connect()
        try:
            rows = connection.execute(
                f"""
                SELECT source_id, relation, target_id, property_name,
                       source_path, source_line, evidence_hash
                FROM edges
                WHERE {' OR '.join(clauses)}
                ORDER BY relation, source_path, source_line
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "sourceId": row["source_id"],
                "relation": row["relation"],
                "targetId": row["target_id"],
                "property": row["property_name"] or None,
                "provenance": {
                    "source": "unity-graph",
                    "path": row["source_path"],
                    "line": row["source_line"],
                    "evidenceHash": row["evidence_hash"],
                },
                "confidence": 1.0,
            }
            for row in rows
        ]

    def linked_evidence(
        self,
        identity_ids: list[str],
        evidence_policy: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self.evidence_database is None:
            return []
        collected: dict[str, dict[str, Any]] = {}
        for identity_id in identity_ids:
            for record in query_evidence(
                self.evidence_database,
                identity_id=identity_id,
                limit=limit,
            ):
                if evidence_policy == "authoritative" and record["confidence"] < 0.8:
                    continue
                if (
                    evidence_policy in {
                        "runtime",
                        "external-evidence",
                        "unity-gate",
                    }
                    and record["sourceKind"] != evidence_policy
                ):
                    continue
                collected[record["evidenceId"]] = record
        return list(collected.values())[:limit]

    def context(
        self,
        identity_or_query: str,
        depth: int = 1,
        evidence_policy: str = "all",
        limit: int = 200,
    ) -> dict[str, Any]:
        root = self.require_identity(identity_or_query)
        depth = max(0, min(depth, 4))
        frontier = {root["identityId"]}
        visited = set(frontier)
        edges: list[dict[str, Any]] = []
        for _ in range(depth):
            next_frontier: set[str] = set()
            for identity_id in sorted(frontier):
                for edge in self.edges_for(
                    identity_id,
                    direction="both",
                    limit=limit,
                ):
                    edge_key = (
                        edge["sourceId"],
                        edge["relation"],
                        edge["targetId"],
                        edge["provenance"]["path"],
                        edge["provenance"]["line"],
                    )
                    if not any(
                        (
                            current["sourceId"],
                            current["relation"],
                            current["targetId"],
                            current["provenance"]["path"],
                            current["provenance"]["line"],
                        )
                        == edge_key
                        for current in edges
                    ):
                        edges.append(edge)
                    next_frontier.update(
                        (edge["sourceId"], edge["targetId"])
                    )
            next_frontier -= visited
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier or len(visited) >= limit:
                break

        nodes: list[dict[str, Any]] = []
        for identity_id in sorted(visited)[:limit]:
            matches = self.resolve_items(identity_id, 1)
            if matches:
                nodes.append(matches[0])
            else:
                nodes.append(
                    {
                        "identityId": identity_id,
                        "identityKind": "UnresolvedTarget",
                        "displayName": identity_id,
                        "confidence": 0.0,
                    }
                )
        evidence = self.linked_evidence(
            [node["identityId"] for node in nodes],
            evidence_policy,
            limit,
        )
        return self.envelope(
            "context",
            {
                "root": root,
                "depth": depth,
                "nodes": nodes,
                "edges": edges[:limit],
                "evidence": evidence,
            },
            unresolved=[
                {
                    "identityId": node["identityId"],
                    "reason": "edge-target-not-materialized-in-local-index",
                }
                for node in nodes
                if node["identityKind"] == "UnresolvedTarget"
            ],
            truncated=len(visited) > limit or len(edges) > limit,
        )

    def uses(self, identity_or_query: str, limit: int = 200) -> dict[str, Any]:
        root = self.require_identity(identity_or_query)
        target_ids = {root["identityId"]}
        connection = self.connect()
        try:
            if root["identityKind"] == "CodeSymbol":
                type_id = (
                    root["identityId"]
                    if root.get("symbolKind") == "Type"
                    else root.get("containingSymbolId")
                )
                if type_id:
                    target_ids.update(
                        row[0]
                        for row in connection.execute(
                            """
                            SELECT asset_id FROM script_symbol_links
                            WHERE symbol_id = ?
                            """,
                            (type_id,),
                        )
                    )
        finally:
            connection.close()
        edges: list[dict[str, Any]] = []
        for target_id in sorted(target_ids):
            edges.extend(self.edges_for(target_id, direction="in", limit=limit))
        return self.envelope(
            "uses",
            {
                "root": root,
                "resolvedTargetIds": sorted(target_ids),
                "uses": edges[:limit],
            },
            truncated=len(edges) > limit,
        )

    def required_gates(
        self,
        root: dict[str, Any],
        change_kind: str,
    ) -> list[str]:
        gates = {"git-diff", "graph-integrity"}
        if root["identityKind"] == "CodeSymbol":
            gates.update({"roslyn-compile", "unity-compile"})
            if root.get("isUnityObject") or root.get("symbolKind") == "Type":
                gates.update(
                    {
                        "unity-guid-preservation",
                        "unity-missing-script",
                        "unity-serialized-reference",
                    }
                )
        if root["identityKind"] in {"UnityAsset", "UnityObject"}:
            gates.update(
                {
                    "unity-guid-preservation",
                    "unity-missing-script",
                    "unity-serialized-reference",
                }
            )
        if change_kind.casefold() in {"rename", "delete", "move"}:
            gates.add("identity-lineage")
        return sorted(gates)

    def impact(
        self,
        identity_or_query: str,
        change_kind: str,
        limit: int = 200,
    ) -> dict[str, Any]:
        uses = self.uses(identity_or_query, limit)
        root = uses["result"]["root"]
        return self.envelope(
            "impact",
            {
                "root": root,
                "changeKind": change_kind,
                "affectedEdges": uses["result"]["uses"],
                "requiredGates": self.required_gates(root, change_kind),
            },
            truncated=uses["page"]["truncated"],
        )

    def repository_relative_path(
        self,
        node: dict[str, Any],
    ) -> str | None:
        project_path = node.get("path")
        if not project_path:
            return None
        absolute = self.unity_project / Path(project_path)
        try:
            return absolute.relative_to(self.repository).as_posix()
        except ValueError:
            return None

    def history(
        self,
        identity_or_query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        root = self.require_identity(identity_or_query)
        path = self.repository_relative_path(root)
        if path is None:
            return self.envelope(
                "history",
                {"root": root, "path": None, "commits": []},
                unresolved=[
                    {
                        "identityId": root["identityId"],
                        "reason": "identity-has-no-repository-path",
                    }
                ],
            )
        process = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.repository.as_posix()}",
                "log",
                "--follow",
                f"--max-count={max(1, min(limit, 200))}",
                "--format=%H%x1f%aI%x1f%an%x1f%s%x00",
                "--",
                path,
            ],
            cwd=self.repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0:
            raise ValueError(
                process.stderr.decode("utf-8", errors="replace").strip()
            )
        commits: list[dict[str, Any]] = []
        for entry in process.stdout.decode(
            "utf-8",
            errors="replace",
        ).split("\0"):
            entry = entry.strip()
            if not entry:
                continue
            fields = entry.split("\x1f", 3)
            if len(fields) != 4:
                continue
            commit_hash, observed, author, subject = fields
            material = f"{commit_hash}\0{path}"
            commits.append(
                {
                    "evidenceId": "evidence:"
                    + hashlib.sha256(material.encode("utf-8")).hexdigest(),
                    "sourceKind": "git-history",
                    "sourceUri": f"git:{commit_hash}:{path}",
                    "identityIds": [root["identityId"]],
                    "claim": "git.commit.touched-path",
                    "confidence": 1.0,
                    "observedUtc": observed,
                    "commitHash": commit_hash,
                    "payload": {
                        "path": path,
                        "author": author,
                        "subject": subject,
                    },
                }
            )
        return self.envelope(
            "history",
            {"root": root, "path": path, "commits": commits},
        )

    def evidence(self, claim: str, limit: int = 50) -> dict[str, Any]:
        records = (
            query_evidence(
                self.evidence_database,
                claim=claim,
                limit=limit + 1,
            )
            if self.evidence_database is not None
            else []
        )
        return self.envelope(
            "evidence",
            {"claim": claim, "items": records[:limit]},
            truncated=len(records) > limit,
        )


def service_from_args(args: argparse.Namespace) -> ContextService:
    return ContextService(
        args.graph.resolve(),
        args.evidence.resolve() if args.evidence else None,
        args.repository.resolve(),
        args.unity_project.resolve(),
    )


def execute_operation(
    service: ContextService,
    operation: str,
    parameters: dict[str, str],
) -> dict[str, Any]:
    if operation == "resolve":
        return service.resolve(
            parameters.get("q", ""),
            int(parameters.get("limit", "20")),
        )
    identity = parameters.get("id", "")
    if operation == "context":
        return service.context(
            identity,
            int(parameters.get("depth", "1")),
            parameters.get("evidencePolicy", "all"),
            int(parameters.get("limit", "200")),
        )
    if operation == "impact":
        return service.impact(
            identity,
            parameters.get("changeKind", "modify"),
            int(parameters.get("limit", "200")),
        )
    if operation == "uses":
        return service.uses(identity, int(parameters.get("limit", "200")))
    if operation == "history":
        return service.history(identity, int(parameters.get("limit", "20")))
    if operation == "evidence":
        return service.evidence(
            parameters.get("claim", ""),
            int(parameters.get("limit", "50")),
        )
    raise ValueError(f"Unsupported Context API operation: {operation}")


def serve(service: ContextService, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 2 or parts[0] != "v1":
                self.send_error(404)
                return
            parameters = {
                key: values[-1]
                for key, values in parse_qs(parsed.query).items()
                if values
            }
            try:
                response = execute_operation(
                    service,
                    parts[1],
                    parameters,
                )
                payload = json.dumps(
                    response,
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                self.send_response(200)
            except (ValueError, sqlite3.Error) as error:
                payload = json.dumps(
                    {
                        "schemaVersion": API_VERSION,
                        "error": str(error),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *values: Any) -> None:
            print(f"[context-api] {format % values}", file=sys.stderr)

    server = ThreadingHTTPServer((host, port), Handler)
    print(
        json.dumps(
            {
                "success": True,
                "listening": f"http://{host}:{port}/v1",
            }
        ),
        flush=True,
    )
    server.serve_forever()


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--unity-project", type=Path, required=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("resolve", "context", "impact", "uses", "history", "evidence"):
        operation = subparsers.add_parser(name)
        add_common_arguments(operation)
        if name == "resolve":
            operation.add_argument("query")
        elif name == "evidence":
            operation.add_argument("claim")
        else:
            operation.add_argument("identity")
        operation.add_argument("--limit", type=int)
        if name == "context":
            operation.add_argument("--depth", type=int, default=1)
            operation.add_argument("--evidence-policy", default="all")
        if name == "impact":
            operation.add_argument("--change-kind", default="modify")
    server = subparsers.add_parser("serve")
    add_common_arguments(server)
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        service = service_from_args(args)
        if args.command == "serve":
            serve(service, args.host, args.port)
            return 0
        parameters = {
            "limit": str(args.limit or (20 if args.command in {"resolve", "history"} else 200))
        }
        if args.command == "resolve":
            parameters["q"] = args.query
        elif args.command == "evidence":
            parameters["claim"] = args.claim
        else:
            parameters["id"] = args.identity
        if args.command == "context":
            parameters["depth"] = str(args.depth)
            parameters["evidencePolicy"] = args.evidence_policy
        if args.command == "impact":
            parameters["changeKind"] = args.change_kind
        result = execute_operation(service, args.command, parameters)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
