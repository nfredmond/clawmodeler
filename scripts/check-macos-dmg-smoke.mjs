#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sidecarSmokeScript = path.join(repoRoot, "scripts", "check-release-sidecar.mjs");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      continue;
    } else if (arg === "--dmg") {
      args.dmg = argv[++i];
    } else if (arg === "--tag") {
      args.tag = argv[++i];
    } else if (arg === "--version") {
      args.version = argv[++i];
    } else if (arg === "--self-test") {
      args.selfTest = true;
    } else if (arg === "--skip-launch") {
      args.skipLaunch = true;
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

function versionFromTag(tag) {
  if (!tag) {
    return null;
  }
  const match = /^v(\d+\.\d+\.\d+)(?:-rc\.\d+)?$/.exec(tag);
  if (!match) {
    throw new Error(`release tag must look like vX.Y.Z or vX.Y.Z-rc.N, got ${tag}`);
  }
  return match[1];
}

function expectedDmgName(version) {
  return `ClawModeler_${version}_aarch64.dmg`;
}

function run(command, args, options = {}) {
  console.log(`[macos-dmg-smoke] ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      [
        `${command} ${args.join(" ")} failed with exit ${result.status}`,
        result.stdout ? `stdout:\n${result.stdout}` : "",
        result.stderr ? `stderr:\n${result.stderr}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  if (result.stdout?.trim()) {
    console.log(result.stdout.trim());
  }
  if (result.stderr?.trim()) {
    console.error(result.stderr.trim());
  }
  return result.stdout;
}

function walkEntries(root) {
  const entries = [];
  function walk(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      entries.push(fullPath);
      if (entry.isDirectory() && !entry.name.endsWith(".app")) {
        walk(fullPath);
      }
    }
  }
  walk(root);
  return entries;
}

function findApp(root) {
  const apps = walkEntries(root).filter((entry) => entry.endsWith(`${path.sep}ClawModeler.app`));
  if (apps.length !== 1) {
    throw new Error(`expected exactly one ClawModeler.app in ${root}, found ${apps.length}`);
  }
  return apps[0];
}

function findPackagedEngine(appPath) {
  const candidates = walkEntries(appPath).filter((entry) => path.basename(entry) === "clawmodeler-engine");
  const executableCandidates = candidates.filter((entry) => {
    try {
      const stat = fs.statSync(entry);
      return stat.isFile() && (stat.mode & 0o111) !== 0;
    } catch {
      return false;
    }
  });
  if (executableCandidates.length !== 1) {
    throw new Error(
      `expected exactly one executable clawmodeler-engine in ${appPath}, found ${executableCandidates.length}`,
    );
  }
  return executableCandidates[0];
}

function findWeasyPrintRuntime(appPath) {
  const candidates = walkEntries(appPath).filter((entry) => {
    try {
      return path.basename(entry) === "weasyprint-runtime" && fs.statSync(entry).isDirectory();
    } catch {
      return false;
    }
  });
  if (candidates.length !== 1) {
    throw new Error(`expected exactly one weasyprint-runtime directory in ${appPath}, found ${candidates.length}`);
  }
  const files = walkEntries(candidates[0]).filter((entry) => fs.statSync(entry).isFile());
  if (files.length === 0) {
    throw new Error(`weasyprint-runtime directory is empty: ${candidates[0]}`);
  }
  return candidates[0];
}

function plistValue(appPath, key) {
  return run("/usr/libexec/PlistBuddy", [
    "-c",
    `Print:${key}`,
    path.join(appPath, "Contents", "Info.plist"),
  ]).trim();
}

function mountDmg(dmgPath, mountPoint) {
  fs.mkdirSync(mountPoint, { recursive: true });
  run("hdiutil", ["attach", dmgPath, "-readonly", "-nobrowse", "-mountpoint", mountPoint]);
}

function detachDmg(mountPoint) {
  const result = spawnSync("hdiutil", ["detach", mountPoint], { encoding: "utf8" });
  if (result.status !== 0) {
    spawnSync("hdiutil", ["detach", mountPoint, "-force"], { encoding: "utf8" });
  }
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function findLaunchedAppProcess(appPath, executableName) {
  const result = spawnSync("ps", ["-axo", "pid=,comm=,command="], { encoding: "utf8" });
  if (result.status !== 0) {
    return "";
  }
  const executablePathPrefix = path.join(appPath, "Contents", "MacOS");
  return result.stdout
    .split(/\r?\n/)
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return false;
      }
      const parts = trimmed.split(/\s+/);
      const comm = parts[1] || "";
      const command = parts.slice(2).join(" ");
      return (
        path.basename(comm) === executableName ||
        path.basename(comm) === "ClawModeler" ||
        command.includes(executablePathPrefix)
      );
    })
    .join("\n");
}

