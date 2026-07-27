import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(moduleDirectory, "..");

export function defaultConfigPath() {
  return (
    process.env.PROJECT_BRAIN_CONFIG ??
    path.join(repositoryRoot, "config", "projects.local.json")
  );
}

export function loadConfiguration(configurationPath = defaultConfigPath()) {
  const absolutePath = path.resolve(configurationPath);
  const document = JSON.parse(fs.readFileSync(absolutePath, "utf8"));

  validateConfiguration(document, absolutePath);
  return {
    ...document,
    configurationPath: absolutePath,
  };
}

export function selectProject(configuration, requestedName) {
  const projects = configuration.projects;
  if (requestedName) {
    const project = projects.find((candidate) => candidate.name === requestedName);
    if (!project) {
      throw new Error(`Unknown project '${requestedName}'.`);
    }

    return project;
  }

  if (projects.length !== 1) {
    throw new Error(
      "A project name is required when more than one project is configured.",
    );
  }

  return projects[0];
}

function validateConfiguration(document, configurationPath) {
  if (document?.schemaVersion !== 1) {
    throw new Error(
      `Unsupported configuration schema in '${configurationPath}'.`,
    );
  }

  if (!Array.isArray(document.projects) || document.projects.length === 0) {
    throw new Error("At least one project must be configured.");
  }

  const names = new Set();
  for (const project of document.projects) {
    if (!project || typeof project.name !== "string" || project.name.length === 0) {
      throw new Error("Every project requires a non-empty name.");
    }

    if (names.has(project.name)) {
      throw new Error(`Duplicate project name '${project.name}'.`);
    }
    names.add(project.name);

    validateAbsoluteDirectory(project.repositoryPath, "repositoryPath", project.name);
    if (project.analysisPath !== undefined) {
      validateAbsoluteDirectory(project.analysisPath, "analysisPath", project.name);
    }
    validateAbsoluteDirectory(
      project.unityProjectPath,
      "unityProjectPath",
      project.name,
    );

    for (const fieldName of [
      "embeddings",
      "generateSkills",
      "readOnlyMcp",
      "skipGit",
      "indexOnly",
    ]) {
      if (
        project[fieldName] !== undefined &&
        typeof project[fieldName] !== "boolean"
      ) {
        throw new Error(
          `Project '${project.name}' has an invalid ${fieldName} value.`,
        );
      }
    }

    if (
      project.indexName !== undefined &&
      (typeof project.indexName !== "string" ||
        project.indexName.trim().length === 0)
    ) {
      throw new Error(
        `Project '${project.name}' has an invalid indexName value.`,
      );
    }

    if (
      project.maxResponseTokens !== undefined &&
      (!Number.isInteger(project.maxResponseTokens) ||
        project.maxResponseTokens <= 0)
    ) {
      throw new Error(
        `Project '${project.name}' has an invalid maxResponseTokens value.`,
      );
    }
  }
}

function validateAbsoluteDirectory(value, fieldName, projectName) {
  if (typeof value !== "string" || !path.isAbsolute(value)) {
    throw new Error(
      `Project '${projectName}' requires an absolute ${fieldName}.`,
    );
  }

  if (!fs.existsSync(value) || !fs.statSync(value).isDirectory()) {
    throw new Error(
      `Project '${projectName}' ${fieldName} does not exist: '${value}'.`,
    );
  }
}
