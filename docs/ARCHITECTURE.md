# Architecture

## Product boundary

Unity Project Brain is a read-only intelligence platform. It indexes and joins
code, Unity serialized identity, evidence, and history. It does not rename
symbols, rewrite scenes, replace art, or call mutation endpoints.

The system has two rebuildable databases:

1. GitNexus owns the code graph and semantic retrieval index.
2. Project Brain owns the SQLite Unity identity/evidence graph.

Authoritative source remains outside both databases.

| Fact | Authority |
| --- | --- |
| Code content | Git working tree and commit |
| Code relationship | GitNexus analysis with index revision |
| Unity asset identity | `.meta` GUID |
| Serialized object identity | Unity fileID and owning asset GUID |
| Prefab/scene/component relationship | Unity serialized asset |
| Optional symbol identity | versioned Roslyn-compatible catalog |
| Runtime behavior | attributed runtime evidence |
| Acceptance result | attributed Unity verification report |

## Components

### GitNexus adapter

The Node.js adapter:

- registers one or more project-scoped indexes;
- supports full repository and focused source indexes;
- pins the GitNexus dependency;
- disables generated skills and agent-instruction injection by default;
- creates repository-restricted, read-only MCP descriptors;
- records Git revision plus dirty-worktree fingerprints for full indexes;
- records source-tree fingerprints for focused non-Git roots;
- translates change envelopes into explicit reindex plans.

### Unity graph

The Python graph builder parses text-serialized Unity data:

- `.meta`;
- `.prefab`;
- `.unity`;
- `.asset`;
- assembly definitions and source paths.

It links asset GUIDs, serialized fileIDs, GameObjects, components, script
references, prefab instances, and optional code symbols. Every unresolved or
ambiguous relationship remains explicit.

### Evidence store

Evidence is immutable and source-attributed. Reingestion is idempotent.
Conflicting observations remain separate rather than silently overwriting one
another.

Supported source classes are:

- runtime;
- external evidence;
- Unity gate;
- Git history.

### Context API

The Context API exposes:

- `resolve`;
- `context`;
- `impact`;
- `uses`;
- `history`;
- `evidence`.

Responses include graph fingerprint, provenance, confidence, unresolved
reasons, and truncation metadata. The HTTP server binds to loopback by
default and has no mutation endpoint.

## Change lifecycle

```text
Git diff or Unity editor callback
             |
      change envelope
             |
   invalidation planner
      /             \
GitNexus rebuild   Unity graph incremental apply
      \             /
       integrity validation
             |
        Context API
```

Incremental output must equal a clean rebuild for the same source revision.
When an asset format or change type cannot be updated safely, the planner
selects a full rebuild rather than guessing.

## ReVisualReskin integration

ReVisualReskin is a separate product with a separate Visual RAG database.

Project Brain owns:

- where an asset or component is used;
- which scenes, prefabs, and code systems depend on it;
- what verification gates are required.

ReVisualReskin owns:

- themes and Theme Packs;
- visual embeddings and semantic roles;
- palette and geometry features;
- mapping decisions;
- visual review and A/B evidence;
- apply and rollback transactions.

Integration uses stable IDs and versioned JSON:

- project ID and index fingerprint;
- Unity GUID/fileID;
- repository-relative asset path;
- content hash;
- semantic role and theme asset ID.

Neither system reads the other's database directly.

## Extension rules

Extensions may add evidence adapters, graph enrichers, or read-only query
surfaces. They must:

- declare their source and confidence;
- use versioned contracts;
- preserve unresolved states;
- avoid source mutation;
- avoid copying secrets or private source into logs;
- remain reproducible from authoritative inputs.