function launchApp(appPath, bundleIdentifier, executableName) {
  spawnSync("xattr", ["-dr", "com.apple.quarantine", appPath], { encoding: "utf8" });
  run("open", ["-n", appPath]);

  const deadline = Date.now() + 30_000;
  let processList = "";
  while (Date.now() < deadline) {
    processList = findLaunchedAppProcess(appPath, executableName);
    if (processList.trim()) {
      console.log(`[macos-dmg-smoke] app process detected:\n${processList.trim()}`);
      break;
    }
    sleep(1000);
  }
  if (!processList.trim()) {
    throw new Error("ClawModeler.app did not appear in the process list after launch");
  }

  spawnSync("osascript", ["-e", `tell application id "${bundleIdentifier}" to quit`], {
    encoding: "utf8",
  });
  spawnSync("pkill", ["-x", executableName], { encoding: "utf8" });
  spawnSync("pkill", ["-x", "ClawModeler"], { encoding: "utf8" });
}

function runSmoke({ dmg, version, skipLaunch }) {
  if (process.platform !== "darwin") {
    throw new Error("macOS DMG smoke must run on macOS");
  }
  const dmgPath = path.resolve(dmg);
  if (!fs.existsSync(dmgPath) || !fs.statSync(dmgPath).isFile()) {
    throw new Error(`DMG not found: ${dmgPath}`);
  }
  if (path.basename(dmgPath) !== expectedDmgName(version)) {
    throw new Error(`expected DMG name ${expectedDmgName(version)}, got ${path.basename(dmgPath)}`);
  }

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-macos-dmg."));
  const mountPoint = path.join(tmp, "mnt");
  const installRoot = path.join(tmp, "install");
  let mounted = false;
  try {
    mountDmg(dmgPath, mountPoint);
    mounted = true;
    const mountedApp = findApp(mountPoint);
    fs.mkdirSync(installRoot);
    const installedApp = path.join(installRoot, "ClawModeler.app");
    run("ditto", [mountedApp, installedApp]);

    const bundleVersion = plistValue(installedApp, "CFBundleShortVersionString");
    if (bundleVersion !== version) {
      throw new Error(`expected CFBundleShortVersionString ${version}, got ${bundleVersion}`);
    }
    const bundleIdentifier = plistValue(installedApp, "CFBundleIdentifier");
    if (bundleIdentifier !== "ai.openclaw.clawmodeler") {
      throw new Error(`unexpected CFBundleIdentifier: ${bundleIdentifier}`);
    }
    const executableName = plistValue(installedApp, "CFBundleExecutable");

    const engine = findPackagedEngine(installedApp);
    const runtime = findWeasyPrintRuntime(installedApp);
    console.log(`[macos-dmg-smoke] packaged engine: ${engine}`);
    console.log(`[macos-dmg-smoke] WeasyPrint runtime: ${runtime}`);
    run("node", [sidecarSmokeScript, "--binary", engine, "--version", version]);

    if (!skipLaunch) {
      launchApp(installedApp, bundleIdentifier, executableName);
    }
    console.log(`macOS DMG smoke passed for ${path.basename(dmgPath)}.`);
  } finally {
    if (mounted) {
      detachDmg(mountPoint);
    }
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function selfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-macos-dmg-self-test."));
  try {
    const appPath = path.join(tmp, "ClawModeler.app");
    const enginePath = path.join(appPath, "Contents", "Resources", "binaries", "clawmodeler-engine");
    const runtimePath = path.join(appPath, "Contents", "Resources", "binaries", "weasyprint-runtime");
    fs.mkdirSync(path.dirname(enginePath), { recursive: true });
    fs.mkdirSync(runtimePath, { recursive: true });
    fs.writeFileSync(enginePath, "");
    fs.chmodSync(enginePath, 0o755);
    fs.writeFileSync(path.join(runtimePath, "libpango.dylib"), "");
    if (expectedDmgName("1.2.3") !== "ClawModeler_1.2.3_aarch64.dmg") {
      throw new Error("unexpected DMG asset name");
    }
    if (versionFromTag("v1.2.3-rc.4") !== "1.2.3") {
      throw new Error("rc tag did not map to base version");
    }
    if (findApp(tmp) !== appPath) {
      throw new Error("findApp failed");
    }
    if (findPackagedEngine(appPath) !== enginePath) {
      throw new Error("findPackagedEngine failed");
    }
    if (findWeasyPrintRuntime(appPath) !== runtimePath) {
      throw new Error("findWeasyPrintRuntime failed");
    }
    console.log("macOS DMG smoke self-test passed");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) {
    selfTest();
    return;
  }
  const version = args.version || versionFromTag(args.tag) || packageVersion();
  if (!args.dmg) {
    throw new Error("usage: check-macos-dmg-smoke.mjs --dmg ClawModeler_X.Y.Z_aarch64.dmg [--tag vX.Y.Z-rc.N]");
  }
  runSmoke({ dmg: args.dmg, version, skipLaunch: Boolean(args.skipLaunch) });
}

main();
