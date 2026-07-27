#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const packageName = "com.heycici.project-brain";
const packageRoot = path.join(repositoryRoot, "Packages", packageName);
const releaseVersion = read("VERSION").trim();
const releaseTag = `v${releaseVersion}`;
const repositoryUrl =
  "https://github.com/orange91pku/unity-ai-project-brain.git";
const upmUrl =
  `${repositoryUrl}?path=/Packages/${packageName}#${releaseTag}`;
const failures = [];

check(/^\d+\.\d+\.\d+$/.test(releaseVersion), "VERSION must be SemVer");

const nodePackage = parseJson("package.json");
const unityPackage = parseJson(
  path.join("Packages", packageName, "package.json"),
);
const pyproject = read("pyproject.toml");
const pythonVersion = pyproject.match(
  /^version\s*=\s*"([^"]+)"\s*$/m,
)?.[1];
const pythonModuleVersion = read("project_brain/__init__.py").match(
  /^__version__\s*=\s*"([^"]+)"\s*$/m,
)?.[1];

check(
  nodePackage.version === releaseVersion,
  "package.json version must equal VERSION",
);
check(
  pythonVersion === releaseVersion,
  "pyproject.toml version must equal VERSION",
);
check(
  pythonModuleVersion === releaseVersion,
  "Python __version__ must equal VERSION",
);
check(
  unityPackage.name === packageName,
  `UPM package name must be ${packageName}`,
);
check(
  unityPackage.version === releaseVersion,
  "UPM package version must equal VERSION",
);
check(
  unityPackage.unity === "6000.3",
  "UPM package baseline Unity version must be 6000.3",
);

for (const documentationFile of [
  "README.md",
  "docs/UPM_INSTALL.md",
]) {
  const content = read(documentationFile);
  check(
    content.includes(upmUrl),
    `${documentationFile} must contain the pinned UPM URL`,
  );
  check(
    !content.includes("com.hydracore.project-brain"),
    `${documentationFile} contains a legacy package identity`,
  );
}

const bridgePath =
  "Packages/com.heycici.project-brain/Editor/" +
  "ProjectBrainBridgeWindow.cs";
const bridge = read(bridgePath);
check(
  bridge.includes(`PackageVersion = "${releaseVersion}"`),
  "Unity bridge PackageVersion must equal VERSION",
);
check(
  bridge.includes(`unity-ai-project-brain.git@${releaseTag}`),
  "Unity bridge backend command must pin the release tag",
);

const metaGuids = new Map();
for (const absolutePath of walk(packageRoot)) {
  const relativePath = normalize(path.relative(repositoryRoot, absolutePath));
  if (relativePath.endsWith(".meta")) {
    const bytes = fs.readFileSync(absolutePath);
    check(
      bytes.length > 0 && bytes.at(-1) === 10,
      `${relativePath} must end with LF`,
    );
    const match = bytes.toString("utf8").match(
      /^guid:\s*([a-fA-F0-9]{32})\s*$/m,
    );
    check(Boolean(match), `${relativePath} must contain a valid Unity GUID`);
    if (match) {
      const guid = match[1].toLowerCase();
      check(
        !metaGuids.has(guid),
        `duplicate Unity GUID ${guid}: ${relativePath}`,
      );
      metaGuids.set(guid, relativePath);
    }
  }
  if (
    relativePath.endsWith(".cs") ||
    relativePath.endsWith(".asmdef") ||
    relativePath.endsWith("package.json")
  ) {
    check(
      fs.existsSync(`${absolutePath}.meta`),
      `${relativePath} is missing its .meta file`,
    );
  }
}

const result = {
  status: failures.length === 0 ? "pass" : "fail",
  releaseVersion,
  releaseTag,
  packageName,
  upmUrl,
  unityGuids: metaGuids.size,
  failures,
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
process.exitCode = failures.length === 0 ? 0 : 1;

function read(relativePath) {
  return fs.readFileSync(path.join(repositoryRoot, relativePath), "utf8");
}

function parseJson(relativePath) {
  return JSON.parse(read(relativePath));
}

function check(condition, message) {
  if (!condition) {
    failures.push(message);
  }
}

function* walk(directory) {
  for (const entry of fs
    .readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name))) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      yield* walk(absolutePath);
    } else if (entry.isFile()) {
      yield absolutePath;
    }
  }
}

function normalize(value) {
  return value.replaceAll(path.sep, "/");
}
