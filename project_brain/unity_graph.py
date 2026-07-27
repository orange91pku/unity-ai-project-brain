#!/usr/bin/env python3
"""Build and query an evidence-backed Unity asset/object graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from project_brain.index_audit import IndexPolicy


SCHEMA_VERSION = 1
UNITY_HEADER = re.compile(
    r"^--- !u!(?P<class_id>-?\d+) &(?P<file_id>-?\d+)(?: stripped)?\s*$"
)
ROOT_TYPE = re.compile(r"^(?P<type_name>[A-Za-z_][A-Za-z0-9_]*):\s*$")
ROOT_NAME = re.compile(r"^  m_Name:\s*(?P<name>.*)$")
PROPERTY = re.compile(
    r"^(?P<indent>\s*)(?:-\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*):"
)
PAIR = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<value>[^,}\s]+)")
META_GUID = re.compile(r"^guid:\s*(?P<guid>[0-9a-fA-F]{32})\s*$", re.MULTILINE)

SERIALIZED_EXTENSIONS = {
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
}


@dataclass(frozen=True)
class UnityReference:
    property_name: str
    file_id: str
    guid: str | None
    type_id: str | None
    line: int
    evidence: str


@dataclass
class UnityDocument:
    class_id: int
    file_id: str
    type_name: str
    name: str | None
    start_line: int
    references: list[UnityReference]


@dataclass
class BuildStats:
    meta_files: int = 0
    serialized_files: int = 0
    skipped_files: int = 0


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_project_path(path: Path, unity_project: Path) -> str:
    return path.relative_to(unity_project).as_posix()


def asset_id_for_guid(guid: str) -> str:
    return f"asset:{guid.casefold()}"


def asset_id_for_path(path: str) -> str:
    digest = hashlib.sha256(path.casefold().encode("utf-8")).hexdigest()[:24]
    return f"path:{digest}"


def object_id(asset_id: str, file_id: str) -> str:
    return f"object:{asset_id}:{file_id}"


def simple_scalar(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:-1]
        if quote == "'":
            value = value.replace("''", "'")
    return value


def parse_reference_blob(
    blob: str, property_name: str, line: int, evidence: str
) -> list[UnityReference]:
    references: list[UnityReference] = []
    for match in re.finditer(r"\{(?P<body>[^{}]+)\}", blob, re.DOTALL):
        pairs = {
            pair.group("name"): pair.group("value")
            for pair in PAIR.finditer(match.group("body"))
        }
        file_id = pairs.get("fileID")
        if file_id is None:
            continue
        guid = pairs.get("guid")
        references.append(
            UnityReference(
                property_name=property_name,
                file_id=file_id,
                guid=guid.casefold() if guid else None,
                type_id=pairs.get("type"),
                line=line,
                evidence=evidence.strip(),
            )
        )
    return references


def parse_document(
    class_id: int, file_id: str, start_line: int, lines: list[str]
) -> UnityDocument:
    type_name = f"Class{class_id}"
    name: str | None = None
    references: list[UnityReference] = []
    containers: dict[int, str] = {}
    index = 0

    for line in lines:
        type_match = ROOT_TYPE.match(line)
        if type_match:
            type_name = type_match.group("type_name")
            break

    while index < len(lines):
        line = lines[index]
        name_match = ROOT_NAME.match(line)
        if name_match and name is None:
            name = simple_scalar(name_match.group("name"))

        property_match = PROPERTY.match(line)
        indent = len(line) - len(line.lstrip(" "))
        property_name = (
            property_match.group("name") if property_match else containers.get(indent, "")
        )
        if property_match and line.rstrip().endswith(":"):
            containers[indent] = property_name
            for existing_indent in list(containers):
                if existing_indent > indent:
                    del containers[existing_indent]

        if "{" not in line:
            index += 1
            continue

        first_line = index
        blob_lines = [line]
        brace_balance = line.count("{") - line.count("}")
        while brace_balance > 0 and index + 1 < len(lines):
            index += 1
            continuation = lines[index]
            blob_lines.append(continuation)
            brace_balance += continuation.count("{") - continuation.count("}")

        blob = " ".join(blob_lines)
        if not property_name:
            property_name = containers.get(indent - 2, "")
        references.extend(
            parse_reference_blob(
                blob,
                property_name or "reference",
                start_line + first_line,
                "\n".join(blob_lines),
            )
        )
        index += 1

    return UnityDocument(
        class_id=class_id,
        file_id=file_id,
        type_name=type_name,
        name=name,
        start_line=start_line,
        references=references,
    )


def parse_unity_yaml(text: str) -> list[UnityDocument]:
    lines = text.splitlines()
    documents: list[UnityDocument] = []
    current_header: tuple[int, str, int] | None = None
    current_lines: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        match = UNITY_HEADER.match(line)
        if match:
            if current_header:
                documents.append(parse_document(*current_header, current_lines))
            current_header = (
                int(match.group("class_id")),
                match.group("file_id"),
                line_number + 1,
            )
            current_lines = []
        elif current_header:
            current_lines.append(line)

    if current_header:
        documents.append(parse_document(*current_header, current_lines))
    return documents


def load_policy(policy_path: Path) -> IndexPolicy:
    return IndexPolicy(json.loads(policy_path.read_text(encoding="utf-8")))


def iter_files(
    assets_root: Path, repository: Path, policy: IndexPolicy
) -> Iterator[Path]:
    for directory, directory_names, file_names in os.walk(assets_root, topdown=True):
        current = Path(directory)
        kept: list[str] = []
        for directory_name in sorted(directory_names):
            child = current / directory_name
            relative = child.relative_to(repository).as_posix()
            if not policy.excluded_directory_reason(relative, directory_name):
                kept.append(directory_name)
        directory_names[:] = kept

        for file_name in sorted(file_names):
            path = current / file_name
            relative = path.relative_to(repository).as_posix()
            if not policy.excluded_file_reason(relative):
                yield path


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        -- This database is built into a temporary file and atomically promoted.
        -- A crash can discard the temporary file, so durable per-row journaling
        -- only adds latency and Windows file locks without improving safety.
        PRAGMA journal_mode = MEMORY;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;
        PRAGMA foreign_keys = OFF;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            guid TEXT UNIQUE,
            path TEXT UNIQUE,
            kind TEXT NOT NULL,
            meta_path TEXT,
            content_hash TEXT,
            exists_locally INTEGER NOT NULL,
            is_external INTEGER NOT NULL
        );

        CREATE TABLE objects (
            object_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            file_id TEXT NOT NULL,
            class_id INTEGER NOT NULL,
            type_name TEXT NOT NULL,
            name TEXT,
            source_path TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            UNIQUE(asset_id, file_id)
        );

        CREATE TABLE code_symbols (
            symbol_id TEXT PRIMARY KEY,
            roslyn_key TEXT NOT NULL UNIQUE,
            documentation_id TEXT,
            kind TEXT NOT NULL,
            subkind TEXT,
            assembly_name TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            namespace_name TEXT NOT NULL,
            metadata_name TEXT,
            containing_symbol_id TEXT,
            containing_roslyn_key TEXT,
            containing_type_metadata_name TEXT,
            accessibility TEXT NOT NULL,
            is_static INTEGER NOT NULL,
            is_script_file INTEGER NOT NULL,
            is_unity_object INTEGER NOT NULL,
            is_mono_behaviour INTEGER NOT NULL,
            is_scriptable_object INTEGER NOT NULL,
            is_partial INTEGER NOT NULL,
            base_types_json TEXT NOT NULL
        );

        CREATE TABLE symbol_declarations (
            symbol_id TEXT NOT NULL,
            project_relative_path TEXT NOT NULL,
            line INTEGER NOT NULL,
            column_number INTEGER NOT NULL,
            span_start INTEGER NOT NULL,
            span_length INTEGER NOT NULL,
            PRIMARY KEY(symbol_id, project_relative_path, span_start)
        );

        CREATE TABLE script_symbol_resolution (
            asset_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            candidate_count INTEGER NOT NULL
        );

        CREATE TABLE script_symbol_links (
            asset_id TEXT NOT NULL,
            symbol_id TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY(asset_id, symbol_id)
        );

        CREATE TABLE edges (
            edge_id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_id TEXT NOT NULL,
            property_name TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            evidence_hash TEXT NOT NULL,
            UNIQUE(
                source_id,
                relation,
                target_id,
                property_name,
                source_path,
                source_line
            )
        );

        CREATE INDEX assets_path_idx ON assets(path);
        CREATE INDEX objects_asset_idx ON objects(asset_id);
        CREATE INDEX objects_name_idx ON objects(name);
        CREATE INDEX code_symbols_name_idx
            ON code_symbols(name, kind, assembly_name);
        CREATE INDEX code_symbols_containing_idx
            ON code_symbols(containing_symbol_id);
        CREATE INDEX symbol_declarations_path_idx
            ON symbol_declarations(project_relative_path);
        CREATE INDEX edges_source_idx ON edges(source_id, relation);
        CREATE INDEX edges_target_idx ON edges(target_id, relation);
        """
    )


