import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  inspectProjectIndexState,
  inspectFocusedIndexState,
  writeProjectIndexState,
  writeFocusedIndexState,
} from "../src/focused-index-state.mjs";

test("focused index state detects source changes without a Git commit", (context) => {
  const temporaryRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "re-gitnexus-state-"),
  );
  context.after(() => fs.rmSync(temporaryRoot, { recursive: true, force: true }));

  const sourceRoot = path.join(temporaryRoot, "source");
  const stateRoot = path.join(temporaryRoot, "state");
  fs.mkdirSync(path.join(sourceRoot, ".gitnexus"), { recursive: true });
  fs.writeFileSync(path.join(sourceRoot, "Level.cs"), "class Level {}\n");

  const project = {
    name: "focused-fixture",
    repositoryPath: temporaryRoot,
    analysisPath: sourceRoot,
    skipGit: true,
  };

  writeFocusedIndexState(project, stateRoot);
  assert.equal(inspectFocusedIndexState(project, stateRoot).status, "fresh");

  fs.writeFileSync(
    path.join(sourceRoot, "Level.cs"),
    "class Level { int Version = 2; }\n",
  );
  assert.equal(inspectFocusedIndexState(project, stateRoot).status, "stale");
});

test("full index state detects Git revision and dirty content changes", (context) => {
  const temporaryRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "project-brain-git-state-"),
  );
  context.after(() =>
    fs.rmSync(temporaryRoot, { recursive: true, force: true }),
  );
  const repositoryRoot = path.join(temporaryRoot, "repository");
  const stateRoot = path.join(temporaryRoot, "state");
  fs.mkdirSync(repositoryRoot);
  runGit(repositoryRoot, "init");
  runGit(repositoryRoot, "config", "user.email", "test@project-brain.invalid");
  runGit(repositoryRoot, "config", "user.name", "Project Brain Test");
  fs.writeFileSync(path.join(repositoryRoot, "Player.cs"), "class Player {}\n");
  runGit(repositoryRoot, "add", "Player.cs");
  runGit(repositoryRoot, "commit", "-m", "fixture");
  fs.mkdirSync(path.join(repositoryRoot, ".gitnexus"));

  const project = {
    name: "full-fixture",
    repositoryPath: repositoryRoot,
    unityProjectPath: repositoryRoot,
  };
  writeProjectIndexState(project, stateRoot);
  assert.equal(
    inspectProjectIndexState(project, stateRoot).status,
    "fresh",
  );

  fs.writeFileSync(
    path.join(repositoryRoot, "Player.cs"),
    "class Player { int Version = 2; }\n",
  );
  assert.equal(
    inspectProjectIndexState(project, stateRoot).status,
    "stale",
  );
});

function runGit(repositoryRoot, ...argumentsToPass) {
  const result = spawnSync(
    "git",
    ["-C", repositoryRoot, ...argumentsToPass],
    {
      encoding: "utf8",
      shell: false,
    },
  );
  assert.equal(result.status, 0, result.stderr);
}
