#!/usr/bin/env python3
"""Plan and safely apply incremental Unity serialized-graph updates."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from project_brain.change_envelope import validate_envelope
from project_brain.unity_graph import (
    META_GUID,
    SERIALIZED_EXTENSIONS,
    asset_id_for_guid,
    asset_id_for_path,
    asset_kind,
    current_git_revision,
    derive_game_object_hierarchy,
    graph_fingerprint,
    graph_stats,
    index_serialized_file,
    insert_asset,
    normalize_project_path,
    sha256_bytes,
    validate_graph,
)


CATALOG_INVALIDATIONS = {
    "roslyn.compilation",
    "roslyn.symbol-catalog",
    "unity.script-symbol-bridge",
}


def normalized_extension(path: str) -> str:
    value = path[:-5] if path.casefold().endswith(".meta") else path
    return Path(value).suffix.casefold()


def is_unity_assets_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip("/").casefold()
    return normalized.startswith("assets/") or "/assets/" in f"/{normalized}"


def action_for_change(change: dict[str, Any]) -> tuple[str, str]:
    invalidations = set(change.get("invalidates", []))
    extension = normalized_extension(change["path"])
    if invalidations & CATALOG_INVALIDATIONS:
        return "full-rebuild", "compiled code or symbol identity changed"
    if not is_unity_assets_path(change["path"]):
        return "ignore", "outside the indexed Unity Assets graph"
    if change["path"].casefold().endswith(".meta"):
        return "full-rebuild", "Unity GUID identity changed"
    if extension in SERIALIZED_EXTENSIONS:
        if change["status"] in {"added", "modified"}:
            return "incremental-serialized", "localized YAML asset update"
        return "full-rebuild", "serialized deletion or rename changes identity"
    if "unity.serialized-objects" in invalidations:
        return "full-rebuild", "serialized format is not incrementally supported"
    return "ignore", "does not affect the Unity object graph"


def build_plan(envelope: dict[str, Any]) -> dict[str, Any]:
    validate_envelope(envelope)
    changes: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for change in envelope["changes"]:
        action, reason = action_for_change(change)
        counts[action] += 1
        changes.append(
            {
                "status": change["status"],
                "path": change["path"],
                "action": action,
                "reason": reason,
            }
        )
    blocking = counts["full-rebuild"] > 0
    return {
        "schemaVersion": 1,
        "envelopeId": envelope["envelopeId"],
        "canApplyIncrementally": not blocking,
        "requiresFullRebuild": blocking,
        "counts": dict(sorted(counts.items())),
        "changes": changes,
    }


def repository_path_to_unity_path(
    repository_path: str,
    repository: Path,
    unity_project: Path,
) -> str:
    unity_prefix = unity_project.relative_to(repository).as_posix().strip("/")
    normalized = repository_path.replace("\\", "/").strip("/")
    if normalized.casefold().startswith("assets/"):
        return normalized
    expected_prefix = f"{unity_prefix}/"
    if not normalized.casefold().startswith(expected_prefix.casefold()):
        raise ValueError(f"Change is outside the Unity project: {repository_path}")
    unity_path = normalized[len(expected_prefix) :]
    if not unity_path.casefold().startswith("assets/"):
        raise ValueError(f"Change is outside Unity Assets: {repository_path}")
    return unity_path


def purge_serialized_source(
    connection: sqlite3.Connection,
    asset_id: str,
    unity_path: str,
) -> None:
    object_ids = [
        row[0]
        for row in connection.execute(
            "SELECT object_id FROM objects WHERE asset_id = ?",
            (asset_id,),
        )
    ]
    if object_ids:
        connection.executemany(
            "DELETE FROM edges WHERE source_id = ?",
            ((object_id,) for object_id in object_ids),
        )
    connection.execute(
        "DELETE FROM edges WHERE source_path = ?",
        (unity_path,),
    )
    connection.execute(
        "DELETE FROM objects WHERE asset_id = ?",
        (asset_id,),
    )


def ensure_local_asset(
    connection: sqlite3.Connection,
    absolute_path: Path,
    unity_project: Path,
) -> str:
    unity_path = normalize_project_path(absolute_path, unity_project)
    row = connection.execute(
        "SELECT asset_id FROM assets WHERE lower(path) = lower(?)",
        (unity_path,),
    ).fetchone()
    if row:
        return row[0]

    meta_path = Path(f"{absolute_path}.meta")
    guid: str | None = None
    meta_hash: str | None = None
    meta_unity_path: str | None = None
    if meta_path.is_file():
        meta_raw = meta_path.read_bytes()
        match = META_GUID.search(meta_raw.decode("utf-8", errors="replace"))
        guid = match.group("guid").casefold() if match else None
        meta_hash = sha256_bytes(meta_raw)
        meta_unity_path = normalize_project_path(meta_path, unity_project)
    resolved_id = asset_id_for_guid(guid) if guid else asset_id_for_path(unity_path)
    insert_asset(
        connection,
        asset_id=resolved_id,
        guid=guid,
        path=unity_path,
        kind=asset_kind(absolute_path),
        meta_path=meta_unity_path,
        content_hash=meta_hash,
        exists_locally=True,
        is_external=False,
    )
    return resolved_id


def apply_incremental(
    repository: Path,
    unity_project: Path,
    database_path: Path,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    plan = build_plan(envelope)
    if plan["requiresFullRebuild"]:
        blocked = [
            item["path"]
            for item in plan["changes"]
            if item["action"] == "full-rebuild"
        ]
        raise ValueError(
            "Incremental apply is unsafe; full rebuild required for: "
            + ", ".join(blocked[:10])
        )
    if not database_path.is_file():
        raise ValueError(f"Graph database does not exist: {database_path}")

    temporary = database_path.with_suffix(database_path.suffix + ".updating")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(database_path, temporary)

    connection = sqlite3.connect(temporary)
    applied_paths: list[str] = []
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM edges WHERE relation = 'GAME_OBJECT_PARENT'"
        )
        path_to_asset_id = {
            row[0].casefold(): row[1]
            for row in connection.execute(
                "SELECT path, asset_id FROM assets WHERE path IS NOT NULL"
            )
        }
        for item in plan["changes"]:
            if item["action"] != "incremental-serialized":
                continue
            unity_path = repository_path_to_unity_path(
                item["path"],
                repository,
                unity_project,
            )
            absolute_path = unity_project / Path(unity_path)
            if not absolute_path.is_file():
                raise ValueError(f"Changed asset does not exist: {absolute_path}")
            asset_id = ensure_local_asset(
                connection,
                absolute_path,
                unity_project,
            )
            purge_serialized_source(connection, asset_id, unity_path)
            path_to_asset_id[unity_path.casefold()] = asset_id
            index_serialized_file(
                connection,
                absolute_path,
                unity_project,
                path_to_asset_id,
            )
            applied_paths.append(unity_path)

        derived_edges = derive_game_object_hierarchy(connection)
        fingerprint = graph_fingerprint(connection)
        metadata = {
            "gitRevision": current_git_revision(repository),
            "graphFingerprint": fingerprint,
            "lastChangeEnvelopeId": envelope["envelopeId"],
            "lastUpdateMode": "incremental-serialized",
        }
        connection.executemany(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            metadata.items(),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    validation = validate_graph(temporary)
    if not validation["passed"]:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            "Incremental graph failed integrity validation: "
            + json.dumps(validation["violations"], ensure_ascii=False)
        )
    os.replace(temporary, database_path)

    connection = sqlite3.connect(database_path)
    try:
        counts = graph_stats(connection)
    finally:
        connection.close()
    return {
        "success": True,
        "mode": "incremental-serialized",
        "envelopeId": envelope["envelopeId"],
        "appliedPaths": applied_paths,
        "derivedHierarchyEdges": derived_edges,
        "graphFingerprint": fingerprint,
        "validation": validation,
        "counts": counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--envelope", type=Path, required=True)
    apply_command = subparsers.add_parser("apply")
    apply_command.add_argument("--repository", type=Path, default=Path.cwd())
    apply_command.add_argument("--unity-project", type=Path, required=True)
    apply_command.add_argument("--database", type=Path, required=True)
    apply_command.add_argument("--envelope", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
        if args.command == "plan":
            result = build_plan(envelope)
        else:
            result = apply_incremental(
                args.repository.resolve(),
                args.unity_project.resolve(),
                args.database.resolve(),
                envelope,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
