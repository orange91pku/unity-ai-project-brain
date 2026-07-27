# AI agent guide

## Mission

Unity Project Brain is a read-only context engine for Unity repositories. It
joins code intelligence, Unity GUID/fileID identity, serialized scene and
prefab relationships, optional Roslyn symbols, runtime evidence, and Git
history so AI agents can reason about a project before proposing changes.

## Safe boundary

- Treat the configured Unity repository as private unless the operator says
  otherwise.
- Do not commit local project configuration, indexes, databases, caches,
  credentials, or absolute machine paths.
- Do not mutate Unity source through Project Brain. Mutation belongs in an
  external tool and its result must pass Unity verification.
- Preserve unresolved and ambiguous relationships as explicit evidence; never
  invent a link to make an answer look complete.
- Keep the Context API loopback-only and MCP read-only unless the operator
  deliberately changes that boundary.

## Authoritative sources

- Git working tree and commits: code content and history.
- Unity `.meta` files: asset GUID identity.
- Text-serialized `.unity`, `.prefab`, and `.asset` files: object, component,
  hierarchy, and serialized-reference identity.
- Roslyn-compatible symbol catalogs: optional code symbol identity.
- Attributed verification reports: acceptance evidence.
- GitNexus: rebuildable code graph and semantic retrieval index.
- Project Brain SQLite graph: rebuildable Unity identity and evidence index.

## Entry points

- `src/cli.mjs`: GitNexus orchestration and scoped MCP descriptors.
- `project_brain/unity_graph.py`: Unity graph build, validate, and query.
- `project_brain/context_api.py`: read-only CLI and loopback HTTP API.
- `project_brain/change_envelope.py`: versioned change contracts.
- `schemas/`: public interoperability contracts.
- `docs/ARCHITECTURE.md`: system boundaries and data flow.
- `docs/GETTING_STARTED.md`: reproducible setup.

## Verification

Run the complete gate before accepting a change:

```bash
pnpm install --frozen-lockfile
python -m pip install -e .
pnpm run verify
```

`pnpm run verify` must pass the Node tests, Python tests, synthetic Unity graph
smoke test, integrity checks, Context API checks, and public privacy audit.

## Contribution priorities

1. Preserve exact Unity identity and provenance.
2. Keep queries read-only and project-scoped.
3. Prefer deterministic, rebuildable indexes.
4. Extend versioned contracts without silently changing existing semantics.
5. Add synthetic fixtures and tests for every new relationship type.
