# Transitive security overrides

## Why overrides exist

`gitnexus@1.6.9` is the latest upstream npm release used by Project Brain.
At the time of the `0.1.0` release, four runtime dependency ranges resolved to
versions covered by published GitHub security advisories. Project Brain pins
the first patched versions until upstream ranges select safe releases.

| Package | Dependency path | Advisory | Minimum patched version |
| --- | --- | --- | --- |
| `brace-expansion` | `gitnexus > glob > minimatch` | `GHSA-mh99-v99m-4gvg` | `5.0.8` |
| `sharp` | `gitnexus > @huggingface/transformers` | `GHSA-f88m-g3jw-g9cj` | `0.35.0` |
| `@hono/node-server` | `gitnexus > @modelcontextprotocol/sdk` | `GHSA-frvp-7c67-39w9`, `GHSA-9mqv-5hh9-4cgg` | `2.0.10` |
| `adm-zip` | `gitnexus > onnxruntime-node` | `GHSA-xcpc-8h2w-3j85` | `0.6.0` |

The overrides are declared in `pnpm-workspace.yaml`. The public audit rejects
a missing or downgraded override.

## Compatibility gates

An override update is accepted only when all of these pass:

1. frozen-lockfile installation;
2. Node and Python test suites;
3. synthetic Unity identity graph and Context API smoke test;
4. public privacy audit;
5. GitNexus CLI load and doctor command;
6. MCP/Hono module load;
7. `sharp`, ONNX Runtime, ZIP, and glob/minimatch runtime probes;
8. GitHub Actions verification;
9. GitHub Dependabot reports no open alert for the pinned advisories.

## Removal policy

Remove an override when the pinned GitNexus release and its upstream
dependencies naturally resolve to the same or a newer non-vulnerable version.
Do not retain overrides indefinitely: each GitNexus update must compare the
lockfile, rerun the compatibility gates, and remove redundant pins.

Overrides mitigate dependency selection; they do not change the separate
license terms of GitNexus or any transitive package.
