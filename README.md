# Unity Project Brain

[![verify](https://github.com/orange91pku/unity-ai-project-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/orange91pku/unity-ai-project-brain/actions/workflows/ci.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Unity Project Brain is an open-source AI context engine and local project
intelligence layer for real Unity repositories. It combines a GitNexus code
graph with Unity GUID/fileID, scene, prefab, GameObject, component, optional
Roslyn symbol, runtime evidence, and Git history relationships behind
read-only MCP and Context API surfaces for AI coding agents.

The project helps an AI answer questions such as:

- Which scenes and prefabs use this script, sprite, material, or component?
- Which GameObjects would be affected if a Unity GUID disappeared?
- What is the blast radius of changing or renaming a code symbol?
- Which technical gates should run before accepting a change?
- Which answer came from serialized Unity data, code analysis, runtime
  evidence, or Git history?

Project Brain does not edit Unity projects. Mutation tools remain separate and
must pass Unity verification before their results become trusted evidence.

## Current public release

Version `0.2.0` includes:

- the `com.heycici.project-brain` read-only Unity Editor bridge;
- no-clone Unity Package Manager and tagged Python backend installation;
- project-scoped GitNexus orchestration;
- full and focused indexes;
- read-only, repository-restricted MCP descriptors;
- deterministic Git revision/worktree fingerprints for full indexes;
- deterministic source-tree fingerprints for focused indexes;
- Unity `.meta`, scene, prefab, component, and asset-reference graph building;
- optional Roslyn-compatible symbol-to-MonoScript identity links;
- incremental Unity graph planning and integrity verification;
- versioned change envelopes;
- an evidence store with provenance and confidence;
- a read-only CLI and loopback HTTP Context API;
- public data schemas and privacy gates.
- a versioned Visual RAG context exporter for specialist applications.

GitNexus method-call edges are not yet imported into the unified SQLite Unity
graph. Use the GitNexus MCP surface for code impact and the Context API for
Unity identity and serialized usage until that connector is complete.

## Architecture

```text
Git repository + Unity project + optional symbol catalog
                  |
        +---------+----------+
        |                    |
  GitNexus code graph   Unity identity graph
        |                    |
        +-------- Context API+
                  |
          AI agents and tools
                  |
     external mutation + Unity verification
                  |
           versioned evidence
```

Project Brain stores rebuildable indexes, not authoritative source. Unity
serialized files remain authoritative for GUID/fileID relationships, Git
remains authoritative for history, and verification reports remain
independent evidence.

## Install the Unity bridge

Unity users do **not** need to clone this repository. In
**Window > Package Management > Package Manager**, select
**Install package from Git URL** and paste:

```text
https://github.com/orange91pku/unity-ai-project-brain.git?path=/Packages/com.heycici.project-brain#v0.2.0
```

After Unity compiles, open **Tools > HeyCici > Project Brain**. See the
[UPM installation guide](docs/UPM_INSTALL.md) for a project manifest example,
updates, uninstall and backend setup.

## Requirements

- Node.js `22.15` or newer
- pnpm
- Python `3.11` or newer
- Git `2.14+`
- A Unity project using text serialization for full scene/prefab visibility

Node and pnpm are required only for GitNexus orchestration. Python is required
only for the external identity graph and Context API. The Unity bridge has no
runtime dependency on either.

## Backend quick start without cloning

Install the tagged Python backend directly from Git:

```bash
python -m pip install \
  "unity-ai-project-brain @ git+https://github.com/orange91pku/unity-ai-project-brain.git@v0.2.0"
```

Build and validate the Unity identity graph:

```bash
python -m project_brain.unity_graph build \
  --repository /absolute/path/to/my-unity-game \
  --unity-project /absolute/path/to/my-unity-game/UnityProject \
  --policy /absolute/path/to/index-policy.json \
  --database /absolute/path/to/.project-brain/unity-graph.sqlite

python -m project_brain.unity_graph validate \
  --database /absolute/path/to/.project-brain/unity-graph.sqlite
```

## Source-development quick start

```bash
pnpm install --frozen-lockfile
python -m pip install -e .
cp config/projects.example.json config/projects.local.json
```

Edit `config/projects.local.json` with absolute paths, then:

```bash
pnpm run doctor -- --project my-unity-game
pnpm run analyze -- --project my-unity-game
pnpm run status -- --project my-unity-game
pnpm run print-mcp -- --project my-unity-game
```

Build and validate the Unity identity graph from the development checkout:

```bash
python -m project_brain.unity_graph build \
  --repository /absolute/path/to/my-unity-game \
  --unity-project /absolute/path/to/my-unity-game/UnityProject \
  --policy config/index-policy.example.json \
  --database .project-brain/unity-graph.sqlite

python -m project_brain.unity_graph validate \
  --database .project-brain/unity-graph.sqlite
```

Start the read-only Context API on loopback:

```bash
python -m project_brain.context_api serve \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/my-unity-game \
  --unity-project /absolute/path/to/my-unity-game/UnityProject \
  --host 127.0.0.1 \
  --port 8765
```

See [Getting started](docs/GETTING_STARTED.md),
[Architecture](docs/ARCHITECTURE.md), and
[Unity CLI guidance](docs/UNITY_CLI.md).

## Read-only boundary

- MCP defaults to read-only.
- MCP is restricted to the selected analysis root.
- The Context API has no mutation endpoint.
- Generated indexes and local paths are gitignored.
- AI suggestions are context, not authorization to edit.
- Any external mutation must compile and pass project-specific Unity gates.

## Related application

[Unity AI Visual Reskin](https://github.com/orange91pku/unity-ai-visual-reskin)
(ReVisualReskin) is a separate project and database. It can consume Project
Brain context to understand where UI and art are used, but owns its own Visual
RAG, theme catalog, mappings, A/B evidence, and reskin transactions.

The two systems exchange stable IDs and versioned JSON. Neither reads the
other's database directly.

Export a Visual RAG context after building and validating the Unity graph:

```bash
python -m project_brain.visual_context export \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject \
  --project-id studio.game \
  --output .project-brain/visual-context.json
```

The exporter is read-only. It emits asset content hashes plus exact GUID,
fileID, owner asset, component and GameObject hierarchy evidence using
`hydracore.project-brain.visual-context/v1`. ReVisualReskin may consume that
file, but it never receives direct database access or mutation authority.

## Licensing

The Project Brain code in this repository is licensed under Apache-2.0.

The pinned `gitnexus@1.6.9` dependency is separately licensed under
PolyForm Noncommercial 1.0.0. Installing or using it requires compliance with
that upstream license. See [Third-party notices](THIRD_PARTY_NOTICES.md).

This project is not affiliated with or endorsed by Unity Technologies or the
GitNexus maintainers.
