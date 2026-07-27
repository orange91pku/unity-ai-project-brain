import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

export function buildInvocation(action, project) {
  const analysisPath = resolveAnalysisPath(project);

  switch (action) {
    case "doctor":
      return {
        arguments: ["doctor"],
        workingDirectory: project.repositoryPath,
        environment: {},
      };
    case "analyze":
      return {
        arguments: [
          "analyze",
          analysisPath,
          ...(project.skipGit ? ["--skip-git"] : []),
          ...(project.indexName ? ["--name", project.indexName] : []),
          project.embeddings === false ? "--skip-embeddings" : "--embeddings",
          ...(project.indexOnly ? ["--index-only"] : []),
          ...(project.generateSkills ? ["--skills"] : ["--skip-skills"]),
          "--skip-agents-md",
        ],
        workingDirectory: analysisPath,
        environment: {},
      };
    case "status":
      return {
        arguments: ["status"],
        workingDirectory: analysisPath,
        environment: {},
      };
    case "mcp":
      return {
        arguments: ["mcp"],
        workingDirectory: analysisPath,
        environment: buildMcpEnvironment(project),
      };
    default:
      throw new Error(`Unsupported GitNexus action '${action}'.`);
  }
}

export function buildMcpEnvironment(project) {
  const analysisPath = resolveAnalysisPath(project);
  return {
    GITNEXUS_MCP_READ_ONLY: project.readOnlyMcp === false ? "0" : "1",
    GITNEXUS_MCP_ALLOWED_REPOS: analysisPath,
    GITNEXUS_MCP_DEFAULT_REPO: analysisPath,
    GITNEXUS_MCP_DEFAULT_MAX_TOKENS: String(
      project.maxResponseTokens ?? 6000,
    ),
  };
}

export function resolveAnalysisPath(project) {
  return project.analysisPath ?? project.repositoryPath;
}

export function buildMcpDescriptor(project) {
  const runtime = resolveGitNexusRuntime();
  return {
    type: "stdio",
    command: runtime.command,
    args: [...runtime.argumentPrefix, "mcp"],
    env: buildMcpEnvironment(project),
  };
}

export function resolveGitNexusRuntime(environment = process.env) {
  const configuredExecutable = environment.PROJECT_BRAIN_GITNEXUS_BIN;
  if (configuredExecutable) {
    return {
      command: configuredExecutable,
      argumentPrefix: [],
    };
  }

  const localCliPath = path.join(
    repositoryRoot,
    "node_modules",
    "gitnexus",
    "dist",
    "cli",
    "index.js",
  );
  if (fs.existsSync(localCliPath)) {
    return {
      command: process.execPath,
      argumentPrefix: [localCliPath],
    };
  }

  return {
    command: "gitnexus",
    argumentPrefix: [],
  };
}
