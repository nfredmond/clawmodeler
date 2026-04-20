#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

function jsonVersion(relativePath) {
  return JSON.parse(read(relativePath)).version;
}

function regexVersion(relativePath, pattern, label) {
  const match = pattern.exec(read(relativePath));
  if (!match) {
    throw new Error(`Could not read ${label} version from ${relativePath}`);
  }
  return match[1];
}

function cargoLockPackageVersion(packageName) {
  const lock = read("desktop/src-tauri/Cargo.lock");
  const packageSections = lock.split(/\n\[\[package\]\]\n/g);
  for (const section of packageSections) {
    if (new RegExp(`\\nname = "${packageName}"\\n`).test(`\n${section}`)) {
      const match = /\nversion = "([^"]+)"/.exec(`\n${section}`);
      if (match) {
        return match[1];
      }
    }
  }
  throw new Error(`Could not read ${packageName} version from Cargo.lock`);
}

export function collectVersions() {
  return {
    "package.json": jsonVersion("package.json"),
    "pyproject.toml": regexVersion(
      "pyproject.toml",
      /\[project\][\s\S]*?\nversion = "([^"]+)"/,
      "Python package",
    ),
    "clawmodeler_engine/workspace.py": regexVersion(
      "clawmodeler_engine/workspace.py",
      /ENGINE_VERSION = "([^"]+)"/,
      "engine",
    ),
    "desktop/src-tauri/Cargo.toml": regexVersion(
      "desktop/src-tauri/Cargo.toml",
      /\[package\][\s\S]*?\nversion = "([^"]+)"/,
      "Cargo package",
    ),
    "desktop/src-tauri/Cargo.lock": cargoLockPackageVersion("clawmodeler-desktop"),
    "desktop/src-tauri/tauri.conf.json": jsonVersion("desktop/src-tauri/tauri.conf.json"),
  };
}

export function assertConsistentVersions() {
  const versions = collectVersions();
  const unique = [...new Set(Object.values(versions))];
  if (unique.length !== 1) {
    throw new Error(
      `Version fields disagree:\n${Object.entries(versions)
        .map(([file, version]) => `  ${file}: ${version}`)
        .join("\n")}`,
    );
  }
  return { version: unique[0], versions };
}

function main() {
  const result = assertConsistentVersions();
  console.log(`Version fields are consistent at ${result.version}.`);
}

main();
