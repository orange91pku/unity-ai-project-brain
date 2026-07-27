# Extension contract

Project Brain supports three extension classes.

## Evidence adapter

An evidence adapter emits immutable observations:

```json
{
  "schemaVersion": 1,
  "kind": "external-evidence",
  "sourceUri": "external://provider/project/observation/42",
  "capturedAtUtc": "2026-01-01T00:00:00Z",
  "confidence": 0.8,
  "identityIds": [
    "asset:example"
  ],
  "payload": {}
}
```

The adapter must use a stable `sourceUri`, retain provenance, and avoid
silently replacing conflicting evidence.

## Graph enricher

A graph enricher may add relationships that serialized Unity data cannot
express. Every added edge must include:

- source type and version;
- source revision or content hash;
- confidence;
- unresolved reason when identity is incomplete.

An enricher cannot rewrite authoritative Unity identity.

## Specialist application

A specialist application consumes Project Brain context but owns its own
domain data and transactions. ReVisualReskin is the reference pattern:

- Project Brain reports asset usage and blast radius.
- ReVisualReskin searches its Visual RAG and proposes art mappings.
- ReVisualReskin owns apply/rollback.
- Unity verification produces evidence returned to Project Brain.

### ReVisualReskin / Visual RAG

Build the Unity graph first, then export the versioned bridge:

```bash
python -m project_brain.visual_context export \
  --graph .project-brain/unity-graph.sqlite \
  --repository /absolute/path/to/repository \
  --unity-project /absolute/path/to/repository/UnityProject \
  --project-id studio.game \
  --output .project-brain/visual-context.json
```

The bridge preserves Project Brain's exact GUID/fileID, owner, component and
hierarchy evidence. ReVisualReskin combines it with its private visual index
and Theme Packs. Neither application reads the other's database.

Specialist applications communicate through versioned JSON and stable IDs.
Direct cross-database reads are not supported.
