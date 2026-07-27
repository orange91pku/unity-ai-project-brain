# Publication checklist

## Repository boundary

- [x] Public repository contains only allowlisted source.
- [x] No `.gitnexus`, `.state`, local config, caches, or generated databases.
- [x] No private project names, absolute machine paths, credentials, or private
      tool identifiers.
- [x] Example data is synthetic.

## Legal

- [ ] Project owner accepts Apache-2.0 for Project Brain contributions.
- [ ] `NOTICE` copyright holder is correct.
- [ ] GitNexus PolyForm Noncommercial terms are accepted for the intended use.
- [x] Third-party notices match the pinned lockfile.
- [x] Unity and GitNexus non-affiliation statement remains visible.

## Technical

- [x] Clean `pnpm install --frozen-lockfile` passes.
- [x] Editable Python installation passes.
- [x] Node tests pass.
- [x] Python tests pass.
- [x] Public audit passes.
- [x] GitNexus descriptor is read-only and scoped.
- [x] Unity graph clean build and validation pass on the synthetic fixture.
- [x] Context API binds to loopback by default.

## Documentation

- [x] README accurately separates implemented features and roadmap.
- [x] Getting-started commands are reproduced in an independent clean export.
- [x] Unity CLI guide links to current official documentation.
- [ ] Security reporting channel is configured before publication.
- [x] Contribution and extension contracts are reviewed.

## Release

- [ ] Default branch protection is enabled.
- [ ] CI is required before merge.
- [ ] Secret scanning and dependency alerts are enabled.
- [ ] Release tag matches package and Python versions.
- [x] No GitHub remote is added until the final public review is accepted.
