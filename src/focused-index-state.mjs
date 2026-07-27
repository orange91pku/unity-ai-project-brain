import crypto from "node:crypto";
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
  const analysisPath = resolveAnalysisPath(project);
  const state = {
    schemaVersion: 1,
    project: project.name,
    analysisPath,
    indexedAt: new Date().toISOString(),
    fingerprint: computeSourceFingerprint(analysisPath),
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
  const currentFingerprint = computeSourceFingerprint(analysisPath);
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

function stateFilePath(project, stateDirectory) {
  const safeName = project.name.replace(/[^a-zA-Z0-9._-]/g, "_");
  return path.join(stateDirectory, `${safeName}.json`);
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
