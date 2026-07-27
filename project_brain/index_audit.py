#!/usr/bin/env python3
"""Audit a repository before it becomes input to a Unity Project Brain index."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LaneStats:
    files: int = 0
    bytes: int = 0

    def add(self, size: int) -> None:
        self.files += 1
        self.bytes += size

    def as_dict(self) -> dict[str, int]:
        return {"files": self.files, "bytes": self.bytes}


@dataclass
class AuditResult:
    repository: str
    policy: str
    scanned: LaneStats = field(default_factory=LaneStats)
    accepted: LaneStats = field(default_factory=LaneStats)
    excluded: LaneStats = field(default_factory=LaneStats)
    lanes: dict[str, LaneStats] = field(default_factory=dict)
    excluded_by_reason: Counter[str] = field(default_factory=Counter)
    gate_violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "repository": self.repository,
            "policy": self.policy,
            "scanned": self.scanned.as_dict(),
            "accepted": self.accepted.as_dict(),
            "excluded": self.excluded.as_dict(),
            "lanes": {
                name: stats.as_dict()
                for name, stats in sorted(self.lanes.items())
            },
            "excludedByReason": dict(sorted(self.excluded_by_reason.items())),
            "gate": {
                "passed": not self.gate_violations,
                "violations": self.gate_violations,
            },
        }


class IndexPolicy:
    def __init__(self, document: dict[str, Any]) -> None:
        if document.get("schemaVersion") != 1:
            raise ValueError("Only index policy schemaVersion 1 is supported.")

        excluded = document.get("exclude", {})
        self.excluded_directory_names = {
            value.casefold() for value in excluded.get("directoryNames", [])
        }
        self.excluded_path_prefixes = tuple(
            self._normalize(value).casefold().rstrip("/")
            for value in excluded.get("pathPrefixes", [])
        )
        self.lane_extensions: dict[str, set[str]] = {
            lane_name: {
                extension.casefold()
                for extension in lane_config.get("extensions", [])
            }
            for lane_name, lane_config in document.get("lanes", {}).items()
        }
        self.forbidden_directory_names = {
            value.casefold()
            for value in document.get("gates", {}).get(
                "forbiddenAcceptedDirectoryNames", []
            )
        }

    @staticmethod
    def _normalize(value: str) -> str:
        return value.replace("\\", "/").strip("/")

    def excluded_directory_reason(
        self, relative_directory: str, directory_name: str
    ) -> str | None:
        if directory_name.casefold() in self.excluded_directory_names:
            return f"directory:{directory_name.casefold()}"

        normalized = self._normalize(relative_directory).casefold()
        for prefix in self.excluded_path_prefixes:
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return f"path:{prefix}"
        return None

    def excluded_file_reason(self, relative_file: str) -> str | None:
        normalized = self._normalize(relative_file).casefold()
        for prefix in self.excluded_path_prefixes:
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return f"path:{prefix}"
        return None

    def lane_for(self, file_path: Path) -> str:
        suffix = file_path.suffix.casefold()
        for lane_name, extensions in self.lane_extensions.items():
            if suffix in extensions:
                return lane_name
        return "other"

    def forbidden_segments(self, relative_file: str) -> list[str]:
        return [
            segment
            for segment in self._normalize(relative_file).split("/")[:-1]
            if segment.casefold() in self.forbidden_directory_names
        ]


def directory_totals(root: Path) -> LaneStats:
    totals = LaneStats()
    for directory, _, file_names in os.walk(root):
        for file_name in file_names:
            path = Path(directory, file_name)
            try:
                totals.add(path.stat().st_size)
            except (FileNotFoundError, PermissionError, OSError):
                continue
    return totals


def audit(repository: Path, policy_path: Path) -> AuditResult:
    policy_document = json.loads(policy_path.read_text(encoding="utf-8"))
    policy = IndexPolicy(policy_document)
    result = AuditResult(
        repository=str(repository.resolve()),
        policy=str(policy_path.resolve()),
        lanes={name: LaneStats() for name in policy.lane_extensions},
    )
    result.lanes["other"] = LaneStats()

    for directory, directory_names, file_names in os.walk(repository, topdown=True):
        current = Path(directory)
        kept_directories: list[str] = []

        for directory_name in sorted(directory_names):
            child = current / directory_name
            relative = child.relative_to(repository).as_posix()
            reason = policy.excluded_directory_reason(relative, directory_name)
            if reason:
                totals = directory_totals(child)
                result.scanned.files += totals.files
                result.scanned.bytes += totals.bytes
                result.excluded.files += totals.files
                result.excluded.bytes += totals.bytes
                result.excluded_by_reason[reason] += totals.files
            else:
                kept_directories.append(directory_name)

        directory_names[:] = kept_directories

        for file_name in sorted(file_names):
            file_path = current / file_name
            relative = file_path.relative_to(repository).as_posix()
            try:
                size = file_path.stat().st_size
            except (FileNotFoundError, PermissionError, OSError):
                continue

            result.scanned.add(size)
            reason = policy.excluded_file_reason(relative)
            if reason:
                result.excluded.add(size)
                result.excluded_by_reason[reason] += 1
                continue

            result.accepted.add(size)
            result.lanes[policy.lane_for(file_path)].add(size)
            forbidden = policy.forbidden_segments(relative)
            if forbidden:
                result.gate_violations.append(
                    f"{relative}: forbidden directory segment(s) {forbidden}"
                )

    return result


def human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def print_human(result: AuditResult) -> None:
    print(f"Repository: {result.repository}")
    print(
        "Scanned: "
        f"{result.scanned.files:,} files / {human_bytes(result.scanned.bytes)}"
    )
    print(
        "Accepted: "
        f"{result.accepted.files:,} files / {human_bytes(result.accepted.bytes)}"
    )
    print(
        "Excluded: "
        f"{result.excluded.files:,} files / {human_bytes(result.excluded.bytes)}"
    )
    print("Lanes:")
    for name, stats in sorted(result.lanes.items()):
        print(f"  {name:16} {stats.files:8,} files  {human_bytes(stats.bytes):>12}")
    print("Largest exclusion reasons:")
    for reason, count in result.excluded_by_reason.most_common(12):
        print(f"  {reason:44} {count:8,} files")
    print(f"Gate: {'PASS' if not result.gate_violations else 'FAIL'}")
    for violation in result.gate_violations[:20]:
        print(f"  {violation}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to audit (default: current directory).",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("config/unity-brain-index-policy.json"),
        help="Path to the machine-readable policy.",
    )
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository = args.repo.resolve()
    policy_path = args.policy.resolve()
    if not repository.is_dir():
        print(f"Repository does not exist: {repository}", file=sys.stderr)
        return 2
    if not policy_path.is_file():
        print(f"Policy does not exist: {policy_path}", file=sys.stderr)
        return 2

    result = audit(repository, policy_path)
    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print_human(result)
    return 0 if not result.gate_violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
