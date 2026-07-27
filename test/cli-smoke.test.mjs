import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

test("public CLI prints a scoped read-only MCP descriptor", (context) => {
  const temporaryRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "project-brain-cli-"),
  );
  context.after(() =>
    fs.rmSync(temporaryRoot, { recursive: true, force: true }),
  );

  const unityProjectPath = path.join(
    repositoryRoot,
    "examples",
    "unity-project",
    "fixture",
    "UnityProject",
  );
  const analysisPath = path.join(unityProjectPath, "Assets", "Scripts");
  const configurationPath = path.join(temporaryRoot, "projects.json");
  fs.writeFileSync(
    configurationPath,
    `${JSON.stringify(
      {
        schemaVersion: 1,
        projects: [
          {
            name: "fixture",
            repositoryPath: repositoryRoot,
            analysisPath,
            unityProjectPath,
            skipGit: true,
            indexName: "fixture",
            readOnlyMcp: true,
          },
        ],
      },
      null,
      2,
    )}\n`,
  );

  const result = spawnSync(
    process.execPath,
    [
      path.join(repositoryRoot, "src", "cli.mjs"),
      "print-mcp",
      "--project",
      "fixture",
      "--config",
      configurationPath,
    ],
    {
      cwd: repositoryRoot,
      encoding: "utf8",
      shell: false,
    },
  );

  assert.equal(result.status, 0, result.stderr);
  const descriptor = JSON.parse(result.stdout);
  assert.equal(descriptor.type, "stdio");
  assert.equal(descriptor.env.GITNEXUS_MCP_READ_ONLY, "1");
  assert.equal(descriptor.env.GITNEXUS_MCP_ALLOWED_REPOS, analysisPath);
  assert.equal(descriptor.env.GITNEXUS_MCP_DEFAULT_REPO, analysisPath);
});
