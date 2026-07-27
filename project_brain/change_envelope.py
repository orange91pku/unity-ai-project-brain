#!/usr/bin/env python3
"""Collect, merge and validate deterministic Unity Brain change envelopes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from project_brain.index_audit import IndexPolicy


META_GUID = re.compile(rb"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
WORKTREE = "WORKTREE"


@dataclass(frozen=True)
class RawChange:
    status: str
    path: str
    old_path: str | None = None


def run_git(repository: Path, arguments: list[str]) -> bytes:
    process = subprocess.run(
        ["git", "-c", f"safe.directory={repository.as_posix()}", *arguments],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError(
            process.stderr.decode("utf-8", errors="replace").strip()
            or f"git {' '.join(arguments)} failed with {process.returncode}"
        )
    return process.stdout


def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    if not normalized or normalized == ".":
        raise ValueError(f"Invalid project-relative path: {value!r}")
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"Path escapes project root: {value!r}")
    return normalized


def parse_name_status_z(payload: bytes) -> list[RawChange]:
    if not payload:
        return []
    tokens = payload.decode("utf-8", errors="surrogateescape").split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()

    changes: list[RawChange] = []
    index = 0
    while index < len(tokens):
        status_token = tokens[index]
        index += 1
        if not status_token:
            raise ValueError("Empty git status token.")
        status_code = status_token[0]
        if status_code in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise ValueError("Truncated rename/copy record from git.")
            old_path = normalize_path(tokens[index])
            new_path = normalize_path(tokens[index + 1])
            index += 2
            changes.append(RawChange("renamed", new_path, old_path))
            continue

        if index >= len(tokens):
            raise ValueError("Truncated path record from git.")
        path = normalize_path(tokens[index])
        index += 1
        status = {
            "A": "added",
            "M": "modified",
            "D": "deleted",
            "T": "modified",
            "U": "modified",
        }.get(status_code)
        if status is None:
            raise ValueError(f"Unsupported git status: {status_token}")
        changes.append(RawChange(status, path))
    return changes


def resolve_revision(repository: Path, revision: str) -> str:
    return run_git(repository, ["rev-parse", revision]).decode("ascii").strip()


def collect_raw_changes(
    repository: Path,
    base_revision: str,
    target_revision: str,
) -> tuple[str, str, list[RawChange]]:
    resolved_base = resolve_revision(repository, base_revision)
    if target_revision.upper() == WORKTREE:
        tracked = parse_name_status_z(
            run_git(
                repository,
                [
                    "diff",
                    "--name-status",
                    "-z",
                    "--find-renames",
                    resolved_base,
                    "--",
                ],
            )
        )
        untracked_paths = run_git(
            repository,
            ["ls-files", "--others", "--exclude-standard", "-z"],
        ).decode("utf-8", errors="surrogateescape").split("\0")
        untracked = [
            RawChange("added", normalize_path(path))
            for path in untracked_paths
            if path
        ]
        return resolved_base, WORKTREE, coalesce_raw_changes([*tracked, *untracked])

    resolved_target = resolve_revision(repository, target_revision)
    changes = parse_name_status_z(
        run_git(
            repository,
            [
                "diff",
                "--name-status",
                "-z",
                "--find-renames",
                resolved_base,
                resolved_target,
                "--",
            ],
        )
    )
    return resolved_base, resolved_target, coalesce_raw_changes(changes)


def coalesce_raw_changes(changes: Iterable[RawChange]) -> list[RawChange]:
    by_identity: dict[tuple[str | None, str], RawChange] = {}
    for change in changes:
        key = (change.old_path, change.path)
        existing = by_identity.get(key)
        if existing is None or existing.status != "renamed":
            by_identity[key] = change
    return sorted(
        by_identity.values(),
        key=lambda change: (change.path.casefold(), change.old_path or ""),
    )


def policy_exclusion_reason(policy: IndexPolicy, path: str) -> str | None:
    normalized = normalize_path(path)
    prefix_reason = policy.excluded_file_reason(normalized)
    if prefix_reason:
        return prefix_reason
    is_meta = normalized.casefold().endswith(".meta")
    represented_path = normalized[:-5] if is_meta else normalized
    represented_prefix_reason = policy.excluded_file_reason(represented_path)
    if represented_prefix_reason:
        return represented_prefix_reason
    segments = represented_path.split("/")
    directory_segments = segments if is_meta else segments[:-1]
    for segment in directory_segments:
        if segment.casefold() in policy.excluded_directory_names:
            return f"directory:{segment.casefold()}"
    return None


def filter_changes(
    changes: Iterable[RawChange], policy: IndexPolicy
) -> list[RawChange]:
    filtered: list[RawChange] = []
    for change in changes:
        new_excluded = policy_exclusion_reason(policy, change.path) is not None
        old_excluded = (
            policy_exclusion_reason(policy, change.old_path) is not None
            if change.old_path
            else new_excluded
        )
        if change.status != "renamed":
            if not new_excluded:
                filtered.append(change)
            continue
        if old_excluded and new_excluded:
            continue
        if old_excluded:
            filtered.append(RawChange("added", change.path))
        elif new_excluded:
            filtered.append(RawChange("deleted", change.old_path or change.path))
        else:
            filtered.append(change)
    return coalesce_raw_changes(filtered)


def read_revision_file(
    repository: Path,
    revision: str,
    project_path: str,
) -> bytes | None:
    if revision == WORKTREE:
        absolute = repository / project_path
        try:
            return absolute.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            return None
    process = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repository.as_posix()}",
            "show",
            f"{revision}:{project_path}",
        ],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.stdout if process.returncode == 0 else None


def unity_guid_for_change(
    repository: Path,
    change: RawChange,
    base_revision: str,
    target_revision: str,
) -> str | None:
    use_old = change.status == "deleted"
    revision = base_revision if use_old else target_revision
    path = change.old_path if use_old and change.old_path else change.path
    meta_path = path if path.casefold().endswith(".meta") else f"{path}.meta"
    content = read_revision_file(repository, revision, meta_path)
    if content is None and change.status == "renamed":
        old_meta = (
            change.old_path
            if change.old_path and change.old_path.casefold().endswith(".meta")
            else f"{change.old_path}.meta"
            if change.old_path
            else None
        )
        if old_meta:
            content = read_revision_file(repository, base_revision, old_meta)
    if content is None:
        return None
    match = META_GUID.search(content)
    return match.group(1).decode("ascii").casefold() if match else None


def content_hash_for_change(
    repository: Path,
    change: RawChange,
    target_revision: str,
) -> str | None:
    if change.status == "deleted":
        return None
    content = read_revision_file(repository, target_revision, change.path)
    return hashlib.sha256(content).hexdigest() if content is not None else None


def invalidations_for(path: str, status: str) -> list[str]:
    normalized = path.casefold()
    extension = Path(normalized.removesuffix(".meta")).suffix
    invalidations = {"gitnexus.path"}
    if normalized.endswith(".meta"):
        invalidations.update(
            {
                "unity.asset-identity",
                "unity.references",
            }
        )
    if extension == ".cs":
        invalidations.update(
            {
                "gitnexus.code",
                "roslyn.symbol-catalog",
                "unity.script-symbol-bridge",
            }
        )
    if extension in {
        ".unity",
        ".prefab",
        ".asset",
        ".mat",
        ".controller",
        ".overridecontroller",
        ".anim",
        ".spriteatlas",
        ".playable",
        ".mask",
    }:
        invalidations.update(
            {
                "unity.serialized-objects",
                "unity.references",
            }
        )
    if extension in {".asmdef", ".asmref"}:
        invalidations.update(
            {
                "roslyn.compilation",
                "roslyn.symbol-catalog",
            }
        )
    if normalized in {
        "packages/manifest.json",
        "packages/packages-lock.json",
    }:
        invalidations.update(
            {
                "unity.packages",
                "roslyn.compilation",
                "roslyn.symbol-catalog",
            }
        )
    if normalized.startswith("projectsettings/"):
        invalidations.add("unity.project-settings")
    if status in {"deleted", "renamed"}:
        invalidations.add("unity.identity-lineage")
    return sorted(invalidations)


def load_policy(policy_path: Path) -> tuple[IndexPolicy, str]:
    document = json.loads(policy_path.read_text(encoding="utf-8"))
    return IndexPolicy(document), document.get("name") or "unknown"


def canonical_envelope_id(document: dict[str, Any]) -> str:
    identity_document = {
        "schemaVersion": document["schemaVersion"],
        "projectId": document["projectId"],
        "source": document["source"],
        "baseRevision": document["baseRevision"],
        "targetRevision": document["targetRevision"],
        "policyVersion": document["policyVersion"],
        "changes": document["changes"],
    }
    payload = json.dumps(
        identity_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"change:{hashlib.sha256(payload).hexdigest()}"


def merge_change_sequence(changes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for raw_change in changes:
        change = dict(raw_change)
        path_key = normalize_path(change["path"]).casefold()
        old_path = change.get("oldPath")
        existing = by_path.get(path_key)

        if change["status"] == "renamed" and old_path:
            old_key = normalize_path(old_path).casefold()
            origin = by_path.pop(old_key, None)
            if origin and origin["status"] == "added":
                change["status"] = "added"
                change["oldPath"] = None
            elif origin and origin["status"] == "renamed":
                change["oldPath"] = origin.get("oldPath")

        existing = by_path.get(path_key)
        if change["status"] == "modified" and existing:
            if existing["status"] in {"added", "renamed"}:
                preserved = dict(existing)
                for key in (
                    "unityGuid",
                    "contentHash",
                    "lane",
                    "invalidates",
                ):
                    if change.get(key) is not None:
                        preserved[key] = change[key]
                change = preserved
        elif change["status"] == "deleted" and existing:
            if existing["status"] == "added":
                by_path.pop(path_key, None)
                continue
            change["oldPath"] = None
            change["contentHash"] = None
        elif (
            change["status"] == "added"
            and existing
            and existing["status"] == "deleted"
        ):
            change["status"] = "modified"
            change["oldPath"] = None

        by_path[path_key] = change
    return sorted(
        by_path.values(),
        key=lambda change: (
            normalize_path(change["path"]).casefold(),
            change.get("oldPath") or "",
        ),
    )


def merge_envelopes(
    documents: Iterable[dict[str, Any]],
    *,
    project_id: str | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    ordered = sorted(
        list(documents),
        key=lambda document: (
            document.get("generatedUtc") or "",
            document.get("envelopeId") or "",
        ),
    )
    if not ordered:
        raise ValueError("At least one envelope is required for merge.")
    for document in ordered:
        validate_envelope(document)
    resolved_project_id = project_id or ordered[0]["projectId"]
    resolved_policy = policy_version or ordered[0]["policyVersion"]
    for document in ordered:
        if document["projectId"] != resolved_project_id and project_id is None:
            raise ValueError("Cannot merge envelopes from different projects.")
        if (
            document["policyVersion"] != resolved_policy
            and policy_version is None
        ):
            raise ValueError("Cannot merge envelopes with different policies.")

    merged_changes = merge_change_sequence(
        change
        for document in ordered
        for change in document["changes"]
    )
    merged: dict[str, Any] = {
        "schemaVersion": 1,
        "envelopeId": "",
        "projectId": resolved_project_id,
        "source": "merged",
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "baseRevision": ordered[0]["baseRevision"],
        "targetRevision": ordered[-1]["targetRevision"],
        "policyVersion": resolved_policy,
        "changes": merged_changes,
    }
    merged["envelopeId"] = canonical_envelope_id(merged)
    validate_envelope(merged)
    return merged


def build_git_envelope(
    repository: Path,
    project_id: str,
    base_revision: str,
    target_revision: str,
    policy_path: Path,
) -> dict[str, Any]:
    policy, policy_version = load_policy(policy_path)
    resolved_base, resolved_target, raw_changes = collect_raw_changes(
        repository,
        base_revision,
        target_revision,
    )
    raw_changes = filter_changes(raw_changes, policy)
    changes: list[dict[str, Any]] = []
    for raw_change in raw_changes:
        path_for_lane = Path(raw_change.path.removesuffix(".meta"))
        item = {
            "status": raw_change.status,
            "path": raw_change.path,
            "oldPath": raw_change.old_path,
            "unityGuid": unity_guid_for_change(
                repository,
                raw_change,
                resolved_base,
                resolved_target,
            ),
            "contentHash": content_hash_for_change(
                repository,
                raw_change,
                resolved_target,
            ),
            "lane": (
                "assetIdentity"
                if raw_change.path.casefold().endswith(".meta")
                else policy.lane_for(path_for_lane)
            ),
            "invalidates": invalidations_for(
                raw_change.path,
                raw_change.status,
            ),
        }
        changes.append(item)

    document: dict[str, Any] = {
        "schemaVersion": 1,
        "envelopeId": "",
        "projectId": project_id,
        "source": "git-diff",
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "baseRevision": resolved_base,
        "targetRevision": resolved_target,
        "policyVersion": policy_version,
        "changes": changes,
    }
    document["envelopeId"] = canonical_envelope_id(document)
    validate_envelope(document)
    return document


def validate_envelope(document: dict[str, Any]) -> None:
    if document.get("schemaVersion") != 1:
        raise ValueError("Only change envelope schemaVersion 1 is supported.")
    if not isinstance(document.get("projectId"), str) or not document["projectId"]:
        raise ValueError("projectId is required.")
    if document.get("source") not in {
        "git-diff",
        "unity-asset-postprocessor",
        "merged",
    }:
        raise ValueError(f"Unsupported envelope source: {document.get('source')}")
    if not isinstance(document.get("changes"), list):
        raise ValueError("changes must be an array.")

    allowed_statuses = {"added", "modified", "deleted", "renamed"}
    seen: set[tuple[str | None, str]] = set()
    for index, change in enumerate(document["changes"]):
        if change.get("status") not in allowed_statuses:
            raise ValueError(f"changes[{index}] has an invalid status.")
        path = normalize_path(change.get("path") or "")
        old_path = change.get("oldPath")
        if old_path is not None:
            old_path = normalize_path(old_path)
        if change["status"] == "renamed" and old_path is None:
            raise ValueError(f"changes[{index}] rename requires oldPath.")
        guid = change.get("unityGuid")
        if guid is not None and not re.fullmatch(r"[0-9a-f]{32}", guid):
            raise ValueError(f"changes[{index}] has an invalid Unity GUID.")
        content_hash = change.get("contentHash")
        if content_hash is not None and not re.fullmatch(
            r"[0-9a-f]{64}", content_hash
        ):
            raise ValueError(f"changes[{index}] has an invalid content hash.")
        invalidates = change.get("invalidates")
        if not isinstance(invalidates, list) or len(set(invalidates)) != len(
            invalidates
        ):
            raise ValueError(
                f"changes[{index}] invalidates must contain unique values."
            )
        identity = (old_path, path)
        if identity in seen:
            raise ValueError(f"Duplicate change identity: {identity}")
        seen.add(identity)

    expected_id = canonical_envelope_id(document)
    if document.get("envelopeId") != expected_id:
        raise ValueError(
            f"Envelope ID mismatch: expected {expected_id}, "
            f"received {document.get('envelopeId')}"
        )


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser(
        "collect-git", help="Collect a Git diff into a change envelope."
    )
    collect.add_argument("--repository", type=Path, default=Path.cwd())
    collect.add_argument("--project-id", required=True)
    collect.add_argument("--base", default="HEAD")
    collect.add_argument("--target", default=WORKTREE)
    collect.add_argument(
        "--policy",
        type=Path,
        default=Path("config/unity-brain-index-policy.json"),
    )
    collect.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="Validate an existing change envelope."
    )
    validate.add_argument("envelope", type=Path)
    merge = subparsers.add_parser(
        "merge",
        help="Coalesce ordered Git/Unity envelopes into one deterministic delta.",
    )
    merge.add_argument("inputs", type=Path, nargs="*")
    merge.add_argument("--input-directory", type=Path)
    merge.add_argument("--project-id")
    merge.add_argument("--policy-version")
    merge.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "collect-git":
            document = build_git_envelope(
                args.repository.resolve(),
                args.project_id,
                args.base,
                args.target,
                args.policy.resolve(),
            )
            write_json_atomic(args.output.resolve(), document)
            print(
                json.dumps(
                    {
                        "success": True,
                        "envelopeId": document["envelopeId"],
                        "changeCount": len(document["changes"]),
                        "output": str(args.output.resolve()),
                    },
                    indent=2,
                )
            )
        elif args.command == "validate":
            document = json.loads(
                args.envelope.read_text(encoding="utf-8")
            )
            validate_envelope(document)
            print(
                json.dumps(
                    {
                        "success": True,
                        "envelopeId": document["envelopeId"],
                        "changeCount": len(document["changes"]),
                    },
                    indent=2,
                )
            )
        elif args.command == "merge":
            input_paths = list(args.inputs)
            if args.input_directory:
                input_paths.extend(
                    sorted(args.input_directory.glob("*.json"))
                )
            documents = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in input_paths
            ]
            document = merge_envelopes(
                documents,
                project_id=args.project_id,
                policy_version=args.policy_version,
            )
            write_json_atomic(args.output.resolve(), document)
            print(
                json.dumps(
                    {
                        "success": True,
                        "envelopeId": document["envelopeId"],
                        "inputCount": len(input_paths),
                        "changeCount": len(document["changes"]),
                        "output": str(args.output.resolve()),
                    },
                    indent=2,
                )
            )
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
