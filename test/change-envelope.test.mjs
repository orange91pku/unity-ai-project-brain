import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  planChangeEnvelope,
  validateChangeEnvelope,
} from "../src/change-envelope.mjs";

function fixture() {
  const repositoryPath = fs.mkdtempSync(
    path.join(os.tmpdir(), "re-gitnexus-envelope-"),
  );
  const unityProjectPath = path.join(repositoryPath, "Unity");
  const analysisPath = path.join(
    unityProjectPath,
    "Assets",
    "Scripts",
    "Core",
  );
  fs.mkdirSync(analysisPath, { recursive: true });
  return {
    repositoryPath,
    unityProjectPath,
    analysisPath,
  };
}

function envelope() {
  return {
    schemaVersion: 1,
    envelopeId: `change:${"a".repeat(64)}`,
    projectId: "fixture",
    source: "merged",
    generatedUtc: "2026-07-25T00:00:00Z",
    baseRevision: null,
    targetRevision: "UNITY_EDITOR",
    policyVersion: "unity-brain-v1",
    changes: [
      {
        status: "modified",
        path: "Assets/Scripts/Core/Player.cs",
        oldPath: null,
        unityGuid: "1".repeat(32),
        contentHash: "2".repeat(64),
        lane: "code",
        invalidates: [
          "gitnexus.code",
          "gitnexus.path",
          "roslyn.symbol-catalog",
          "unity.script-symbol-bridge",
        ],
      },
      {
        status: "modified",
        path: "Assets/Prefabs/Player.prefab",
        oldPath: null,
        unityGuid: "3".repeat(32),
        contentHash: "4".repeat(64),
        lane: "unitySerialized",
        invalidates: [
          "gitnexus.path",
          "unity.serialized-objects",
        ],
      },
    ],
  };
}

test("focused project plans only changes inside its analysis root", (context) => {
  const paths = fixture();
  context.after(() =>
    fs.rmSync(paths.repositoryPath, { recursive: true, force: true }),
  );
  const plan = planChangeEnvelope(
    {
      name: "game-core",
      ...paths,
    },
    envelope(),
  );

  assert.equal(plan.requiresReindex, true);
  assert.equal(plan.reindexMode, "full-project-analyze");
  assert.deepEqual(plan.affectedPaths, [
    "Unity/Assets/Scripts/Core/Player.cs",
  ]);
  assert.deepEqual(plan.ignoredPaths, [
    "Unity/Assets/Prefabs/Player.prefab",
  ]);
  assert.deepEqual(plan.downstreamActions, [
    "refresh-roslyn-symbol-catalog",
    "refresh-roslyn-unity-identity-bridge",
  ]);
});

test("full repository project includes Unity graph invalidations", (context) => {
  const paths = fixture();
  context.after(() =>
    fs.rmSync(paths.repositoryPath, { recursive: true, force: true }),
  );
  const plan = planChangeEnvelope(
    {
      name: "full",
      ...paths,
      analysisPath: paths.repositoryPath,
    },
    envelope(),
  );

  assert.equal(plan.affectedPaths.length, 2);
  assert.ok(plan.downstreamActions.includes("update-unity-object-graph"));
});

test("invalid envelope identity is rejected", () => {
  const document = envelope();
  document.envelopeId = "not-a-change-id";
  assert.throws(
    () => validateChangeEnvelope(document),
    /Invalid envelopeId/,
  );
});
