#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
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
    } else if (arg === "--current") {
      args.current = argv[++i];
    } else if (arg === "--tags") {
      args.tags = argv[++i];
    } else if (arg === "--github-output") {
      args.githubOutput = argv[++i];
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

export function parseSemverTag(tag) {
  const match = /^v(\d+)\.(\d+)\.(\d+)$/.exec(tag.trim());
  if (!match) return null;
  return {
    tag: tag.trim(),
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

function compareSemver(a, b) {
  return a.major - b.major || a.minor - b.minor || a.patch - b.patch;
}

export function latestPolicy(currentTag, tags) {
  const current = parseSemverTag(currentTag);
  if (!current) {
    return { makeLatest: false, highestTag: null };
  }
  const versions = tags.map(parseSemverTag).filter(Boolean);
  if (!versions.some((item) => item.tag === current.tag)) {
    versions.push(current);
  }
  const highest = versions.toSorted(compareSemver).at(-1);
  return {
    makeLatest: Boolean(highest && highest.tag === current.tag),
    highestTag: highest?.tag ?? current.tag,
  };
}

function readGitTags() {
  const output = execFileSync("git", ["tag", "--list", "v[0-9]*.[0-9]*.[0-9]*"], {
    encoding: "utf8",
  });
  return output.split(/\r?\n/u).map((line) => line.trim()).filter(Boolean);
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

function selfTest() {
  assertEqual(
    latestPolicy("v0.9.4", ["v0.9.2", "v0.9.3", "v0.9.4"]).makeLatest,
    true,
    "highest current tag",
  );
  assertEqual(
    latestPolicy("v0.9.3", ["v0.9.2", "v0.9.3", "v0.9.4"]).makeLatest,
    false,
    "older current tag",
  );
  assertEqual(
    latestPolicy("v0.10.0", ["v0.9.9", "v0.10.0"]).makeLatest,
    true,
    "minor version ordering",
  );
  assertEqual(
    latestPolicy("v0.9.5", ["v0.9.5-rc.1", "v0.9.4"]).makeLatest,
    true,
    "ignore prerelease suffixes",
  );
  console.log("release latest-policy self-test passed");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) {
    selfTest();
    return;
  }

  const current = args.current || process.env.GITHUB_REF_NAME || "";
  if (!current) {
    throw new Error("current tag is required; pass --current or set GITHUB_REF_NAME");
  }
  const tags = args.tags
    ? args.tags.split(/[\s,]+/u).map((tag) => tag.trim()).filter(Boolean)
    : readGitTags();
  const policy = latestPolicy(current, tags);
  const makeLatest = policy.makeLatest ? "true" : "false";
  console.log(`current_tag=${current}`);
  console.log(`highest_tag=${policy.highestTag ?? ""}`);
  console.log(`make_latest=${makeLatest}`);
  if (args.githubOutput) {
    fs.appendFileSync(
      args.githubOutput,
      `make_latest=${makeLatest}\nhighest_tag=${policy.highestTag ?? ""}\n`,
      "utf8",
    );
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main();
}
