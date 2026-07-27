#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const ignoredDirectories = new Set([
  ".git",
  ".gitnexus",
  ".project-brain",
  ".pytest_cache",
  ".state",
  "__pycache__",
  "coverage",
  "node_modules",
]);
const ignoredFiles = new Set([
  "pnpm-lock.yaml",
  "tools/public-audit.mjs",
]);
const requiredFiles = [
  ".gitignore",
  "AGENTS.md",
  "LICENSE",
  "NOTICE",
  "README.md",
  "SECURITY.md",
  "THIRD_PARTY_NOTICES.md",
  "config/projects.example.json",
  "docs/ARCHITECTURE.md",
  "docs/GETTING_STARTED.md",
  "docs/UNITY_CLI.md",
  "llms.txt",
  "package.json",
  "schemas/change-envelope.schema.json",
  "schemas/project-brain-config.schema.json",
];
const forbiddenTrackedPaths = [
  ".state",
  ".gitnexus",
  "config/projects.local.json",
  "node_modules",
];
const contentRules = [
  {
    id: "private-machine-path",
    expression:
      /[A-Za-z]:[\\/](?:Users[\\/]|\_re_recontruct[\\/]|\_package[\\/])/i,
  },
  {
    id: "private-project-identifier",
    expression: /puzzle[-_ ]?drop|ngoch|ironman/i,
  },
  {
    id: "private-tool-identifier",
    expression: /\bre[-_ ]?api\b|\boracle\b|\biris\b|\bre[-_ ]?roslyn\b/i,
  },
  {
    id: "private-key",
    expression: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  },
  {
    id: "credential-assignment",
    expression:
      /\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*["'][^"']{8,}["']/i,
  },
  {
    id: "github-token",
    expression: /\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b/,
  },
];

const failures = [];
for (const relativePath of requiredFiles) {
  if (!fs.existsSync(path.join(repositoryRoot, relativePath))) {
    failures.push(`missing required file: ${relativePath}`);
  }
}
const scannedFiles = [];
visit(repositoryRoot);
for (const absolutePath of scannedFiles) {
  const relativePath = normalize(path.relative(repositoryRoot, absolutePath));
  if (ignoredFiles.has(relativePath)) {
    continue;
  }
  const stat = fs.statSync(absolutePath);
  if (stat.size > 2 * 1024 * 1024 || looksBinary(absolutePath)) {
    continue;
  }
  const content = fs.readFileSync(absolutePath, "utf8");
  for (const rule of contentRules) {
    if (rule.expression.test(content)) {
      failures.push(`${rule.id}: ${relativePath}`);
    }
  }
}

const packageDocument = JSON.parse(
  fs.readFileSync(path.join(repositoryRoot, "package.json"), "utf8"),
);
if (packageDocument.license !== "Apache-2.0") {
  failures.push("package.json must declare Apache-2.0");
}
if (packageDocument.name !== "unity-ai-project-brain") {
  failures.push("package.json must use the public distribution name");
}
if (
  packageDocument.repository?.url !==
  "git+https://github.com/orange91pku/unity-ai-project-brain.git"
) {
  failures.push("package.json must use the canonical public repository");
}
if (packageDocument.dependencies?.gitnexus !== "1.6.9") {
  failures.push("GitNexus must be pinned exactly to 1.6.9");
}
if (fs.existsSync(path.join(repositoryRoot, ".git"))) {
  const tracked = trackedFiles();
  for (const forbiddenPath of forbiddenTrackedPaths) {
    if (
      tracked.some(
        (candidate) =>
          candidate === forbiddenPath ||
          candidate.startsWith(`${forbiddenPath}/`),
      )
    ) {
      failures.push(`forbidden tracked artifact: ${forbiddenPath}`);
    }
  }
}

const result = {
  status: failures.length === 0 ? "pass" : "fail",
  filesScanned: scannedFiles.length,
  failures,
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
process.exitCode = failures.length === 0 ? 0 : 1;

function visit(directory) {
  for (const entry of fs
    .readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name))) {
    if (
      entry.isDirectory() &&
      (ignoredDirectories.has(entry.name) || entry.name.endsWith(".egg-info"))
    ) {
      continue;
    }
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      visit(absolutePath);
    } else if (entry.isFile()) {
      scannedFiles.push(absolutePath);
    }
  }
}

function looksBinary(filePath) {
  return /\.(?:gif|ico|jpe?g|pdf|png|pyc|woff2?|zip)$/i.test(filePath);
}

function normalize(value) {
  return value.replaceAll(path.sep, "/");
}

function trackedFiles() {
  const result = spawnSync(
    "git",
    ["-C", repositoryRoot, "ls-files", "-z"],
    {
      encoding: "utf8",
      shell: false,
    },
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || "git ls-files failed");
  }
  return result.stdout
    .split("\0")
    .filter(Boolean)
    .map((value) => value.replaceAll("\\", "/"));
}
