import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../..");

type EngineResult = {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  json?: unknown;
};

function runEngine(args: string[]): Promise<EngineResult> {
  return new Promise((resolve, reject) => {
    const child = spawn("python3", ["-m", "clawmodeler_engine", ...args], {
      cwd: repoRoot,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      const exitCode = code ?? 1;
      let json: unknown;
      try {
        const trimmed = stdout.trim();
        json = trimmed ? JSON.parse(trimmed) : undefined;
      } catch {
        json = undefined;
      }
      resolve({ ok: exitCode === 0, exitCode, stdout, stderr, json });
    });
  });
}

async function readBody(
  request: import("node:http").IncomingMessage,
): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) {
    return {};
  }
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {};
  }
  return parsed as Record<string, unknown>;
}

function sendJson(
  response: import("node:http").ServerResponse,
  statusCode: number,
  payload: unknown,
) {
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify(payload));
}

function requiredString(body: Record<string, unknown>, key: string): string {
  const value = body[key];
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${key} is required`);
  }
  return value.trim();
}

async function readJsonIfExists(filePath: string): Promise<Record<string, unknown> | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function readTextIfExists(filePath: string): Promise<string | null> {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

const FILE_LIST_LIMIT = 500;
const ARTIFACT_PREVIEW_LIMIT = 128 * 1024;

async function listFiles(root: string): Promise<{ files: string[]; truncated: boolean }> {
  const files: string[] = [];
  let truncated = false;
  type FileEntry = {
    name: string;
    isDirectory(): boolean;
    isFile(): boolean;
  };
  async function walk(current: string) {
    let entries: FileEntry[];
    try {
      entries = (await fs.readdir(current, { withFileTypes: true })) as FileEntry[];
    } catch {
      return;
    }
    for (const entry of entries) {
      if (files.length >= FILE_LIST_LIMIT) {
        truncated = true;
        return;
      }
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  }
  await walk(root);
  return { files: files.toSorted(), truncated };
}

async function listReportFiles(workspace: string, runId: string): Promise<string[]> {
  const reportsDir = path.join(workspace, "reports");
  let entries: Array<{ name: string; isFile(): boolean }>;
  try {
    entries = (await fs.readdir(reportsDir, { withFileTypes: true })) as Array<{
      name: string;
      isFile(): boolean;
    }>;
  } catch {
    return [];
  }
  const prefixes = [`${runId}_`, `${runId}.`];
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((name) => prefixes.some((prefix) => name.startsWith(prefix)))
    .map((name) => path.join(reportsDir, name))
    .toSorted();
}

function indexArtifactFiles(
  workspaceIndex: Record<string, unknown> | null,
  runId: string,
): string[] {
  const artifacts = workspaceIndex?.artifacts;
  if (!Array.isArray(artifacts)) {
    return [];
  }
  return artifacts
    .map((artifact) => asRecord(artifact))
    .filter((artifact) => artifact?.run_id === runId)
    .map((artifact) => artifact?.path)
    .filter((value): value is string => typeof value === "string" && Boolean(value))
    .toSorted();
}

function indexRunString(
  workspaceIndex: Record<string, unknown> | null,
  runId: string,
  key: string,
): string | null {
  const runs = workspaceIndex?.runs;
  if (!Array.isArray(runs)) {
    return null;
  }
  const row = runs
    .map((run) => asRecord(run))
    .find((run) => run?.run_id === runId);
  const value = row?.[key];
  return typeof value === "string" && value ? value : null;
}

async function refreshWorkspaceIndex(
  workspace: string,
  runId: string,
): Promise<Record<string, unknown> | null> {
  const result = await runEngine([
    "data",
    "index",
    "--workspace",
    workspace,
    "--run-id",
    runId,
    "--json",
  ]);
  return result.ok
    ? asRecord(result.json)
    : await readJsonIfExists(path.join(workspace, "logs", "workspace_index.json"));
}

function optionalNumber(body: Record<string, unknown>, key: string): number | null {
  const value = body[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function optionalStringArray(body: Record<string, unknown>, key: string): string[] {
  const value = body[key];
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

async function readArtifactPreview(filePath: string) {
  if (filePath.includes("\0")) {
    throw new Error("artifact path must not contain NUL bytes");
  }
  const stat = await fs.stat(filePath);
  if (!stat.isFile()) {
    throw new Error(`artifact file not found: ${filePath}`);
  }
  const bytes = await fs.readFile(filePath);
  const truncated = bytes.length > ARTIFACT_PREVIEW_LIMIT;
  const content = bytes.subarray(0, ARTIFACT_PREVIEW_LIMIT).toString("utf8");
  return {
    path: filePath,
    sizeBytes: stat.size,
    content,
    truncated,
  };
}

function clawModelerApiPlugin(): Plugin {
  return {
    name: "clawmodeler-api",
    configureServer(server) {
      server.middlewares.use("/api/clawmodeler", async (request, response) => {
        try {
          const url = new URL(request.url ?? "/", "http://127.0.0.1");
          const route = url.pathname;

          if (request.method === "GET" && route === "/doctor") {
            const result = await runEngine(["doctor", "--json"]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (request.method === "GET" && route === "/tools") {
            const result = await runEngine(["tools", "--json"]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (request.method === "GET" && route === "/workspace") {
            const workspace = url.searchParams.get("workspace")?.trim();
            const runId = url.searchParams.get("runId")?.trim() || "demo";
            if (!workspace) {
              throw new Error("workspace is required");
            }
            const workspaceIndex = await refreshWorkspaceIndex(workspace, runId);
            const runRoot = path.join(workspace, "runs", runId);
            let files = indexArtifactFiles(workspaceIndex, runId);
            let truncated = false;
            if (!workspaceIndex) {
              const fallback = await listFiles(runRoot);
              const reportFiles = await listReportFiles(workspace, runId);
              files = [...fallback.files, ...reportFiles].toSorted();
              truncated = fallback.truncated;
            }
            const reportPath =
              indexRunString(workspaceIndex, runId, "report_path") ??
              path.join(workspace, "reports", `${runId}_report.md`);
            const payload = {
              workspace,
              runId,
              manifest: await readJsonIfExists(path.join(runRoot, "manifest.json")),
              qaReport: await readJsonIfExists(path.join(runRoot, "qa_report.json")),
              workflowReport: await readJsonIfExists(path.join(runRoot, "workflow_report.json")),
              reportMarkdown: await readTextIfExists(reportPath),
              files,
              filesTruncated: truncated,
              workspaceIndex,
              indexStatus:
                typeof workspaceIndex?.database_status === "string"
                  ? workspaceIndex.database_status
                  : null,
              indexUpdatedAt:
                typeof workspaceIndex?.created_at === "string"
                  ? workspaceIndex.created_at
                  : null,
            };
            sendJson(response, 200, { ok: true, json: payload });
            return;
          }

          if (request.method !== "POST") {
            sendJson(response, 405, { ok: false, error: "method not allowed" });
            return;
          }

          const body = await readBody(request);
          if (route === "/init") {
            const result = await runEngine([
              "init",
              "--workspace",
              requiredString(body, "workspace"),
            ]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/demo-full") {
            const result = await runEngine([
              "workflow",
              "demo-full",
              "--workspace",
              requiredString(body, "workspace"),
              "--run-id",
              requiredString(body, "runId"),
            ]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/diagnose") {
            const args = ["workflow", "diagnose", "--workspace", requiredString(body, "workspace")];
            const runId = typeof body.runId === "string" ? body.runId.trim() : "";
            if (runId) {
              args.push("--run-id", runId);
            }
            const result = await runEngine(args);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/report-only") {
            const result = await runEngine([
              "workflow",
              "report-only",
              "--workspace",
              requiredString(body, "workspace"),
              "--run-id",
              requiredString(body, "runId"),
            ]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/run") {
            const args = body.args;
            if (!Array.isArray(args) || args.some((item) => typeof item !== "string")) {
              throw new Error("args must be a string array");
            }
            const result = await runEngine(args as string[]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/artifact") {
            const json = await readArtifactPreview(requiredString(body, "path"));
            sendJson(response, 200, { ok: true, json });
            return;
          }

          if (route === "/chat") {
            const args = [
              "chat",
              "--workspace",
              requiredString(body, "workspace"),
              "--run-id",
              requiredString(body, "runId"),
              "--message",
              requiredString(body, "message"),
              "--json",
            ];
            if (body.noHistory === true) {
              args.push("--no-history");
            }
            const result = await runEngine(args);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/what-if") {
            const args = [
              "what-if",
              "--workspace",
              requiredString(body, "workspace"),
              "--base-run-id",
              requiredString(body, "baseRunId"),
              "--new-run-id",
              requiredString(body, "newRunId"),
              "--json",
            ];
            const weights = [
              ["weightSafety", "--weight-safety"],
              ["weightEquity", "--weight-equity"],
              ["weightClimate", "--weight-climate"],
              ["weightFeasibility", "--weight-feasibility"],
            ] as const;
            for (const [bodyKey, argKey] of weights) {
              const value = optionalNumber(body, bodyKey);
              if (value !== null) {
                args.push(argKey, String(value));
              }
            }
            const referenceVmt = optionalNumber(body, "referenceVmtPerCapita");
            if (referenceVmt !== null) {
              args.push("--reference-vmt-per-capita", String(referenceVmt));
            }
            const thresholdPct = optionalNumber(body, "thresholdPct");
            if (thresholdPct !== null) {
              args.push("--threshold-pct", String(thresholdPct));
            }
            for (const projectId of optionalStringArray(body, "includeProjects")) {
              args.push("--include-project", projectId);
            }
            for (const projectId of optionalStringArray(body, "excludeProjects")) {
              args.push("--exclude-project", projectId);
            }
            if (typeof body.sensitivityFloor === "string" && body.sensitivityFloor.trim()) {
              args.push("--sensitivity-floor", body.sensitivityFloor.trim());
            }
            const result = await runEngine(args);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/portfolio") {
            const result = await runEngine([
              "portfolio",
              "--workspace",
              requiredString(body, "workspace"),
              "--json",
            ]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          if (route === "/diff") {
            const result = await runEngine([
              "diff",
              "--workspace",
              requiredString(body, "workspace"),
              "--run-a",
              requiredString(body, "runA"),
              "--run-b",
              requiredString(body, "runB"),
              "--json",
            ]);
            sendJson(response, result.ok ? 200 : 500, result);
            return;
          }

          sendJson(response, 404, { ok: false, error: "not found" });
        } catch (error) {
          sendJson(response, 500, {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      });
    },
  };
}

export default defineConfig({
  root: here,
  build: {
    outDir: path.resolve(repoRoot, "dist/clawmodeler-desktop"),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    host: true,
    port: 5174,
    strictPort: true,
  },
  plugins: [clawModelerApiPlugin()],
});