def asset_kind(asset_path: Path, is_directory: bool = False) -> str:
    if is_directory:
        return "folder"
    extension = asset_path.suffix.casefold()
    return {
        ".cs": "script",
        ".unity": "scene",
        ".prefab": "prefab",
        ".asset": "serializedAsset",
        ".mat": "material",
        ".controller": "animatorController",
        ".anim": "animation",
    }.get(extension, extension.removeprefix(".") or "file")


def insert_asset(
    connection: sqlite3.Connection,
    *,
    asset_id: str,
    guid: str | None,
    path: str | None,
    kind: str,
    meta_path: str | None,
    content_hash: str | None,
    exists_locally: bool,
    is_external: bool,
) -> None:
    connection.execute(
        """
        INSERT INTO assets(
            asset_id, guid, path, kind, meta_path, content_hash,
            exists_locally, is_external
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            guid = COALESCE(excluded.guid, assets.guid),
            path = COALESCE(excluded.path, assets.path),
            kind = CASE
                WHEN excluded.exists_locally = 1 THEN excluded.kind
                ELSE assets.kind
            END,
            meta_path = COALESCE(excluded.meta_path, assets.meta_path),
            content_hash = COALESCE(excluded.content_hash, assets.content_hash),
            exists_locally = MAX(assets.exists_locally, excluded.exists_locally),
            is_external = MIN(assets.is_external, excluded.is_external)
        """,
        (
            asset_id,
            guid,
            path,
            kind,
            meta_path,
            content_hash,
            int(exists_locally),
            int(is_external),
        ),
    )


