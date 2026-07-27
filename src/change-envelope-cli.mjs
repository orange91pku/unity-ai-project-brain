#!/usr/bin/env node

import path from "node:path";
import {
  defaultConfigPath,
  loadConfiguration,
  selectProject,
} from "./config.mjs";
import {
  loadChangeEnvelope,
  planChangeEnvelope,
} from "./change-envelope.mjs";

const parsed = parseArguments(process.argv.slice(2));
const configuration = loadConfiguration(parsed.configurationPath);
const project = selectProject(configuration, parsed.projectName);
const envelope = loadChangeEnvelope(parsed.envelopePath);
const plan = planChangeEnvelope(project, envelope);

process.stdout.write(`${JSON.stringify(plan, null, 2)}\n`);

function parseArguments(argumentsToParse) {
  let projectName;
  let envelopePath;
  let configurationPath = defaultConfigPath();

  for (let index = 0; index < argumentsToParse.length; index += 1) {
    const argument = argumentsToParse[index];
    if (argument === "--") {
      continue;
    } else if (argument === "--project") {
      projectName = requireValue(argumentsToParse, ++index, argument);
    } else if (argument === "--config") {
      configurationPath = path.resolve(
        requireValue(argumentsToParse, ++index, argument),
      );
    } else if (argument === "--envelope") {
      envelopePath = path.resolve(
        requireValue(argumentsToParse, ++index, argument),
      );
    } else {
      throw new Error(`Unknown argument '${argument}'.`);
    }
  }

  if (!envelopePath) {
    throw new Error(
      "Usage: change-envelope-cli.mjs --envelope <path> " +
        "[--project <name>] [--config <path>]",
    );
  }

  return {
    projectName,
    envelopePath,
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
