"""Export a versioned, read-only visual context for specialist applications."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_brain.unity_graph import validate_graph


SCHEMA = "hydracore.project-brain.visual-context/v1"
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tga",
    ".bmp",
    ".psd",
    ".exr",
    ".hdr",
}
GUID_FILE_ID = re.compile(
    r"fileID:\s*(-?\d+).*?guid:\s*([0-9a-fA-F]{32})",
    re.DOTALL,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_readonly(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def target_file_id(
    unity_project: Path,
    source_path: str,
    source_line: int,
    target_guid: str,
) -> str | None:
    path = unity_project / Path(source_path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    start = max(0, source_line - 1)
    evidence = "\n".join(lines[start : min(len(lines), start + 6)])
    for match in GUID_FILE_ID.finditer(evidence):
        if match.group(2).casefold() == target_guid.casefold():
            return match.group(1)
    return None


def hierarchy_path(
    object_id: str,
    object_rows: dict[str, sqlite3.Row],
    parents: dict[str, str],
) -> str | None:
    names: list[str] = []
    visited: set[str] = set()
    current: str | None = object_id
    while current and current not in visited:
        visited.add(current)
        row = object_rows.get(current)
        if row and row["name"]:
            names.append(row["name"])
        current = parents.get(current)
    return "/".join(reversed(names)) or None


def export_visual_context(
    graph_database: Path,
    repository: Path,
    unity_project: Path,
    project_id: str,
) -> dict[str, Any]:
    graph_database = graph_database.resolve()
    repository = repository.resolve()
    unity_project = unity_project.resolve()
    validation = validate_graph(graph_database)
    if not validation["passed"]:
        raise ValueError(
            "Project Brain graph failed integrity validation; refusing export."
        )
    try:
        unity_project.relative_to(repository)
    except ValueError as error:
        raise ValueError("Unity project must be inside the configured repository.") from error

    connection = open_readonly(graph_database)
    try:
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        image_rows = connection.execute(
            """
            SELECT asset_id, guid, path, kind
            FROM assets
            WHERE exists_locally = 1
              AND guid IS NOT NULL
              AND path IS NOT NULL
            ORDER BY path
            """
        ).fetchall()
        images = [
            row
            for row in image_rows
            if Path(row["path"]).suffix.casefold() in IMAGE_EXTENSIONS
        ]
        image_asset_ids = {row["asset_id"] for row in images}

        object_rows = {
            row["object_id"]: row
            for row in connection.execute(
                "SELECT object_id, name, type_name, asset_id FROM objects"
            )
        }
        parents = {
            row["source_id"]: row["target_id"]
            for row in connection.execute(
                """
                SELECT source_id, target_id
                FROM edges
                WHERE relation = 'GAME_OBJECT_PARENT'
                """
            )
        }
        component_game_objects = {
            row["source_id"]: row["target_id"]
            for row in connection.execute(
                """
                SELECT source_id, target_id
                FROM edges
                WHERE relation = 'COMPONENT_ON_GAME_OBJECT'
                """
            )
        }
        reference_rows = connection.execute(
            """
            SELECT
                edge.source_id,
                edge.relation,
                edge.target_id,
                edge.property_name,
                edge.source_path,
                edge.source_line,
                source_object.type_name AS component_type,
                source_object.asset_id AS owner_asset_id,
                owner_asset.path AS owner_path,
                target_asset.guid AS target_guid
            FROM edges edge
            JOIN objects source_object
              ON source_object.object_id = edge.source_id
            JOIN assets owner_asset
              ON owner_asset.asset_id = source_object.asset_id
            JOIN assets target_asset
              ON target_asset.asset_id = edge.target_id
            ORDER BY edge.source_path, edge.source_line
            """
        ).fetchall()
    finally:
        connection.close()

    assets: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for row in images:
        absolute = unity_project / Path(row["path"])
        if not absolute.is_file():
            warnings.append(
                {
                    "kind": "missing-visual-asset",
                    "unityGuid": row["guid"],
                    "relativePath": row["path"],
                }
            )
            continue
        assets.append(
            {
                "assetId": row["asset_id"],
                "unityGuid": row["guid"],
                "relativePath": row["path"],
                "contentHash": sha256_file(absolute),
                "assetKind": row["kind"],
            }
        )

    usage_counter: Counter[tuple[Any, ...]] = Counter()
    unresolved_file_ids = 0
    for row in reference_rows:
        if row["target_id"] not in image_asset_ids:
            continue
        file_id = target_file_id(
            unity_project,
            row["source_path"],
            row["source_line"],
            row["target_guid"],
        )
        if file_id is None:
            unresolved_file_ids += 1
        source_game_object = component_game_objects.get(row["source_id"])
        if source_game_object is None:
            source = object_rows.get(row["source_id"])
            if source and source["type_name"] == "GameObject":
                source_game_object = row["source_id"]
        owner_hierarchy = (
            hierarchy_path(source_game_object, object_rows, parents)
            if source_game_object
            else None
        )
        key = (
            row["target_guid"],
            file_id or "",
            row["owner_path"],
            owner_hierarchy or "",
            row["component_type"] or "",
            row["property_name"] or "",
        )
        usage_counter[key] += 1

    usages = [
        {
            "unityGuid": guid,
            "fileId": file_id,
            "ownerPath": owner_path,
            "hierarchyPath": hierarchy or None,
            "componentType": component_type or None,
            "propertyName": property_name or None,
            "referenceCount": count,
        }
        for (
            guid,
            file_id,
            owner_path,
            hierarchy,
            component_type,
            property_name,
        ), count in sorted(usage_counter.items())
    ]
    if unresolved_file_ids:
        warnings.append(
            {
                "kind": "unresolved-target-file-id",
                "count": unresolved_file_ids,
                "explanation": "GUID usage is retained with an empty fileId.",
            }
        )

    return {
        "schema": SCHEMA,
        "projectId": project_id,
        "indexFingerprint": metadata["graphFingerprint"],
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": "unity-project-brain",
            "graphFingerprint": metadata["graphFingerprint"],
            "gitRevision": metadata.get("gitRevision"),
            "policyName": metadata.get("policyName"),
        },
        "assets": assets,
        "usages": usages,
        "warnings": warnings,
        "summary": {
            "visualAssets": len(assets),
            "usageRecords": len(usages),
            "references": sum(item["referenceCount"] for item in usages),
            "unresolvedFileIds": unresolved_file_ids,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--graph", type=Path, required=True)
    export.add_argument("--repository", type=Path, required=True)
    export.add_argument("--unity-project", type=Path, required=True)
    export.add_argument("--project-id", required=True)
    export.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        document = export_visual_context(
            arguments.graph,
            arguments.repository,
            arguments.unity_project,
            arguments.project_id,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(document["summary"], indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