def insert_edge(
    connection: sqlite3.Connection,
    source_id: str,
    relation: str,
    target_id: str,
    property_name: str,
    source_path: str,
    source_line: int,
    evidence: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO edges(
            source_id, relation, target_id, property_name,
            source_path, source_line, evidence_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            relation,
            target_id,
            property_name,
            source_path,
            source_line,
            sha256_bytes(evidence.encode("utf-8")),
        ),
    )


def collect_assets(
    connection: sqlite3.Connection,
    files: Iterable[Path],
    unity_project: Path,
) -> tuple[dict[str, str], BuildStats]:
    path_to_asset_id: dict[str, str] = {}
    stats = BuildStats()

    for meta_path in (path for path in files if path.suffix.casefold() == ".meta"):
        try:
            raw = meta_path.read_bytes()
        except OSError:
            stats.skipped_files += 1
            continue
        match = META_GUID.search(raw.decode("utf-8", errors="replace"))
        if not match:
            stats.skipped_files += 1
            continue

        asset_path = Path(str(meta_path)[: -len(".meta")])
        project_path = normalize_project_path(asset_path, unity_project)
        meta_project_path = normalize_project_path(meta_path, unity_project)
        guid = match.group("guid").casefold()
        resolved_asset_id = asset_id_for_guid(guid)
        path_to_asset_id[project_path.casefold()] = resolved_asset_id
        insert_asset(
            connection,
            asset_id=resolved_asset_id,
            guid=guid,
            path=project_path,
            kind=asset_kind(asset_path, asset_path.is_dir()),
            meta_path=meta_project_path,
            content_hash=sha256_bytes(raw),
            exists_locally=asset_path.exists(),
            is_external=False,
        )
        stats.meta_files += 1

    return path_to_asset_id, stats


def relation_for(reference: UnityReference, document: UnityDocument) -> str:
    property_name = reference.property_name
    if property_name == "component" and document.type_name == "GameObject":
        return "GAME_OBJECT_HAS_COMPONENT"
    return {
        "m_GameObject": "COMPONENT_ON_GAME_OBJECT",
        "m_Script": "COMPONENT_USES_SCRIPT",
        "m_SourcePrefab": "PREFAB_INSTANCE_SOURCE",
        "m_CorrespondingSourceObject": "CORRESPONDS_TO_SOURCE_OBJECT",
        "m_PrefabInstance": "PART_OF_PREFAB_INSTANCE",
        "m_Father": "TRANSFORM_PARENT",
    }.get(property_name, "REFERENCES")


