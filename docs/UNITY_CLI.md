# Unity CLI verification guidance

Unity CLI is an external Unity product. Project Brain does not redistribute,
wrap, or claim ownership of it. This document recommends using it as an
operator-controlled verification layer after another tool changes a Unity
project.

Unity currently describes the standalone CLI as experimental. Check
`unity --help` on the installed version before relying on a command in
production automation.

Official documentation:

- <https://docs.unity.com/en-us/unity-cli>
- <https://docs.unity.com/en-us/unity-cli/use-unity-cli>
- <https://docs.unity.com/en-us/unity-cli/unity-cli-reference>
- <https://docs.unity.com/en-us/unity-production-pipeline/local-tools-cli/unity-pipeline-package>

## Recommended responsibilities

Use Unity CLI for:

- locating and installing the required Editor version;
- installing build modules;
- opening a project with its declared Editor;
- selecting JSON output and checking exit codes;
- installing the Unity Pipeline package;
- discovering and invoking project-specific verification commands.

Project Brain records the resulting report as evidence; it does not convert a
failed command into a pass.

## Environment checks

```bash
unity --version
unity auth status
unity editors -i --format json
```

Install an Editor and modules when required:

```bash
unity install 6000.3.7f1
unity install-modules -e 6000.3.7f1 -m android
```

Open the project using the Editor version declared by that project:

```bash
unity open /absolute/path/to/UnityProject
```

## Unity Pipeline package

With the Unity project open:

```bash
unity auth login
unity pipeline install
unity pipeline list
unity command --project-path=/absolute/path/to/UnityProject
```

`unity command` displays commands exposed by the connected Editor and Pipeline
package. Automation should select commands from that authoritative list instead
of assuming an undocumented command exists.

## Minimum acceptance gates

After a source or asset mutation, require:

1. Editor import and C# compilation succeed.
2. No new Missing Script components appear.
3. Unity GUIDs and required `.meta` files remain stable.
4. Scene and prefab serialized references resolve.
5. Edit Mode and Play Mode tests required by the project pass.
6. A second apply is either a verified no-op or produces an explained plan.
7. Rollback restores exact hashes for transaction-owned files.

Visual changes additionally require human visual review. A successful compile
does not prove visual quality.

## Automation policy

- Use `--format json` where supported.
- Treat exit code `0` as success, `1` as failure, and `130` as cancellation.
- Capture stdout, stderr, command version, Editor version, project revision,
  start/end timestamps, and selected gate.
- Never parse animated progress output.
- Keep Unity credentials outside Project Brain configuration and evidence.
- Do not expose a running Pipeline or Context API on a public interface by
  default.

Unity CLI and Unity Pipeline are evolving experimental surfaces. Pin the
verified CLI and Editor versions in CI documentation and revalidate commands
before upgrading.
