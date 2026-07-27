import fs from "node:fs";
import path from "node:path";

const supportedSources = new Set([
  "git-diff",
  "unity-asset-postprocessor",
  "merged",
]);

export function loadChangeEnvelope(envelopePath) {
  const absolutePath = path.resolve(envelopePath);
  const document = JSON.parse(fs.readFileSync(absolutePath, "utf8"));
  validateChangeEnvelope(document, absolutePath);
  return {
    ...document,
    envelopePath: absolutePath,
  };
}

export function validateChangeEnvelope(document, source = "change envelope") {
  if (document?.schemaVersion !== 1) {
    throw new Error(`Unsupported schemaVersion in '${source}'.`);
  }

  if (
    typeof document.envelopeId !== "string" ||
    !/^change:[0-9a-f]{64}$/.test(document.envelopeId)
  ) {
    throw new Error(`Invalid envelopeId in '${source}'.`);
  }

  if (!supportedSources.has(document.source)) {
    throw new Error(`Unsupported envelope source in '${source}'.`);
  }

  if (!Array.isArray(document.changes)) {
    throw new Error(`Envelope '${source}' requires a changes array.`);
  }

  for (const [index, change] of document.changes.entries()) {
    if (
      !change ||
      typeof change.path !== "string" ||
      change.path.length === 0 ||
      !Array.isArray(change.invalidates)
    ) {
      throw new Error(`Invalid changes[${index}] in '${source}'.`);
    }
  }
}

export function planChangeEnvelope(project, envelope) {
  validateChangeEnvelope(envelope);
  const repositoryRoot = path.resolve(project.repositoryPath);
  const unityProjectRoot = path.resolve(project.unityProjectPath);
  const analysisRoot = path.resolve(
    project.analysisPath ?? project.repositoryPath,
  );
  const affectedPaths = new Set();
  const ignoredPaths = new Set();
  const invalidations = new Set();

  for (const change of envelope.changes) {
    const candidates = [change.path, change.oldPath].filter(Boolean);
    let affectsIndex = false;
    for (const candidate of candidates) {
      const resolved = resolveEnvelopePath(
        candidate,
        repositoryRoot,
        unityProjectRoot,
      );
      if (isWithin(analysisRoot, resolved)) {
        affectsIndex = true;
        affectedPaths.add(normalizeForReport(resolved, repositoryRoot));
      } else {
        ignoredPaths.add(normalizeForReport(resolved, repositoryRoot));
      }
    }

    if (affectsIndex) {
      for (const invalidation of change.invalidates) {
        invalidations.add(invalidation);
      }
    }
  }

  const requiresReindex =
    invalidations.has("gitnexus.path") ||
    invalidations.has("gitnexus.code");
  const downstreamActions = [];
  if (
    invalidations.has("roslyn.compilation") ||
    invalidations.has("roslyn.symbol-catalog")
  ) {
    downstreamActions.push("refresh-roslyn-symbol-catalog");
  }
  if (
    invalidations.has("unity.serialized-objects") ||
    invalidations.has("unity.references") ||
    invalidations.has("unity.asset-identity")
  ) {
    downstreamActions.push("update-unity-object-graph");
  }
  if (invalidations.has("unity.script-symbol-bridge")) {
    downstreamActions.push("refresh-roslyn-unity-identity-bridge");
  }

  return {
    schemaVersion: 1,
    project: project.name,
    envelopeId: envelope.envelopeId,
    source: envelope.source,
    analysisPath: analysisRoot,
    affectedPaths: [...affectedPaths].sort(),
    ignoredPaths: [...ignoredPaths].sort(),
    invalidations: [...invalidations].sort(),
    requiresReindex,
    reindexMode: requiresReindex ? "full-project-analyze" : "none",
    reason: requiresReindex
      ? "The pinned GitNexus CLI has no safe per-symbol incremental writer; rebuild the selected project index."
      : "No indexed GitNexus path or code partition was invalidated.",
    commands: requiresReindex
      ? [`pnpm run analyze -- --project ${project.name}`]
      : [],
    downstreamActions: [...new Set(downstreamActions)].sort(),
  };
}

function resolveEnvelopePath(value, repositoryRoot, unityProjectRoot) {
  const normalized = value.replaceAll("\\", "/").replace(/^\/+/, "");
  const firstSegment = normalized.split("/", 1)[0].toLowerCase();
  if (["assets", "packages", "projectsettings"].includes(firstSegment)) {
    return path.resolve(unityProjectRoot, ...normalized.split("/"));
  }

  return path.resolve(repositoryRoot, ...normalized.split("/"));
}

function isWithin(root, candidate) {
  const relative = path.relative(root, candidate);
  return (
    relative === "" ||
    (!relative.startsWith("..") && !path.isAbsolute(relative))
  );
}

function normalizeForReport(absolutePath, repositoryRoot) {
  const relative = path.relative(repositoryRoot, absolutePath);
  if (!relative.startsWith("..") && !path.isAbsolute(relative)) {
    return relative.replaceAll(path.sep, "/");
  }

  return absolutePath.replaceAll(path.sep, "/");
}
