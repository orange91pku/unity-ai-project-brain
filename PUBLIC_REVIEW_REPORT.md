# Public review report

Generated: 2026-07-27

## Candidate

- Product: Unity Project Brain
- Version: `0.2.0`
- Public workspace: independent clean export
- Publication state: published and independently accessible
- Repository: <https://github.com/orange91pku/unity-ai-project-brain>
- Release: <https://github.com/orange91pku/unity-ai-project-brain/releases/tag/v0.2.0>

## Automated evidence

The candidate was installed and verified from the independent public
workspace.

| Gate | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | PASS, 252 packages |
| Python editable install | PASS |
| Python distribution `unity-ai-project-brain` | PASS, wheel metadata/build/install |
| Node unit and CLI smoke tests | PASS, 12/12 |
| Python unit tests | PASS, 16/16 |
| Registry dependency audit | PASS, 0 vulnerabilities |
| GitNexus/native override compatibility probes | PASS |
| Full Git index freshness/staleness | PASS |
| Focused source index freshness/staleness | PASS |
| Synthetic Unity identity graph | PASS |
| GUID to script resolution | PASS |
| Component to code-symbol resolution | PASS |
| Prefab source linkage | PASS |
| Scene/prefab hierarchy linkage | PASS |
| Graph fingerprint/integrity | PASS |
| Context API `resolve` | PASS |
| Context API `uses` | PASS |
| Visual RAG context exporter | PASS |
| UPM identity/version/URL/GUID validator | PASS |
| Unity 6000.3 Editor bridge compile | PASS, exit code 0 |
| Unity Editor bridge assembly | PASS, `HeyCici.ProjectBrain.Editor.dll` |
| Public path/private identifier audit | PASS |
| AI discovery map (`AGENTS.md`, `llms.txt`) | PASS |
| GitHub Actions frozen-install verification | PASS |
| GitHub Dependabot open alerts | PASS, 0 |
| Anonymous repository/release/raw access | PASS, HTTP 200 |
| Protected `main` required check | PASS, `test` |

Synthetic graph fingerprint:

```text
8be38e7f2b80e2bdecf990d8bd2d3ca7fb35a6f4219e65897f54e51f99e6eba9
```

## Public boundary

Included:

- project-scoped GitNexus orchestration;
- read-only MCP descriptor generation;
- Unity GUID/fileID graph;
- optional Roslyn-compatible symbol bridge;
- incremental graph and change envelopes;
- evidence store and read-only Context API;
- `com.heycici.project-brain` read-only Unity Editor bridge;
- tagged Git UPM installation without a manual repository clone;
- versioned Visual RAG context export;
- schemas, synthetic fixture, tests, and documentation.

Excluded:

- local project configuration;
- generated indexes and databases;
- Unity caches and build outputs;
- private project source and art;
- internal mutation tools;
- Visual RAG and ReVisualReskin database.

## License review

- Project Brain candidate license: Apache-2.0.
- Direct dependency: `gitnexus@1.6.9`.
- GitNexus license: PolyForm Noncommercial 1.0.0.
- Upstream source is not copied into this repository.

The owner accepted the Apache-2.0 Project Brain license, the `NOTICE`
attribution, and the separate GitNexus PolyForm Noncommercial dependency
boundary for the intended public release.

## Publication outcome

- Canonical repository: `orange91pku/unity-ai-project-brain`.
- Release tag: `v0.2.0`.
- UPM package: `com.heycici.project-brain@0.2.0`.
- The release tag is required to resolve to the verified `main` commit.
- The protected `main` verification workflow is required to pass before the
  release is accepted.
- Private vulnerability reporting, secret scanning, push protection,
  Dependabot security updates, and protected `main` are enabled.

No publication gate is failing.