def index_serialized_file(
    connection: sqlite3.Connection,
    path: Path,
    unity_project: Path,
    path_to_asset_id: dict[str, str],
) -> None:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    project_path = normalize_project_path(path, unity_project)
    current_asset_id = path_to_asset_id.get(project_path.casefold())
    if current_asset_id is None:
        current_asset_id = asset_id_for_path(project_path)
        insert_asset(
            connection,
            asset_id=current_asset_id,
            guid=None,
            path=project_path,
            kind=asset_kind(path),
            meta_path=None,
            content_hash=sha256_bytes(raw),
            exists_locally=True,
            is_external=False,
        )
    else:
        connection.execute(
            "UPDATE assets SET content_hash = ? WHERE asset_id = ?",
            (sha256_bytes(raw), current_asset_id),
        )

    kind_row = connection.execute(
        "SELECT kind FROM assets WHERE asset_id = ?", (current_asset_id,)
    ).fetchone()
    current_kind = kind_row[0] if kind_row else asset_kind(path)

    for document in parse_unity_yaml(text):
        current_object_id = object_id(current_asset_id, document.file_id)
        connection.execute(
            """
            INSERT OR REPLACE INTO objects(
                object_id, asset_id, file_id, class_id, type_name,
                name, source_path, source_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current_object_id,
                current_asset_id,
                document.file_id,
                document.class_id,
                document.type_name,
                document.name,
                project_path,
                document.start_line,
            ),
        )
        insert_edge(
            connection,
            current_asset_id,
            "ASSET_CONTAINS_OBJECT",
            current_object_id,
            "",
            project_path,
            document.start_line,
            f"{document.class_id}:{document.file_id}:{document.type_name}",
        )
        if document.type_name == "GameObject":
            relation = (
                "SCENE_CONTAINS_GAME_OBJECT"
                if current_kind == "scene"
                else "PREFAB_CONTAINS_GAME_OBJECT"
                if current_kind == "prefab"
                else "ASSET_CONTAINS_GAME_OBJECT"
            )
            insert_edge(
                connection,
                current_asset_id,
                relation,
                current_object_id,
                "",
                project_path,
                document.start_line,
                document.name or document.type_name,
            )

        for reference in document.references:
            if reference.file_id == "0" and not reference.guid:
                continue
            relation = relation_for(reference, document)
            if reference.guid:
                target_asset_id = asset_id_for_guid(reference.guid)
                insert_asset(
                    connection,
                    asset_id=target_asset_id,
                    guid=reference.guid,
                    path=None,
                    kind="external",
                    meta_path=None,
                    content_hash=None,
                    exists_locally=False,
                    is_external=True,
                )
                target_id = (
                    object_id(target_asset_id, reference.file_id)
                    if relation == "CORRESPONDS_TO_SOURCE_OBJECT"
                    else target_asset_id
                )
                insert_edge(
                    connection,
                    current_asset_id,
                    "ASSET_REFERENCES_ASSET",
                    target_asset_id,
                    reference.property_name,
                    project_path,
                    reference.line,
                    reference.evidence,
                )
            else:
                target_id = object_id(current_asset_id, reference.file_id)

            insert_edge(
                connection,
                current_object_id,
                relation,
                target_id,
                reference.property_name,
                project_path,
                reference.line,
                reference.evidence,
            )


def derive_game_object_hierarchy(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT
            child_go.target_id,
            parent_go.target_id,
            parent_ref.source_path,
            parent_ref.source_line,
            parent_ref.evidence_hash
        FROM edges parent_ref
        JOIN edges child_go
          ON child_go.source_id = parent_ref.source_id
         AND child_go.relation = 'COMPONENT_ON_GAME_OBJECT'
        JOIN edges parent_go
          ON parent_go.source_id = parent_ref.target_id
         AND parent_go.relation = 'COMPONENT_ON_GAME_OBJECT'
        WHERE parent_ref.relation = 'TRANSFORM_PARENT'
        """
    ).fetchall()
    for child_id, parent_id, source_path, source_line, evidence_hash in rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO edges(
                source_id, relation, target_id, property_name,
                source_path, source_line, evidence_hash
            ) VALUES (?, 'GAME_OBJECT_PARENT', ?, 'm_Father', ?, ?, ?)
            """,
            (child_id, parent_id, source_path, source_line, evidence_hash),
        )
    return len(rows)


def import_symbol_catalog(
    connection: sqlite3.Connection,
    catalog_path: Path,
) -> dict[str, int | str]:
    raw = catalog_path.read_bytes()
    document = json.loads(raw)
    if document.get("schemaVersion") != 1:
        raise ValueError(
            f"Unsupported symbol catalog schema: "
            f"{document.get('schemaVersion')}"
        )

    symbols = document.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("Symbol catalog does not contain a symbols array.")

    types_by_path: dict[str, list[str]] = {}
    unity_types_by_path: dict[str, list[str]] = {}
    declarations_count = 0
    for symbol in symbols:
        symbol_id = symbol["symbolId"]
        containing_symbol_id = symbol.get("containingSymbolId")
        declarations = symbol.get("declarations") or []
        connection.execute(
            """
            INSERT INTO code_symbols(
                symbol_id, roslyn_key, documentation_id, kind, subkind,
                assembly_name, name, qualified_name, namespace_name,
                metadata_name, containing_symbol_id, containing_roslyn_key,
                containing_type_metadata_name, accessibility, is_static,
                is_script_file, is_unity_object, is_mono_behaviour,
                is_scriptable_object, is_partial, base_types_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                symbol_id,
                symbol["roslynKey"],
                symbol.get("documentationId"),
                symbol["kind"],
                symbol.get("subkind"),
                symbol["assemblyName"],
                symbol["name"],
                symbol["qualifiedName"],
                symbol.get("namespaceName") or "",
                symbol.get("metadataName"),
                containing_symbol_id,
                symbol.get("containingRoslynKey"),
                symbol.get("containingTypeMetadataName"),
                symbol.get("accessibility") or "NotApplicable",
                int(bool(symbol.get("isStatic"))),
                int(bool(symbol.get("isScriptFile"))),
                int(bool(symbol.get("isUnityObject"))),
                int(bool(symbol.get("isMonoBehaviour"))),
                int(bool(symbol.get("isScriptableObject"))),
                int(bool(symbol.get("isPartial"))),
                json.dumps(
                    symbol.get("baseTypes") or [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )

        for declaration in declarations:
            project_path = declaration["projectRelativePath"].replace("\\", "/")
            connection.execute(
                """
                INSERT INTO symbol_declarations(
                    symbol_id, project_relative_path, line, column_number,
                    span_start, span_length
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol_id,
                    project_path,
                    declaration["line"],
                    declaration["column"],
                    declaration["spanStart"],
                    declaration["spanLength"],
                ),
            )
            declarations_count += 1
            if (
                symbol["kind"] == "Type"
                and symbol.get("isScriptFile")
                and Path(project_path).suffix.casefold() == ".cs"
                and Path(project_path).stem == symbol["name"]
            ):
                types_by_path.setdefault(
                    project_path.casefold(), []
                ).append(symbol_id)
                if symbol.get("isUnityObject"):
                    unity_types_by_path.setdefault(
                        project_path.casefold(), []
                    ).append(symbol_id)

        if containing_symbol_id and declarations:
            first = declarations[0]
            source_path = first["projectRelativePath"].replace("\\", "/")
            insert_edge(
                connection,
                containing_symbol_id,
                "DECLARES",
                symbol_id,
                symbol["kind"],
                source_path,
                first["line"],
                symbol["roslynKey"],
            )

    script_assets = connection.execute(
        """
        SELECT asset_id, path
        FROM assets
        WHERE exists_locally = 1 AND kind = 'script'
        ORDER BY path
        """
    ).fetchall()
    status_counts: Counter[str] = Counter()
    for asset_id, asset_path in script_assets:
        type_candidates = sorted(
            set(types_by_path.get(asset_path.casefold(), []))
        )
        candidates = sorted(
            set(unity_types_by_path.get(asset_path.casefold(), []))
        )
        if len(candidates) == 1:
            status = "resolved"
            reason = "exact-path-and-single-unity-object-type"
        elif not candidates and type_candidates:
            status = "not_unity_script"
            reason = "compiled-types-exist-but-none-derive-from-unity-object"
        elif not candidates:
            status = "unresolved"
            reason = "no-compiled-top-level-type-matches-script-file"
        else:
            status = "ambiguous"
            reason = "multiple-unity-object-types-match-script-file"

        connection.execute(
            """
            INSERT INTO script_symbol_resolution(
                asset_id, status, reason, candidate_count
            ) VALUES (?, ?, ?, ?)
            """,
            (asset_id, status, reason, len(candidates)),
        )
        status_counts[status] += 1
        for type_candidate in type_candidates:
            declaration = connection.execute(
                """
                SELECT project_relative_path, line
                FROM symbol_declarations
                WHERE symbol_id = ?
                ORDER BY project_relative_path, line
                LIMIT 1
                """,
                (type_candidate,),
            ).fetchone()
            insert_edge(
                connection,
                asset_id,
                "SOURCE_FILE_DECLARES_TYPE",
                type_candidate,
                "",
                declaration[0] if declaration else asset_path,
                declaration[1] if declaration else 1,
                f"{asset_path}|{type_candidate}",
            )

        for candidate in candidates:
            confidence = 1.0 if len(candidates) == 1 else 0.5
            connection.execute(
                """
                INSERT INTO script_symbol_links(asset_id, symbol_id, confidence)
                VALUES (?, ?, ?)
                """,
                (asset_id, candidate, confidence),
            )
            declaration = connection.execute(
                """
                SELECT project_relative_path, line
                FROM symbol_declarations
                WHERE symbol_id = ?
                ORDER BY project_relative_path, line
                LIMIT 1
                """,
                (candidate,),
            ).fetchone()
            insert_edge(
                connection,
                asset_id,
                "SCRIPT_GUID_RESOLVES_TO_SYMBOL",
                candidate,
                "m_Script",
                declaration[0] if declaration else asset_path,
                declaration[1] if declaration else 1,
                f"{asset_path}|{candidate}|{confidence}",
            )

    connection.execute(
        "INSERT INTO metadata(key, value) VALUES ('symbolCatalogHash', ?)",
        (sha256_bytes(raw),),
    )
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES ('symbolCatalogKeyFormat', ?)",
        (document.get("keyFormat") or "unknown",),
    )
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES ('symbolCatalogRoslynVersion', ?)",
        (document.get("roslynVersion") or "unknown",),
    )
    return {
        "catalogSymbols": len(symbols),
        "catalogDeclarations": declarations_count,
        "resolvedScriptAssets": status_counts["resolved"],
        "unresolvedScriptAssets": status_counts["unresolved"],
        "nonUnityScriptAssets": status_counts["not_unity_script"],
        "ambiguousScriptAssets": status_counts["ambiguous"],
    }


def current_git_revision(repository: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def graph_fingerprint(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    queries = {
        "assets": """
            SELECT asset_id, COALESCE(guid, ''), COALESCE(path, ''), kind,
                   COALESCE(meta_path, ''), COALESCE(content_hash, ''),
                   exists_locally, is_external
            FROM assets ORDER BY asset_id
        """,
        "objects": """
            SELECT object_id, asset_id, file_id, class_id, type_name,
                   COALESCE(name, ''), source_path, source_line
            FROM objects ORDER BY object_id
        """,
        "code_symbols": """
            SELECT symbol_id, roslyn_key, COALESCE(documentation_id, ''),
                   kind, COALESCE(subkind, ''), assembly_name, name,
                   qualified_name, namespace_name, COALESCE(metadata_name, ''),
                   COALESCE(containing_symbol_id, ''),
                   COALESCE(containing_roslyn_key, ''),
                   COALESCE(containing_type_metadata_name, ''),
                   accessibility, is_static, is_script_file, is_unity_object,
                   is_mono_behaviour, is_scriptable_object, is_partial,
                   base_types_json
            FROM code_symbols ORDER BY symbol_id
        """,
        "symbol_declarations": """
            SELECT symbol_id, project_relative_path, line, column_number,
                   span_start, span_length
            FROM symbol_declarations
            ORDER BY symbol_id, project_relative_path, span_start
        """,
        "script_symbol_resolution": """
            SELECT asset_id, status, reason, candidate_count
            FROM script_symbol_resolution ORDER BY asset_id
        """,
        "script_symbol_links": """
            SELECT asset_id, symbol_id, confidence
            FROM script_symbol_links ORDER BY asset_id, symbol_id
        """,
        "edges": """
            SELECT source_id, relation, target_id, property_name,
                   source_path, source_line, evidence_hash
            FROM edges
            ORDER BY source_id, relation, target_id, property_name,
                     source_path, source_line
        """,
    }
    for table_name, query in queries.items():
        digest.update(table_name.encode("utf-8"))
        digest.update(b"\0")
        for row in connection.execute(query):
            digest.update(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            digest.update(b"\n")
    return digest.hexdigest()


def build_graph(
    repository: Path,
    unity_project: Path,
    policy_path: Path,
    database_path: Path,
    symbol_catalog_path: Path | None = None,
) -> dict[str, int | str]:
    policy = load_policy(policy_path)
    assets_root = unity_project / "Assets"
    if not assets_root.is_dir():
        raise ValueError(f"Unity Assets directory does not exist: {assets_root}")

    files = list(iter_files(assets_root, repository, policy))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_database = database_path.with_suffix(database_path.suffix + ".building")
    if temporary_database.exists():
        temporary_database.unlink()

    connection = sqlite3.connect(temporary_database)
    try:
        initialize_database(connection)
        path_to_asset_id, build_stats = collect_assets(
            connection, files, unity_project
        )
        for path in files:
            if path.suffix.casefold() not in SERIALIZED_EXTENSIONS:
                continue
            try:
                index_serialized_file(
                    connection, path, unity_project, path_to_asset_id
                )
                build_stats.serialized_files += 1
            except OSError:
                build_stats.skipped_files += 1

        derived_hierarchy = derive_game_object_hierarchy(connection)
        catalog_stats: dict[str, int | str] = {}
        if symbol_catalog_path is not None:
            catalog_stats = import_symbol_catalog(
                connection,
                symbol_catalog_path,
            )
        metadata = {
            "schemaVersion": str(SCHEMA_VERSION),
            "policyName": json.loads(policy_path.read_text(encoding="utf-8")).get(
                "name", "unknown"
            ),
            "gitRevision": current_git_revision(repository),
            "unityProject": str(unity_project.resolve()),
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items()
        )
        fingerprint = graph_fingerprint(connection)
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('graphFingerprint', ?)",
            (fingerprint,),
        )
        connection.commit()

        counts = graph_stats(connection)
        counts.update(
            {
                "metaFiles": build_stats.meta_files,
                "serializedFiles": build_stats.serialized_files,
                "skippedFiles": build_stats.skipped_files,
                "derivedHierarchyEdges": derived_hierarchy,
                "graphFingerprint": fingerprint,
                **catalog_stats,
            }
        )
    finally:
        connection.close()

    os.replace(temporary_database, database_path)
    return counts


def graph_stats(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "assets": connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
        "localAssets": connection.execute(
            "SELECT COUNT(*) FROM assets WHERE exists_locally = 1"
        ).fetchone()[0],
        "externalAssets": connection.execute(
            "SELECT COUNT(*) FROM assets WHERE exists_locally = 0"
        ).fetchone()[0],
        "scenes": connection.execute(
            "SELECT COUNT(*) FROM assets WHERE kind = 'scene'"
        ).fetchone()[0],
        "prefabs": connection.execute(
            "SELECT COUNT(*) FROM assets WHERE kind = 'prefab'"
        ).fetchone()[0],
        "objects": connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0],
        "codeSymbols": connection.execute(
            "SELECT COUNT(*) FROM code_symbols"
        ).fetchone()[0],
        "symbolDeclarations": connection.execute(
            "SELECT COUNT(*) FROM symbol_declarations"
        ).fetchone()[0],
        "gameObjects": connection.execute(
            "SELECT COUNT(*) FROM objects WHERE type_name = 'GameObject'"
        ).fetchone()[0],
        "components": connection.execute(
            """
            SELECT COUNT(DISTINCT source_id)
            FROM edges
            WHERE relation = 'COMPONENT_ON_GAME_OBJECT'
            """
        ).fetchone()[0],
        "edges": connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "scriptLinks": connection.execute(
            "SELECT COUNT(*) FROM edges WHERE relation = 'COMPONENT_USES_SCRIPT'"
        ).fetchone()[0],
        "resolvedLocalScriptLinks": connection.execute(
            """
            SELECT COUNT(*)
            FROM edges
            JOIN assets ON assets.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND assets.exists_locally = 1
              AND assets.kind = 'script'
            """
        ).fetchone()[0],
        "resolvedComponentSymbolLinks": connection.execute(
            """
            SELECT COUNT(*)
            FROM edges
            JOIN script_symbol_links
              ON script_symbol_links.asset_id = edges.target_id
            JOIN script_symbol_resolution
              ON script_symbol_resolution.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND script_symbol_resolution.status = 'resolved'
            """
        ).fetchone()[0],
        "unresolvedLocalComponentScriptLinks": connection.execute(
            """
            SELECT COUNT(*)
            FROM edges
            JOIN assets ON assets.asset_id = edges.target_id
            LEFT JOIN script_symbol_links
              ON script_symbol_links.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND assets.exists_locally = 1
              AND assets.kind = 'script'
              AND script_symbol_links.symbol_id IS NULL
            """
        ).fetchone()[0],
        "externalOrPackageScriptLinks": connection.execute(
            """
            SELECT COUNT(*)
            FROM edges
            JOIN assets ON assets.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND NOT (assets.exists_locally = 1 AND assets.kind = 'script')
            """
        ).fetchone()[0],
        "prefabSourceLinks": connection.execute(
            "SELECT COUNT(*) FROM edges WHERE relation = 'PREFAB_INSTANCE_SOURCE'"
        ).fetchone()[0],
        "gameObjectParentLinks": connection.execute(
            "SELECT COUNT(*) FROM edges WHERE relation = 'GAME_OBJECT_PARENT'"
        ).fetchone()[0],
    }


def open_readonly(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise ValueError(f"Graph database does not exist: {database_path}")
    uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def print_stats(database_path: Path) -> None:
    connection = open_readonly(database_path)
    try:
        stats = graph_stats(connection)
        relations = connection.execute(
            """
            SELECT relation, COUNT(*)
            FROM edges
            GROUP BY relation
            ORDER BY COUNT(*) DESC, relation
            """
        ).fetchall()
    finally:
        connection.close()
    print(json.dumps({"database": str(database_path), **stats}, indent=2))
    print("Relations:")
    for relation, count in relations:
        print(f"  {relation:34} {count:8,}")


def resolve_asset(
    connection: sqlite3.Connection, identity: str
) -> tuple[str, str | None, str | None]:
    normalized = identity.replace("\\", "/")
    row = connection.execute(
        """
        SELECT asset_id, guid, path
        FROM assets
        WHERE guid = ? COLLATE NOCASE
           OR path = ? COLLATE NOCASE
           OR path LIKE ? COLLATE NOCASE
        ORDER BY
            CASE WHEN guid = ? COLLATE NOCASE THEN 0
                 WHEN path = ? COLLATE NOCASE THEN 1
                 ELSE 2 END,
            LENGTH(path)
        LIMIT 1
        """,
        (normalized, normalized, f"%/{normalized}", normalized, normalized),
    ).fetchone()
    if not row:
        raise ValueError(f"Asset not found: {identity}")
    return row


def print_uses(database_path: Path, identity: str, limit: int) -> None:
    connection = open_readonly(database_path)
    try:
        asset_id, guid, path = resolve_asset(connection, identity)
        rows = connection.execute(
            """
            SELECT
                edges.relation,
                edges.source_id,
                owner.path,
                objects.type_name,
                objects.name,
                edges.property_name,
                edges.source_path,
                edges.source_line
            FROM edges
            LEFT JOIN objects ON objects.object_id = edges.source_id
            LEFT JOIN assets owner ON owner.asset_id = objects.asset_id
            WHERE edges.target_id = ?
            ORDER BY owner.path, objects.name, edges.source_line
            LIMIT ?
            """,
            (asset_id, limit),
        ).fetchall()
    finally:
        connection.close()

    print(json.dumps({"assetId": asset_id, "guid": guid, "path": path}, indent=2))
    for row in rows:
        print(
            json.dumps(
                {
                    "relation": row[0],
                    "sourceId": row[1],
                    "ownerAsset": row[2],
                    "objectType": row[3],
                    "objectName": row[4],
                    "property": row[5],
                    "evidence": f"{row[6]}:{row[7]}",
                },
                ensure_ascii=False,
            )
        )


def print_find_object(database_path: Path, name: str, limit: int) -> None:
    connection = open_readonly(database_path)
    try:
        rows = connection.execute(
            """
            SELECT objects.object_id, objects.name, objects.type_name,
                   assets.path, objects.source_line
            FROM objects
            JOIN assets ON assets.asset_id = objects.asset_id
            WHERE objects.name LIKE ? COLLATE NOCASE
            ORDER BY assets.path, objects.name
            LIMIT ?
            """,
            (f"%{name}%", limit),
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        print(
            json.dumps(
                {
                    "objectId": row[0],
                    "name": row[1],
                    "type": row[2],
                    "asset": row[3],
                    "line": row[4],
                },
                ensure_ascii=False,
            )
        )


def print_find_symbol(database_path: Path, name: str, limit: int) -> None:
    connection = open_readonly(database_path)
    try:
        rows = connection.execute(
            """
            SELECT
                symbols.symbol_id,
                symbols.kind,
                symbols.name,
                symbols.qualified_name,
                symbols.assembly_name,
                symbols.containing_symbol_id,
                declarations.project_relative_path,
                declarations.line,
                scripts.path,
                (
                    SELECT COUNT(*)
                    FROM edges component_edges
                    WHERE component_edges.relation = 'COMPONENT_USES_SCRIPT'
                      AND component_edges.target_id = script_links.asset_id
                )
            FROM code_symbols symbols
            LEFT JOIN symbol_declarations declarations
              ON declarations.symbol_id = symbols.symbol_id
             AND declarations.rowid = (
                 SELECT MIN(candidate.rowid)
                 FROM symbol_declarations candidate
                 WHERE candidate.symbol_id = symbols.symbol_id
             )
            LEFT JOIN script_symbol_links script_links
              ON script_links.symbol_id =
                 CASE
                     WHEN symbols.kind = 'Type' THEN symbols.symbol_id
                     ELSE symbols.containing_symbol_id
                 END
            LEFT JOIN assets scripts
              ON scripts.asset_id = script_links.asset_id
            WHERE symbols.name LIKE ? COLLATE NOCASE
               OR symbols.qualified_name LIKE ? COLLATE NOCASE
            ORDER BY
                CASE WHEN symbols.name = ? COLLATE NOCASE THEN 0 ELSE 1 END,
                symbols.qualified_name,
                symbols.kind
            LIMIT ?
            """,
            (f"%{name}%", f"%{name}%", name, limit),
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        print(
            json.dumps(
                {
                    "symbolId": row[0],
                    "kind": row[1],
                    "name": row[2],
                    "qualifiedName": row[3],
                    "assembly": row[4],
                    "containingSymbolId": row[5],
                    "source": (
                        f"{row[6]}:{row[7]}" if row[6] is not None else None
                    ),
                    "unityScript": row[8],
                    "componentUseCount": row[9],
                },
                ensure_ascii=False,
            )
        )


def validate_graph(database_path: Path) -> dict[str, object]:
    connection = open_readonly(database_path)
    checks = {
        "danglingHasComponent": """
            SELECT COUNT(*)
            FROM edges
            LEFT JOIN objects ON objects.object_id = edges.target_id
            WHERE edges.relation = 'GAME_OBJECT_HAS_COMPONENT'
              AND objects.object_id IS NULL
        """,
        "danglingComponentGameObject": """
            SELECT COUNT(*)
            FROM edges
            LEFT JOIN objects ON objects.object_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_ON_GAME_OBJECT'
              AND objects.object_id IS NULL
        """,
        "selfParentLinks": """
            SELECT COUNT(*)
            FROM edges
            WHERE relation = 'GAME_OBJECT_PARENT'
              AND source_id = target_id
        """,
        "localAssetsWithoutPath": """
            SELECT COUNT(*)
            FROM assets
            WHERE exists_locally = 1 AND path IS NULL
        """,
        "scriptTargetsWithoutAsset": """
            SELECT COUNT(*)
            FROM edges
            LEFT JOIN assets ON assets.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND assets.asset_id IS NULL
        """,
        "localComponentScriptsWithoutResolution": """
            SELECT COUNT(*)
            FROM edges
            JOIN assets ON assets.asset_id = edges.target_id
            LEFT JOIN script_symbol_resolution
              ON script_symbol_resolution.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND assets.exists_locally = 1
              AND assets.kind = 'script'
              AND script_symbol_resolution.asset_id IS NULL
        """,
        "scriptSymbolLinksWithoutCodeSymbol": """
            SELECT COUNT(*)
            FROM script_symbol_links
            LEFT JOIN code_symbols
              ON code_symbols.symbol_id = script_symbol_links.symbol_id
            WHERE code_symbols.symbol_id IS NULL
        """,
        "ambiguousScriptAssets": """
            SELECT COUNT(*)
            FROM script_symbol_resolution
            WHERE status = 'ambiguous'
        """,
        "unresolvedLocalComponentScriptLinks": """
            SELECT COUNT(*)
            FROM edges
            JOIN assets ON assets.asset_id = edges.target_id
            LEFT JOIN script_symbol_links
              ON script_symbol_links.asset_id = edges.target_id
            WHERE edges.relation = 'COMPONENT_USES_SCRIPT'
              AND assets.exists_locally = 1
              AND assets.kind = 'script'
              AND script_symbol_links.symbol_id IS NULL
        """,
    }
    try:
        results = {
            name: connection.execute(query).fetchone()[0]
            for name, query in checks.items()
        }
        recorded = connection.execute(
            "SELECT value FROM metadata WHERE key = 'graphFingerprint'"
        ).fetchone()
        catalog_present = connection.execute(
            "SELECT COUNT(*) FROM metadata WHERE key = 'symbolCatalogHash'"
        ).fetchone()[0] == 1
        computed_fingerprint = graph_fingerprint(connection)
    finally:
        connection.close()

    recorded_fingerprint = recorded[0] if recorded else None
    fingerprint_matches = recorded_fingerprint == computed_fingerprint
    bridge_checks = {
        "localComponentScriptsWithoutResolution",
        "scriptSymbolLinksWithoutCodeSymbol",
        "ambiguousScriptAssets",
        "unresolvedLocalComponentScriptLinks",
    }
    effective_results = {
        name: count
        for name, count in results.items()
        if catalog_present or name not in bridge_checks
    }
    return {
        "passed": all(count == 0 for count in effective_results.values())
        and fingerprint_matches,
        "catalogPresent": catalog_present,
        "checks": results,
        "recordedFingerprint": recorded_fingerprint,
        "computedFingerprint": computed_fingerprint,
        "fingerprintMatches": fingerprint_matches,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a clean Unity graph.")
    build.add_argument("--repository", type=Path, default=Path.cwd())
    build.add_argument("--unity-project", type=Path, required=True)
    build.add_argument(
        "--policy",
        type=Path,
        default=Path("config/unity-brain-index-policy.json"),
    )
    build.add_argument("--database", type=Path, required=True)
    build.add_argument(
        "--symbol-catalog",
        type=Path,
        help="Optional Roslyn-compatible semantic symbol catalog JSON.",
    )

    stats = subparsers.add_parser("stats", help="Print graph statistics.")
    stats.add_argument("--database", type=Path, required=True)

    uses = subparsers.add_parser("uses", help="Find objects using an asset.")
    uses.add_argument("--database", type=Path, required=True)
    uses.add_argument("--asset", required=True, help="Asset path or GUID.")
    uses.add_argument("--limit", type=int, default=50)

    find_object = subparsers.add_parser(
        "find-object", help="Find named GameObjects or serialized objects."
    )
    find_object.add_argument("--database", type=Path, required=True)
    find_object.add_argument("--name", required=True)
    find_object.add_argument("--limit", type=int, default=50)

    find_symbol = subparsers.add_parser(
        "find-symbol", help="Find Roslyn symbols and linked Unity usage."
    )
    find_symbol.add_argument("--database", type=Path, required=True)
    find_symbol.add_argument("--name", required=True)
    find_symbol.add_argument("--limit", type=int, default=50)

    validate = subparsers.add_parser(
        "validate", help="Run graph referential-integrity gates."
    )
    validate.add_argument("--database", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "build":
            stats = build_graph(
                args.repository.resolve(),
                args.unity_project.resolve(),
                args.policy.resolve(),
                args.database.resolve(),
                args.symbol_catalog.resolve()
                if args.symbol_catalog is not None
                else None,
            )
            print(json.dumps(stats, indent=2))
        elif args.command == "stats":
            print_stats(args.database.resolve())
        elif args.command == "uses":
            print_uses(args.database.resolve(), args.asset, args.limit)
        elif args.command == "find-object":
            print_find_object(args.database.resolve(), args.name, args.limit)
        elif args.command == "find-symbol":
            print_find_symbol(args.database.resolve(), args.name, args.limit)
        elif args.command == "validate":
            result = validate_graph(args.database.resolve())
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
