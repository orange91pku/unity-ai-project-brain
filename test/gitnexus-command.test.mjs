import assert from "node:assert/strict";
import test from "node:test";
import {
  buildInvocation,
  buildMcpDescriptor,
  buildMcpEnvironment,
  resolveGitNexusRuntime,
} from "../src/gitnexus-command.mjs";

const project = {
  name: "fixture",
  repositoryPath: "/fixture/repository",
  unityProjectPath: "/fixture/repository/unity",
  embeddings: true,
  generateSkills: false,
  readOnlyMcp: true,
  maxResponseTokens: 4096,
};

const focusedProject = {
  ...project,
  name: "fixture-game-core",
  analysisPath: "/fixture/repository/unity/Assets/Scripts/Game",
  embeddings: true,
  skipGit: true,
  indexName: "fixture-game-core",
  indexOnly: true,
};

test("analyze enables embeddings and keeps generated skills disabled", () => {
  const invocation = buildInvocation("analyze", project);

  assert.deepEqual(invocation.arguments, [
    "analyze",
    project.repositoryPath,
    "--embeddings",
    "--skip-skills",
    "--skip-agents-md",
  ]);
});

test("focused analysis creates a named semantic index without requiring a nested Git repository", () => {
  const invocation = buildInvocation("analyze", focusedProject);

  assert.deepEqual(invocation.arguments, [
    "analyze",
    focusedProject.analysisPath,
    "--skip-git",
    "--name",
    "fixture-game-core",
    "--embeddings",
    "--index-only",
    "--skip-skills",
    "--skip-agents-md",
  ]);
  assert.equal(invocation.workingDirectory, focusedProject.analysisPath);
});

test("focused MCP is restricted to the analyzed source subtree", () => {
  const environment = buildMcpEnvironment(focusedProject);

  assert.equal(
    environment.GITNEXUS_MCP_ALLOWED_REPOS,
    focusedProject.analysisPath,
  );
  assert.equal(
    environment.GITNEXUS_MCP_DEFAULT_REPO,
    focusedProject.analysisPath,
  );
});

test("MCP is restricted to the selected repository and read-only by default", () => {
  const environment = buildMcpEnvironment(project);

  assert.equal(environment.GITNEXUS_MCP_READ_ONLY, "1");
  assert.equal(
    environment.GITNEXUS_MCP_ALLOWED_REPOS,
    project.repositoryPath,
  );
  assert.equal(
    environment.GITNEXUS_MCP_DEFAULT_REPO,
    project.repositoryPath,
  );
  assert.equal(environment.GITNEXUS_MCP_DEFAULT_MAX_TOKENS, "4096");
});

test("MCP descriptor is suitable for Codex stdio configuration", () => {
  const descriptor = buildMcpDescriptor(project);

  assert.equal(descriptor.type, "stdio");
  assert.equal(descriptor.command, process.execPath);
  assert.equal(descriptor.args.at(-1), "mcp");
  assert.match(
    descriptor.args[0],
    /node_modules[\\/]gitnexus[\\/]dist[\\/]cli[\\/]index\.js$/,
  );
  assert.equal(
    descriptor.env.GITNEXUS_MCP_ALLOWED_REPOS,
    project.repositoryPath,
  );
});

test("a configured GitNexus executable overrides local discovery", () => {
  const runtime = resolveGitNexusRuntime({
    PROJECT_BRAIN_GITNEXUS_BIN: "/tools/gitnexus",
  });

  assert.equal(runtime.command, "/tools/gitnexus");
  assert.deepEqual(runtime.argumentPrefix, []);
});
