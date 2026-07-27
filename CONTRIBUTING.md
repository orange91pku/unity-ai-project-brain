# Contributing

Contributions are welcome when they preserve the read-only intelligence
boundary and keep Unity evidence traceable to an authoritative source.

## Development setup

```bash
pnpm install --frozen-lockfile
python -m pip install -e .
pnpm run verify
```

## Pull request requirements

- Add or update tests for behavior changes.
- Keep JSON contracts versioned and backwards compatible.
- Do not commit local configuration, generated indexes, Unity caches, private
  project names, absolute machine paths, credentials, or proprietary assets.
- Report provenance and confidence for new evidence edges.
- Do not introduce mutation endpoints into MCP or Context API.
- Update third-party notices for dependency or license changes.
- Run `pnpm run verify` before requesting review.

## Design principles

1. Unity GUID/fileID relationships are authoritative only when derived from
   Unity serialized data or an explicitly identified Unity API.
2. Code, Unity, runtime, and Git evidence remain distinguishable.
3. Unresolved and ambiguous identities are returned explicitly.
4. Rebuildable indexes never become the source of truth.
5. Safe defaults take priority over unattended mutation.

By contributing, you agree that your contribution is licensed under the
Apache License 2.0.
