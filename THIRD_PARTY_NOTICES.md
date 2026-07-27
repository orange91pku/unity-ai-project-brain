# Third-party notices

## GitNexus

- Package: `gitnexus`
- Pinned version: `1.6.9`
- Author: Abhigyan Patwari
- Source: <https://github.com/abhigyanpatwari/GitNexus>
- License: PolyForm Noncommercial 1.0.0
- License text: <https://polyformproject.org/licenses/noncommercial/1.0.0/>

GitNexus is installed from its upstream npm package. Its source is not copied
into this repository. The Apache-2.0 license for Project Brain does not replace
or weaken GitNexus's separate license terms.

Users are responsible for confirming that their use of GitNexus complies with
the PolyForm Noncommercial license or for obtaining an appropriate commercial
license from its rights holder.

## Transitive security overrides

Project Brain pins patched transitive versions where the current GitNexus
dependency ranges do not yet select a non-vulnerable release:

- `brace-expansion@5.0.8`;
- `sharp@0.35.0`;
- `@hono/node-server@2.0.10`;
- `adm-zip@0.6.0`.

These packages retain their own upstream licenses. See
`docs/SECURITY_OVERRIDES.md` for dependency paths, advisories, compatibility
gates, and the removal policy.
