# Public review report

Generated: 2026-07-27

## Candidate

- Product: Unity Project Brain
- Version: `0.1.0`
- Public workspace: independent clean export
- Publication state: local review candidate; no remote configured

## Automated evidence

The candidate was installed and verified from the independent public
workspace.

| Gate | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | PASS, 252 packages |
| Python editable install | PASS |
| Node unit and CLI smoke tests | PASS, 11/11 |
| Python unit tests | PASS, 15/15 |
| Synthetic Unity identity graph | PASS |
| GUID to script resolution | PASS |
| Component to code-symbol resolution | PASS |
| Prefab source linkage | PASS |
| Scene/prefab hierarchy linkage | PASS |
| Graph fingerprint/integrity | PASS |
| Context API `resolve` | PASS |
| Context API `uses` | PASS |
| Public path/private identifier audit | PASS |

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

The owner must confirm the intended use is compatible with the upstream
noncommercial license before publication.

## Owner decisions before push

1. Accept or change Apache-2.0.
2. Confirm the copyright line in `NOTICE`.
3. Configure a private security-reporting channel on the public host.
4. Accept the GitNexus PolyForm Noncommercial dependency boundary.
5. Choose the final repository name and description.

No technical gate is currently failing. Publication remains intentionally
paused for owner review and remote-repository approval.
