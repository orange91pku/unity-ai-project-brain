import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolveAnalysisPath } from "./gitnexus-command.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const ignoredDirectoryNames = new Set([
  ".git",
  ".gitnexus",
  "Library",
  "Temp",
  "node_modules",
  "obj",
]);

export function computeSourceFingerprint(sourceRoot) {
  const hash = crypto.createHash("sha256");
  let fileCount = 0;

  visitDirectory(sourceRoot, sourceRoot, hash, () => {
    fileCount += 1;
  });

  return {
    algorithm: "sha256",
    value: hash.digest("hex"),
    fileCount,
  };
}

export function writeFocusedIndexState(
  project,
  stateDirectory = path.join(repositoryRoot, ".state"),
) {
  return writeProjectIndexState(project, stateDirectory);
}

export function writeProjectIndexState(
  project,
  stateDirectory = path.join(repositoryRoot, ".state"),
) {
  const analysisPath = resolveAnalysisPath(project);
  const state = {
    schemaVersion: 1,
    project: project.name,
    analysisPath,
    indexedAt: new Date().toISOString(),
    fingerprint: project.skipGit
      ? computeSourceFingerprint(analysisPath)
      : computeGitFingerprint(project.repositoryPath),
  };

  fs.mkdirSync(stateDirectory, { recursive: true });
  fs.writeFileSync(
    stateFilePath(project, stateDirectory),
    `${JSON.stringify(state, null, 2)}\n`,
    "utf8",
  );
  return state;
}

export function inspectFocusedIndexState(
  project,
  stateDirectory = path.join(repositoryRoot, ".state"),
) {
  return inspectProjectIndexState(project, stateDirectory);
}

export function inspectProjectIndexState(
  project,
  stateDirectory = path.join(repositoryRoot, ".state"),
) {
  const analysisPath = resolveAnalysisPath(project);
  const indexPath = path.join(analysisPath, ".gitnexus");
  const filePath = stateFilePath(project, stateDirectory);

  if (!fs.existsSync(indexPath) || !fs.existsSync(filePath)) {
    return {
      status: "missing",
      analysisPath,
      indexPath,
    };
  }

  const recorded = JSON.parse(fs.readFileSync(filePath, "utf8"));
  const currentFingerprint = project.skipGit
    ? computeSourceFingerprint(analysisPath)
    : computeGitFingerprint(project.repositoryPath);
  return {
    status:
      recorded.analysisPath === analysisPath &&
      recorded.fingerprint?.value === currentFingerprint.value
        ? "fresh"
        : "stale",
    analysisPath,
    indexPath,
    indexedAt: recorded.indexedAt,
    recordedFingerprint: recorded.fingerprint,
    currentFingerprint,
  };
}

export function computeGitFingerprint(repositoryPath) {
  const repository = path.resolve(repositoryPath);
  const revision = runGit(repository, ["rev-parse", "HEAD"]).trim();
  const status = runGit(repository, [
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
  ]);
  const changedPaths = new Set([
    ...nullDelimitedPaths(
      runGit(repository, ["diff", "--name-only", "-z"]),
    ),
    ...nullDelimitedPaths(
      runGit(repository, ["diff", "--cached", "--name-only", "-z"]),
    ),
    ...nullDelimitedPaths(
      runGit(repository, [
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
      ]),
    ),
  ]);
  const hash = crypto.createHash("sha256");
  hash.update(revision);
  hash.update("\0");
  hash.update(status);
  hash.update("\0");
  for (const relativePath of [...changedPaths].sort()) {
    hash.update(relativePath);
    hash.update("\0");
    const absolutePath = path.join(
      repository,
      ...relativePath.split("/"),
    );
    if (fs.existsSync(absolutePath) && fs.statSync(absolutePath).isFile()) {
      hash.update(fs.readFileSync(absolutePath));
    } else {
      hash.update("<deleted>");
    }
    hash.update("\0");
  }
  return {
    algorithm: "git-head-worktree-sha256",
    value: hash.digest("hex"),
    fileCount: changedPaths.size,
    revision,
    dirty: status.length > 0,
  };
}

function stateFilePath(project, stateDirectory) {
  const safeName = project.name.replace(/[^a-zA-Z0-9._-]/g, "_");
  return path.join(stateDirectory, `${safeName}.json`);
}

function runGit(repositoryPath, argumentsToPass) {
  const result = spawnSync(
    "git",
    ["-C", repositoryPath, ...argumentsToPass],
    {
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
      shell: false,
    },
  );
  if (result.status !== 0) {
    throw new Error(
      result.stderr?.trim() ||
        `git ${argumentsToPass.join(" ")} failed.`,
    );
  }
  return result.stdout;
}

function nullDelimitedPaths(value) {
  return value
    .split("\0")
    .filter(Boolean)
    .map((candidate) => candidate.replaceAll("\\", "/"));
}

function visitDirectory(sourceRoot, directory, hash, onFile) {
  const entries = fs
    .readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name));

  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!ignoredDirectoryNames.has(entry.name)) {
        visitDirectory(sourceRoot, absolutePath, hash, onFile);
      }
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    const relativePath = path
      .relative(sourceRoot, absolutePath)
      .replaceAll(path.sep, "/");
    hash.update(relativePath);
    hash.update("\0");
    hash.update(fs.readFileSync(absolutePath));
    hash.update("\0");
    onFile();
  }
}
