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
    } else if (arg === "--python") {
      args.python = argv[++i];
    } else if (arg === "--keep-workspace") {
      args.keepWorkspace = true;
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

function pythonCommand(preferred) {
  const candidates = preferred ? [preferred] : ["python3", "python"];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (result.status === 0) {
      return candidate;
    }
  }
  throw new Error(`could not find a Python interpreter from: ${candidates.join(", ")}`);
}

function engineRunner(args) {
  if (args.binary) {
    return {
      command: path.resolve(args.binary),
      prefix: [],
      label: path.resolve(args.binary),
    };
  }
  const python = pythonCommand(args.python);
  return {
    command: python,
    prefix: ["-m", "clawmodeler_engine"],
    label: `${python} -m clawmodeler_engine`,
  };
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: [repoRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      PYTHONUNBUFFERED: "1",
    },
    ...options,
  });
  if (result.error && result.status !== 0) {
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
  return result.stdout;
}

function runEngine(engine, args) {
  return run(engine.command, [...engine.prefix, ...args]);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertExists(filePath) {
  assert(fs.existsSync(filePath), `expected file was not written: ${filePath}`);
}

function refreshIndex(engine, workspace, runId = null) {
  const args = ["data", "index", "--workspace", workspace, "--json"];
  if (runId) {
    args.splice(4, 0, "--run-id", runId);
  }
  const summary = JSON.parse(runEngine(engine, args));
  const diskSummary = readJson(path.join(workspace, "logs", "workspace_index.json"));
  assert(diskSummary.created_at === summary.created_at, "workspace_index.json was not refreshed");
  return summary;
}

function findRun(index, runId) {
  return (index.runs || []).find((run) => run.run_id === runId);
}

function findQa(index, runId) {
  return (index.qa || []).find((qa) => qa.run_id === runId);
}

function assertBaselineIndexed(index) {
  const baseline = findRun(index, "baseline");
  const qa = findQa(index, "baseline");
  assert(index.run_count >= 1, "workspace index did not record any runs");
  assert(Boolean(baseline), "workspace index did not include baseline run");
  assert(baseline.export_ready === true, "baseline run was not export-ready in the index");
  assert(qa?.export_ready === true, "baseline QA was not export-ready in the index");
  assert(Array.isArray(qa?.blockers) && qa.blockers.length === 0, "baseline QA has blockers");
  assert(index.artifact_count > 0, "workspace index did not record generated artifacts");
  assert(index.bridge_readiness_count >= 4, "workspace index missed bridge readiness rows");
}

function assertPlannerPackIndexed(index) {
  const baseline = findRun(index, "baseline");
  const artifacts = baseline?.planner_pack_artifacts || [];
  assert(artifacts.includes("ceqa_vmt"), "CEQA Planner Pack artifact is not visible in index");
}

function assertPortfolioIndexed(index, expectedRows) {
  assert(index.portfolio_run_count === expectedRows, `expected ${expectedRows} portfolio rows`);
  assert(
    (index.portfolio_runs || []).every((row) => row.export_ready === true),
    "portfolio includes a run that is not export-ready",
  );
}

function assertDiffIndexed(index) {
  const diff = (index.diffs || []).find(
    (candidate) => candidate.run_a_id === "baseline" && candidate.run_b_id === "safety-heavy",
  );
  assert(index.diff_count >= 1, "workspace index did not record run diffs");
  assert(Boolean(diff), "baseline vs safety-heavy diff is not visible in index");
  assert(diff.totals?.changed >= 1, "baseline diff did not record changed rows");
}

function runFirstUserSmoke({ engine, keepWorkspace }) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "clawmodeler-first-user."));
  const workspace = path.join(tmp, "planner-workspace");
  const fixture = path.join(repoRoot, "tests", "fixtures", "tiny_region");

  try {
    console.log(`Running first-user release smoke with ${engine.label}`);

    runEngine(engine, ["init", "--workspace", workspace]);
    assertExists(path.join(workspace, "inputs"));

    runEngine(engine, [
      "workflow",
      "full",
      "--workspace",
      workspace,
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
    let focusedIndex = refreshIndex(engine, workspace, "baseline");
    assertBaselineIndexed(focusedIndex);
    assertExists(path.join(workspace, "reports", "baseline_report.md"));

    runEngine(engine, [
      "planner-pack",
      "ceqa-vmt",
      "--workspace",
      workspace,
      "--run-id",
      "baseline",
      "--json",
    ]);
    focusedIndex = refreshIndex(engine, workspace, "baseline");
    assertPlannerPackIndexed(focusedIndex);
    assertExists(path.join(workspace, "reports", "baseline_ceqa_vmt.md"));

    runEngine(engine, [
      "what-if",
      "--workspace",
      workspace,
      "--base-run-id",
      "baseline",
      "--new-run-id",
      "safety-heavy",
      "--weight-safety",
      "0.40",
      "--weight-equity",
      "0.25",
      "--weight-climate",
      "0.20",
      "--weight-feasibility",
      "0.15",
      "--json",
    ]);
    runEngine(engine, ["portfolio", "--workspace", workspace, "--json"]);
    const workspaceIndex = refreshIndex(engine, workspace);
    assertBaselineIndexed(workspaceIndex);
    assertPlannerPackIndexed(workspaceIndex);
    assertPortfolioIndexed(workspaceIndex, 2);
    assertExists(path.join(workspace, "reports", "portfolio.md"));

    runEngine(engine, [
      "diff",
      "--workspace",
      workspace,
      "--run-a",
      "baseline",
      "--run-b",
      "safety-heavy",
      "--json",
    ]);
    focusedIndex = refreshIndex(engine, workspace, "baseline");
    assertBaselineIndexed(focusedIndex);
    assertPlannerPackIndexed(focusedIndex);
    assertPortfolioIndexed(focusedIndex, 1);
    assertDiffIndexed(focusedIndex);
    assertExists(path.join(workspace, "reports", "baseline_vs_safety-heavy_diff.md"));

    const workflow = readJson(path.join(workspace, "runs", "baseline", "workflow_report.json"));
    assert(
      workflow.routing?.selected_source === "network_edges_csv",
      "first-user fixture did not use the staged network_edges.csv routing source",
    );
    assert(
      workflow.bridge_validation?.detailed_forecast_ready === false,
      "fixture should remain blocked from detailed forecast claims",
    );

    const result = [
      "First-user release smoke passed.",
      `indexed_artifacts=${focusedIndex.artifact_count}`,
      `portfolio_rows=${workspaceIndex.portfolio_run_count}`,
      `diffs=${focusedIndex.diff_count}`,
    ];
    if (keepWorkspace) {
      result.splice(1, 0, `workspace=${workspace}`);
    }
    console.log(result.join(" "));
  } finally {
    if (keepWorkspace) {
      console.log(`Kept smoke workspace: ${tmp}`);
    } else {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  }
}

const args = parseArgs(process.argv.slice(2));
runFirstUserSmoke({
  engine: engineRunner(args),
  keepWorkspace: Boolean(args.keepWorkspace),
});
