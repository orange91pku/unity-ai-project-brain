# Security policy

## Supported version

Security fixes are currently applied to the latest `0.x` release.

## Reporting

Do not open a public issue for a suspected vulnerability, exposed credential,
private source path, unsafe MCP boundary, or unintended data disclosure.
Contact the repository maintainers privately through the security reporting
channel configured on the public hosting platform.

Include:

- affected version and operating system;
- reproduction steps;
- whether source, credentials, or generated indexes were exposed;
- the selected Project Brain configuration with secrets and private paths
  removed;
- expected and observed behavior.

## Security model

- The Context API binds to loopback by default.
- MCP is read-only and scoped to one configured analysis root by default.
- Local configuration and generated indexes are excluded from Git.
- Project Brain does not provide source mutation endpoints.
- Indexes may contain sensitive code relationships and must be protected like
  source code.

Running the HTTP API on a non-loopback interface, disabling read-only MCP, or
sharing an index outside the source repository's access boundary is an
explicit operator decision and outside the safe default.
