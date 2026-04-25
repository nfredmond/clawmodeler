#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { expectedReleaseAssets, validateReleaseAssets } from "./check-release-assets.mjs";
import { assertConsistentVersions } from "./check-version-consistency.mjs";
import { latestPolicy } from "./release-latest-policy.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

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
    } else if (arg === "--out") {
      args.out = argv[++i];
    } else if (arg === "--json-out") {
      args.jsonOut = argv[++i];
    } else if (arg === "--tags") {
      args.tags = argv[++i];
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

export function parseCandidateTag(tag) {
  const normalizedTag = String(tag || "").trim();
  const match = /^v(\d+\.\d+\.\d+)(?:-rc\.(\d+))?$/.exec(normalizedTag);
  if (!match) {
    throw new Error(`candidate tag must look like vX.Y.Z or vX.Y.Z-rc.N, got ${tag}`);
  }
  const rcNumber = match[2] === undefined ? null : Number(match[2]);
  return {
    tag: normalizedTag,
    version: match[1],
    finalTag: `v${match[1]}`,
    kind: rcNumber === null ? "final" : "release-candidate",
    prerelease: rcNumber !== null,
    rcNumber,
  };
}

function parseTagList(value) {
  return String(value || "")
    .split(/[\s,]+/u)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function readGitTags() {
  const output = execFileSync("git", ["tag", "--list", "v*"], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  return parseTagList(output);
}

function assertIncludes(content, needle, filePath) {
  if (!content.includes(needle)) {
    throw new Error(`${filePath} is missing dry-run release proof text: ${needle}`);
  }
}

function validateWorkflowDryRunGuard() {
  const relativePath = ".github/workflows/release.yml";
  const content = fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
  const required = [
    "workflow_dispatch:",
    "candidate_tag:",
    "dry-run-readiness:",
    "if: github.event_name == 'workflow_dispatch'",
    "pnpm release:dry-run -- --tag",
    "release-dry-run-proof.md",
    "release-dry-run-proof.json",
    "if: startsWith(github.ref, 'refs/tags/v')",
  ];
  for (const needle of required) {
    assertIncludes(content, needle, relativePath);
  }
  return {
    workflow: relativePath,
    dryRunJob: "dry-run-readiness",
    publishGuard: "startsWith(github.ref, 'refs/tags/v')",
  };
}

export function collectReadinessProof({ tag, dir, tags }) {
  const candidate = parseCandidateTag(tag);
  const versionResult = assertConsistentVersions();
  if (versionResult.version !== candidate.version) {
    throw new Error(
      `candidate tag ${candidate.tag} expects version ${candidate.version}, ` +
        `but version files are ${versionResult.version}`,
    );
  }

  const assetResult = validateReleaseAssets(candidate.tag, dir);
  const tagList = tags === undefined ? readGitTags() : parseTagList(tags);
  const finalPolicy = latestPolicy(candidate.finalTag, tagList);
  const workflowGuard = validateWorkflowDryRunGuard();
  const assetNames = assetResult.files.map((file) => path.basename(file)).toSorted();

  return {
    generated_at: new Date().toISOString(),
    candidate_tag: candidate.tag,
    candidate_kind: candidate.kind,
    base_version: candidate.version,
    prerelease: candidate.prerelease,
    rc_number: candidate.rcNumber,
    artifact_dir: path.resolve(dir),
    asset_count: assetNames.length,
    expected_assets: expectedReleaseAssets(candidate.tag),
    found_assets: assetNames,
    version_files: versionResult.versions,
    github_release: {
      prerelease: candidate.prerelease,
      make_latest: candidate.prerelease ? false : finalPolicy.makeLatest,
      final_tag_make_latest: finalPolicy.makeLatest,
      highest_semver_tag: finalPolicy.highestTag,
    },
    workflow_guard: workflowGuard,
    checks: [
      "candidate tag format",
      "version consistency",
      "installer asset manifest",
      "rc/final release policy",
      "workflow dispatch dry-run guard",
      "tag-only publish guard",
    ],
  };
}

export function formatMarkdown(summary) {
  const versionLines = Object.entries(summary.version_files)
    .map(([file, version]) => `- \`${file}\`: \`${version}\``)
    .join("\n");
  const assetLines = summary.found_assets.map((asset) => `- \`${asset}\``).join("\n");
  const modeLine =
    summary.candidate_kind === "release-candidate"
      ? `Release candidate RC.${summary.rc_number} (\`prerelease=true\`, \`make_latest=false\`)`
      : `Final release (\`prerelease=false\`, \`make_latest=${summary.github_release.make_latest}\`)`;

  return [
    "# ClawModeler Release Dry-Run Proof",
    "",
    `Generated: ${summary.generated_at}`,
    `Candidate tag: \`${summary.candidate_tag}\``,
    `Candidate mode: ${modeLine}`,
    `Base version: \`${summary.base_version}\``,
    `Artifact directory: \`${summary.artifact_dir}\``,
    "",
    "## Automated Checks",
    "",
    `- [x] Candidate tag is a supported RC or final SemVer release tag.`,
    `- [x] All version fields match \`${summary.base_version}\`.`,
    `- [x] Dry-run artifacts contain exactly ${summary.asset_count} expected installer assets.`,
    "- [x] RC/final GitHub release policy is resolved before any public tag exists.",
    "- [x] Workflow dispatch dry-run readiness job is present.",
    "- [x] GitHub release publication remains guarded to pushed `v*` tags.",
    "",
    "## GitHub Release Policy",
    "",
    `- \`prerelease\`: \`${summary.github_release.prerelease}\``,
    `- \`make_latest\`: \`${summary.github_release.make_latest}\``,
    `- Final tag Latest candidate: \`${summary.github_release.final_tag_make_latest}\``,
    `- Highest known SemVer tag: \`${summary.github_release.highest_semver_tag || ""}\``,
    "",
    "## Version Fields",
    "",
    versionLines,
    "",
    "## Installer Assets",
    "",
    assetLines,
    "",
    "## Dry-Run Scope",
    "",
    "- [x] This proof does not create a Git tag.",
    "- [x] This proof does not publish a GitHub release.",
    "- [x] The matrix artifacts can be validated as an RC or final candidate before the public tag.",
    "- Manual GUI first-run evidence is outside this headless proof; this job does not gate on it.",
    "",
  ].join("\n");
}

function writeOutput(filePath, content) {
  fs.mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

function writeProof(summary, args) {
  const markdown = formatMarkdown(summary);
  if (args.out) {
    writeOutput(args.out, markdown);
  } else {
    console.log(markdown);
  }
  if (args.jsonOut) {
    writeOutput(args.jsonOut, `${JSON.stringify(summary, null, 2)}\n`);
  }
}

function seedAssets(dir, tag) {
  for (const asset of expectedReleaseAssets(tag)) {
    fs.writeFileSync(path.join(dir, asset), "");
  }
}

function selfTest() {
  const { version } = assertConsistentVersions();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-release-dry-run."));
  try {
    const rcTag = `v${version}-rc.99`;
    const finalTag = `v${version}`;
    seedAssets(tmp, rcTag);

    const rcSummary = collectReadinessProof({
      tag: rcTag,
      dir: tmp,
      tags: "v0.9.6 v0.9.5",
    });
    if (!rcSummary.prerelease || rcSummary.github_release.make_latest !== false) {
      throw new Error("RC dry-run proof did not resolve prerelease/latest policy correctly");
    }

    const finalSummary = collectReadinessProof({
      tag: finalTag,
      dir: tmp,
      tags: "v0.9.6 v0.9.5",
    });
    if (finalSummary.prerelease || finalSummary.github_release.make_latest !== true) {
      throw new Error("final dry-run proof did not resolve latest policy correctly");
    }

    const proofPath = path.join(tmp, "proof.md");
    const jsonPath = path.join(tmp, "proof.json");
    writeProof(rcSummary, { out: proofPath, jsonOut: jsonPath });
    const proof = fs.readFileSync(proofPath, "utf8");
    if (!proof.includes("Manual GUI first-run evidence is outside this headless proof")) {
      throw new Error("dry-run proof should describe the headless validation scope");
    }
    JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log("release dry-run readiness self-test passed");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) {
    selfTest();
    return;
  }
  if (!args.tag || !args.dir) {
    throw new Error("usage: check-release-dry-run.mjs --tag vX.Y.Z[-rc.N] --dir artifacts");
  }
  const summary = collectReadinessProof(args);
  writeProof(summary, args);
  console.log(
    `Release dry-run readiness passed for ${summary.candidate_tag} with ${summary.asset_count} assets.`,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main();
}
