#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      continue;
    } else if (arg === "--binary") {
      args.binary = argv[++i];
    } else if (arg === "--version") {
      args.version = argv[++i];
    } else if (arg === "--keep-workspace") {
      args.keepWorkspace = true;
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

function packageVersion() {
  const pkg = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  return pkg.version;
}

function defaultBinaryPath() {
  const suffix = process.platform === "win32" ? ".exe" : "";
  return path.join(repoRoot, "desktop", "src-tauri", "binaries", `clawmodeler-engine${suffix}`);
}

function runEngine(binary, args, options = {}) {
  const result = spawnSync(binary, args, {
    cwd: repoRoot,
    encoding: "utf8",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      [
        `clawmodeler-engine ${args.join(" ")} failed with exit ${result.status}`,
        result.stdout ? `stdout:\n${result.stdout}` : "",
        result.stderr ? `stderr:\n${result.stderr}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  return result.stdout;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assertExists(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`expected file was not written: ${filePath}`);
  }
}

function runSmoke({ binary, version, keepWorkspace }) {
  if (!fs.existsSync(binary) || !fs.statSync(binary).isFile()) {
    throw new Error(`sidecar binary not found: ${binary}`);
  }

  const versionText = runEngine(binary, ["--version"]).trim();
  if (!versionText.includes(version)) {
    throw new Error(`expected sidecar version ${version}, got: ${versionText}`);
  }

  const doctor = JSON.parse(runEngine(binary, ["doctor", "--json"]));
  if (!Array.isArray(doctor.checks) || doctor.checks.length === 0) {
    throw new Error("doctor --json did not return checks");
  }

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-release-sidecar."));
  try {
    const demoWorkspace = path.join(tmp, "demo-workspace");
    runEngine(binary, [
      "workflow",
      "demo-full",
      "--workspace",
      demoWorkspace,
      "--run-id",
      "demo",
    ]);
    assertExists(path.join(demoWorkspace, "runs", "demo", "workflow_report.json"));
    assertExists(path.join(demoWorkspace, "reports", "demo_report.md"));

    const fixture = path.join(repoRoot, "tests", "fixtures", "tiny_region");
    const fixtureWorkspace = path.join(tmp, "fixture-workspace");
    runEngine(binary, [
      "workflow",
      "full",
      "--workspace",
      fixtureWorkspace,
      "--inputs",
      path.join(fixture, "zones.geojson"),
      path.join(fixture, "socio.csv"),
      path.join(fixture, "projects.csv"),
      path.join(fixture, "network_edges.csv"),
      "--question",
      path.join(fixture, "question.json"),
      "--run-id",
      "baseline",
      "--scenarios",
      "baseline",
      "station-growth",
    ]);
    runEngine(binary, [
      "planner-pack",
      "ceqa-vmt",
      "--workspace",
      fixtureWorkspace,
      "--run-id",
      "baseline",
      "--json",
    ]);

    const workflow = readJson(
      path.join(fixtureWorkspace, "runs", "baseline", "workflow_report.json"),
    );
    if (workflow.qa?.export_ready !== true) {
      throw new Error("fixture workflow did not finish export-ready");
    }
    if (workflow.bridge_validation?.export_ready !== true) {
      throw new Error("fixture bridge validation did not finish export-ready");
    }
    assertExists(path.join(fixtureWorkspace, "reports", "baseline_report.md"));
    assertExists(path.join(fixtureWorkspace, "reports", "baseline_ceqa_vmt.md"));
  } finally {
    if (keepWorkspace) {
      console.log(`Kept smoke workspace: ${tmp}`);
    } else {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  }

  console.log(`Release sidecar smoke passed for ${versionText}.`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  runSmoke({
    binary: path.resolve(args.binary || defaultBinaryPath()),
    version: args.version || packageVersion(),
    keepWorkspace: Boolean(args.keepWorkspace),
  });
}

main();
