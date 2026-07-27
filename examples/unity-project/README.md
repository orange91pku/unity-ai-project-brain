# Unity project example

Copy `config/projects.example.json` to `config/projects.local.json`, then replace
every placeholder with an absolute path on your machine.

For a typical repository:

```text
my-game/
  .git/
  UnityProject/
    Assets/
    Packages/
    ProjectSettings/
```

Use one full repository index for exact context and one focused code index for
fast semantic retrieval. Generated `.gitnexus` indexes and local configuration
must remain uncommitted.

Copy `.gitnexusignore.example` to the analysis root as `.gitnexusignore` and
adapt it to the repository. Keep first-party source and Unity text assets;
exclude generated caches, builds, vendor packages, and recovered outputs that
do not belong in the AI context.
