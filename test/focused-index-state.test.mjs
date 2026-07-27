import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  inspectFocusedIndexState,
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
