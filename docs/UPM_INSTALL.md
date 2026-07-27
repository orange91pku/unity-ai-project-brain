# Install with Unity Package Manager

Unity AI Project Brain provides a read-only Unity Editor bridge as a versioned
Git package. Unity users do not need to clone this repository or copy package
files into `Assets`.

## Requirements

- Unity `6000.3` for the currently verified package baseline.
- Git `2.14+` available on `PATH`.
- Asset Serialization Mode set to **Force Text** for complete scene, prefab and
  asset evidence.
- Python `3.11+` only when using the external identity graph or Context API.
- Node.js `22.15+` and pnpm only when using GitNexus orchestration.

## Install from the Package Manager UI

1. Open **Window > Package Management > Package Manager**.
2. Select **+ > Install package from Git URL**.
3. Paste:

   ```text
   https://github.com/orange91pku/unity-ai-project-brain.git?path=/Packages/com.heycici.project-brain#v0.2.0
   ```

4. Select **Install** and wait for Unity to finish compiling.
5. Open **Tools > HeyCici > Project Brain**.

The `?path=` query selects the Unity package from this multi-runtime
repository. The `#v0.2.0` tag pins a reproducible release.

## Install from Packages/manifest.json

Teams can commit the dependency directly:

```json
{
  "dependencies": {
    "com.heycici.project-brain": "https://github.com/orange91pku/unity-ai-project-brain.git?path=/Packages/com.heycici.project-brain#v0.2.0"
  }
}
```

Commit the generated `Packages/packages-lock.json` so developers and CI resolve
the same revision.

## What the Unity package installs

The Editor bridge:

- reports the Unity project and containing Git repository;
- checks Force Text serialization;
- copies a versioned, read-only project context JSON document;
- prepares backend installation and Context API commands;
- never edits assets or starts an external process automatically.

The UPM package intentionally does not embed Node.js, Python, GitNexus, a
database, or private project data.

## Install the backend without cloning

Install the Python identity graph and Context API directly from the same
release tag:

```bash
python -m pip install \
  "unity-ai-project-brain @ git+https://github.com/orange91pku/unity-ai-project-brain.git@v0.2.0"
```

The Unity window can copy this command.

GitNexus orchestration remains optional and has separate PolyForm
Noncommercial terms. Contributors developing the Node/GitNexus layer should
use the source-development workflow in [Getting started](GETTING_STARTED.md).

## First use

1. Set **Project Settings > Editor > Asset Serialization Mode** to
   **Force Text**.
2. Open **Tools > HeyCici > Project Brain**.
3. Copy the project context JSON and make it available to the operator or AI
   session.
4. Install the backend if Unity GUID/fileID graph, Context API or Visual RAG
   export is required.
5. Build and validate the graph before trusting context answers.

Generated graphs, indexes and configuration remain outside Unity `Assets/`.

## Update

Replace `#v0.2.0` with a newer published tag in
`Packages/manifest.json`, save the file and let Unity resolve the package.
Review the changelog before updating a production project.

## Uninstall

Remove `com.heycici.project-brain` from Package Manager or
`Packages/manifest.json`.

Uninstalling the Editor bridge does not remove external `.project-brain`
indexes, Python packages or GitNexus data. Those are deliberately separate
operator-owned artifacts.

## Troubleshooting

### No Git executable was found

Install Git `2.14+`, add it to `PATH`, then restart Unity Hub and the Editor.

### Package cannot be found

Use the complete URL including `.git`, the package `?path=` and the release
tag. Do not use abbreviated commit hashes; when pinning a commit instead of a
tag, Unity requires the full SHA.

### Project context is incomplete

Confirm Force Text serialization is enabled and that the relevant scenes and
prefabs have been saved as text.

### Backend command is unavailable

UPM installs only the Unity bridge. Install Python `3.11+` and run the tagged
pip command above for the identity graph and Context API.
