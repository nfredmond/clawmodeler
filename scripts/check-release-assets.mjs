#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      continue;
    } else if (arg === "--self-test") {
      args.selfTest = true;
    } else if (arg === "--tag") {
      args.tag = argv[++i];
    } else if (arg === "--dir") {
      args.dir = argv[++i];
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

export function expectedReleaseAssets(tag) {
  const match = /^v(\d+\.\d+\.\d+)(?:-rc\.\d+)?$/.exec(tag);
  if (!match) {
    throw new Error(`release tag must look like vX.Y.Z or vX.Y.Z-rc.N, got ${tag}`);
  }
  const version = match[1];
  return [
    `ClawModeler-${version}-1.x86_64.rpm`,
    `ClawModeler_${version}_aarch64.dmg`,
    `ClawModeler_${version}_amd64.AppImage`,
    `ClawModeler_${version}_amd64.deb`,
    `ClawModeler_${version}_x64-setup.exe`,
    `ClawModeler_${version}_x64_en-US.msi`,
  ];
}

export function isPrereleaseTag(tag) {
  return /^v\d+\.\d+\.\d+-rc\.\d+$/.test(tag);
}

function listFiles(root) {
  const files = [];
  function walk(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  }
  walk(root);
  return files;
}

export function validateReleaseAssets(tag, dir) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
    throw new Error(`asset directory not found: ${dir}`);
  }
  const expected = expectedReleaseAssets(tag);
  const expectedSet = new Set(expected);
  const files = listFiles(dir);
  const names = files.map((file) => path.basename(file)).toSorted();
  const missing = expected.filter((name) => !names.includes(name));
  const unexpected = names.filter((name) => !expectedSet.has(name));
  const duplicates = names.filter((name, index) => names.indexOf(name) !== index);
  if (missing.length || unexpected.length || duplicates.length) {
    throw new Error(
      [
        missing.length ? `missing: ${missing.join(", ")}` : "",
        unexpected.length ? `unexpected: ${unexpected.join(", ")}` : "",
        duplicates.length ? `duplicates: ${duplicates.join(", ")}` : "",
      ]
        .filter(Boolean)
        .join("; "),
    );
  }
  return { expected, files };
}

function selfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-release-assets."));
  try {
    for (const asset of expectedReleaseAssets("v1.2.3")) {
      fs.writeFileSync(path.join(tmp, asset), "");
    }
    validateReleaseAssets("v1.2.3", tmp);
    fs.writeFileSync(path.join(tmp, "ClawModeler_1.2.2_amd64.deb"), "");
    let failed = false;
    try {
      validateReleaseAssets("v1.2.3", tmp);
    } catch {
      failed = true;
    }
    if (!failed) {
      throw new Error("expected unexpected asset to fail validation");
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  // Pre-release tags share asset names with their base version.
  const rcExpected = expectedReleaseAssets("v1.2.3-rc.1");
  const finalExpected = expectedReleaseAssets("v1.2.3");
  if (JSON.stringify(rcExpected) !== JSON.stringify(finalExpected)) {
    throw new Error(
      `rc tag should produce same asset names as final; rc=${JSON.stringify(rcExpected)} final=${JSON.stringify(finalExpected)}`,
    );
  }
  if (!isPrereleaseTag("v1.2.3-rc.1")) {
    throw new Error("isPrereleaseTag should return true for v1.2.3-rc.1");
  }
  if (isPrereleaseTag("v1.2.3")) {
    throw new Error("isPrereleaseTag should return false for v1.2.3");
  }

  console.log("release asset self-test passed");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) {
    selfTest();
    return;
  }
  if (!args.tag || !args.dir) {
    throw new Error("usage: check-release-assets.mjs --tag vX.Y.Z --dir artifacts");
  }
  const result = validateReleaseAssets(args.tag, args.dir);
  console.log(`Verified ${result.files.length} release assets for ${args.tag}.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main();
}
