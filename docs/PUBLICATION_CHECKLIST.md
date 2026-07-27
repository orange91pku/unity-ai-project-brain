# Publication checklist

## Repository boundary

- [ ] Public repository contains only allowlisted source.
- [ ] No `.gitnexus`, `.state`, local config, caches, or generated databases.
- [ ] No private project names, absolute machine paths, credentials, or private
      tool identifiers.
- [ ] Example data is synthetic.

## Legal

- [ ] Project owner accepts Apache-2.0 for Project Brain contributions.
- [ ] `NOTICE` copyright holder is correct.
- [ ] GitNexus PolyForm Noncommercial terms are accepted for the intended use.
- [ ] Third-party notices match the pinned lockfile.
- [ ] Unity and GitNexus non-affiliation statement remains visible.

## Technical

- [ ] Clean `pnpm install --frozen-lockfile` passes.
- [ ] Editable Python installation passes.
- [ ] Node tests pass.
- [ ] Python tests pass.
- [ ] Public audit passes.
- [ ] GitNexus descriptor is read-only and scoped.
- [ ] Unity graph clean build and validation pass on the synthetic fixture.
- [ ] Context API binds to loopback by default.

## Documentation

- [ ] README accurately separates implemented features and roadmap.
- [ ] Getting-started commands are reproduced on a clean machine.
- [ ] Unity CLI guide links to current official documentation.
- [ ] Security reporting channel is configured before publication.
- [ ] Contribution and extension contracts are reviewed.

## Release

- [ ] Default branch protection is enabled.
- [ ] CI is required before merge.
- [ ] Secret scanning and dependency alerts are enabled.
- [ ] Release tag matches package and Python versions.
- [ ] No GitHub remote is added until the final public review is accepted.
