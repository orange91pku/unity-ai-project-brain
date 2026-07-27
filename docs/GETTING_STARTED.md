# Getting started

## 1. Install the Unity bridge

Unity users can install the read-only bridge without cloning this repository:

```text
https://github.com/orange91pku/unity-ai-project-brain.git?path=/Packages/com.heycici.project-brain#v0.2.0
```

Use **Window > Package Management > Package Manager > Install package from Git
URL**, then open **Tools > HeyCici > Project Brain**.

See [UPM installation](UPM_INSTALL.md) for the manifest form, updates and
uninstall instructions.

## 2. Install backend prerequisites

Install Node.js 22.15 or newer, pnpm, Python 3.11 or newer, and Git.

Verify:

```bash
node --version
pnpm --version
python --version
git --version
```

## 3. Install the Python backend without cloning

```bash
python -m pip install \
  "unity-ai-project-brain @ git+https://github.com/orange91pku/unity-ai-project-brain.git@v0.2.0"
```

This provides the Unity identity graph, evidence store, Context API and Visual
RAG context exporter.

## 4. Prepare a source-development checkout

This step is needed only for GitNexus orchestration or Project Brain
development:

```bash
pnpm install --frozen-lockfile
python -m pip install -e .
```

The npm install downloads the pinned `gitnexus@1.6.9` dependency. Review
`THIRD_PARTY_NOTICES.md` before use.

## 5. Configure a Unity repository

Copy the example:

```bash
cp config/projects.example.json config/projects.local.json
```

PowerShell:

```powershell
Copy-Item config/projects.example.json config/projects.local.json
```

Replace all placeholder paths with absolute paths valid on the current host.
The repository path must identify a Git working tree unless `skipGit` is true.
The Unity project must contain `Assets`, `Packages`, and `ProjectSettings`.

Recommended configuration:

- one full repository project for exact context and impact;
- one focused `Assets/Scripts` project for faster semantic retrieval.

## 6. Audit index input

```bash
python -m project_brain.index_audit \
  --repo /absolute/path/to/repository \
  --policy config/index-policy.example.json \
  --format json
```

Review accepted lanes and exclusions before building an index. Do not index
Unity `Library`, package caches, builds, credentials, or irrelevant vendor
content.

## 7. Build the code graph

```bash
pnpm run doctor -- --project my-unity-game
pnpm run analyze -- --project my-unity-game
pnpm run status -- --project my-unity-game
```

After a successful analysis, Project Brain records its own freshness
baseline. For a full index, the baseline covers the Git revision plus staged,
modified, deleted, and untracked content. For a focused non-Git index, it
covers the analyzed source tree. `status` compares the current project with
that baseline and reports `up-to-date`, `stale`, or `missing baseline`
without depending on upstream status output.

To print an MCP descriptor:

```bash
pnpm run print-mcp -- --project my-unity-game
```

MCP defaults to read-only and is restricted to the selected analysis path.

## 6. Build the Unity identity graph

```bash
python -m project_brain.unity_graph build \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject \
  --policy config/index-policy.example.json \
  --database .project-brain/unity-graph.sqlite
```

Validate:

```bash
python -m project_brain.unity_graph validate \
  --database .project-brain/unity-graph.sqlite
```

The build is accepted only when integrity gates pass and the recorded graph
fingerprint matches a fresh computation.

## 7. Query context

```bash
python -m project_brain.context_api resolve \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject \
  PlayerController
```

Start the loopback service:

```bash
python -m project_brain.context_api serve \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject
```

Example endpoints:

```text
GET /v1/resolve?q=PlayerController
GET /v1/context?id=asset:<id>&depth=2
GET /v1/impact?id=symbol:<id>&changeKind=rename
GET /v1/uses?id=asset:<id>
GET /v1/history?id=asset:<id>&limit=20
GET /v1/evidence?claim=missingScriptCount
```

## 8. Process changes

Generate or consume a versioned change envelope, then:

```bash
pnpm run plan-change -- \
  --project my-unity-game-code \
  --envelope /absolute/path/to/change-envelope.json
```

The plan reports affected paths, invalidated graph partitions, required
reindexing, and downstream Unity graph actions. It does not mutate source.

## 9. Export context for Visual RAG

After `unity_graph validate` passes:

```bash
python -m project_brain.visual_context export \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject \
  --project-id studio.game \
  --output .project-brain/visual-context.json
```

The output conforms to `schemas/visual-context.schema.json`. It contains image
asset GUIDs and hashes plus aggregated owner, fileID, component and hierarchy
usage evidence. The output is context only and cannot authorize Unity
mutation.
