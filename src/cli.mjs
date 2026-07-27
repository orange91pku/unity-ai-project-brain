#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import {
  defaultConfigPath,
  loadConfiguration,
  selectProject,
} from "./config.mjs";
import {
  buildInvocation,
  buildMcpDescriptor,
  resolveGitNexusRuntime,
} from "./gitnexus-command.mjs";
import {
  inspectProjectIndexState,
  writeProjectIndexState,
} from "./focused-index-state.mjs";

const parsed = parseArguments(process.argv.slice(2));
const configuration = loadConfiguration(parsed.configurationPath);
const project = selectProject(configuration, parsed.projectName);

validateProjectRepository(project);

if (parsed.action === "status") {
  printProjectStatus(project);
  process.exit(0);
}

if (parsed.action === "print-mcp") {
  process.stdout.write(`${JSON.stringify(buildMcpDescriptor(project), null, 2)}\n`);
  process.exit(0);
}

const invocation = buildInvocation(parsed.action, project);
const runtime = resolveGitNexusRuntime();
const result = spawnSync(
  runtime.command,
  [...runtime.argumentPrefix, ...invocation.arguments],
  {
    cwd: invocation.workingDirectory,
    env: {
      ...process.env,
      ...invocation.environment,
    },
    stdio: "inherit",
    shell: false,
  },
);

if (result.error) {
  console.error(
    `[project-brain] Could not start '${runtime.command}': ${result.error.message}`,
  );
  process.exit(2);
}

if (result.status === 0 && parsed.action === "analyze") {
  const state = writeProjectIndexState(project);
  console.log(
    "[project-brain] Recorded " +
      `${state.fingerprint.algorithm} source baseline.`,
  );
}

process.exit(result.status ?? 1);

function parseArguments(argumentsToParse) {
  const action = argumentsToParse[0];
  const supportedActions = new Set([
    "doctor",
    "analyze",
    "status",
    "mcp",
    "print-mcp",
  ]);

  if (!supportedActions.has(action)) {
    throw new Error(
      "Usage: cli.mjs <doctor|analyze|status|mcp|print-mcp> " +
        "[--project <name>] [--config <path>]",
    );
  }

  let projectName;
  let configurationPath = defaultConfigPath();

  for (let index = 1; index < argumentsToParse.length; index += 1) {
    const argument = argumentsToParse[index];
    if (argument === "--project") {
      projectName = requireValue(argumentsToParse, ++index, argument);
    } else if (argument === "--config") {
      configurationPath = path.resolve(
        requireValue(argumentsToParse, ++index, argument),
      );
    } else {
      throw new Error(`Unknown argument '${argument}'.`);
    }
  }

  return {
    action,
    projectName,
    configurationPath,
  };
}

function requireValue(argumentsToParse, index, option) {
  const value = argumentsToParse[index];
  if (!value) {
    throw new Error(`Option '${option}' requires a value.`);
  }

  return value;
}

function validateProjectRepository(projectToValidate) {
  if (projectToValidate.skipGit) {
    return;
  }

  const result = spawnSync(
    "git",
    [
      "-C",
      projectToValidate.repositoryPath,
      "rev-parse",
      "--is-inside-work-tree",
    ],
    {
      encoding: "utf8",
      shell: false,
    },
  );
  if (result.status !== 0 || result.stdout.trim() !== "true") {
    throw new Error(
      `Configured repository is not a Git worktree: '${projectToValidate.repositoryPath}'.`,
    );
  }
}

function printProjectStatus(projectToInspect) {
  const result = inspectProjectIndexState(projectToInspect);
  console.log(`Repository: ${result.analysisPath}`);
  console.log(`Index: ${result.indexPath}`);

  if (result.indexedAt) {
    console.log(`Indexed: ${result.indexedAt}`);
  }

  if (result.status === "fresh") {
    console.log(
      "Status: up-to-date " +
        `(${result.currentFingerprint.algorithm})`,
    );
  } else if (result.status === "stale") {
    console.log("Status: stale (source fingerprint changed)");
  } else {
    console.log("Status: missing baseline (re-run gitnexus analyze)");
  }
}
