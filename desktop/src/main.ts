import "./styles.css";
import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import {
  artifactBasename,
  buildBridgeExecuteArgs,
  buildDiffArgs,
  buildFullWorkflowArgs,
  buildPlannerPackArgs,
  type ChatTurn,
  chatTurnBadge,
  DEFAULT_WHAT_IF_WEIGHTS,
  deriveWorkflowGuide,
  deriveQuestionSavePath,
  findProjectWorkspace,
  formatDacShare,
  formatMeanScore,
  friendlyError,
  isPreviewableArtifact,
  manifestOutputCategories,
  normalizePathList,
  normalizeScenarios,
  parseChatTurn,
  parseProjectState,
  parsePortfolioPayload,
  type PlannerPackKind,
  PLANNER_PACK_SPECS,
  type PortfolioResult,
  type PortfolioRun,
  type PortfolioSortDirection,
  type PortfolioSortKey,
  type ProjectRunStateInput,
  type ProjectWorkspaceRecord,
  projectRunLabel,
  rebalanceWhatIfWeights,
  segmentChatText,
  serializeProjectState,
  sortPortfolioRuns,
  summarizeRunArtifacts,
  summarizeQa,
  toggleRunSelection,
  upsertProjectRunState,
  validateDiffSelection,
  validatePlannerPackForm,
  validateWhatIfForm,
  whatIfWeightSum,
  type WhatIfWeights,
  type WorkflowGuideStep,
  workspaceDisplayName,
} from "./workbench.js";

type ApiResult<T = unknown> = {
  ok: boolean;
  exitCode?: number;
  stdout?: string;
  stderr?: string;
  json?: T;
  jsonParseError?: string;
  error?: string;
};

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

type ToolCheck = {
  name: string;
  id: string;
  status: string;
  detail: string;
  category: string;
  profile: string;
};

type DoctorResult = {
  ok: boolean;
  checks: ToolCheck[];
};

type WorkspaceArtifacts = {
  workspace: string;
  runId: string;
  manifest: Record<string, unknown> | null;
  qaReport: Record<string, unknown> | null;
  workflowReport: Record<string, unknown> | null;
  reportMarkdown: string | null;
  files: string[];
  filesTruncated: boolean;
  workspaceIndex?: Record<string, unknown> | null;
  indexStatus?: string | null;
  indexUpdatedAt?: string | null;
};

type ArtifactPreview = {
  path: string;
  sizeBytes: number;
  content: string;
  truncated: boolean;
};

type ArtifactPreviewState = {
  selectedPath: string;
  preview: ArtifactPreview | null;
  busy: boolean;
  status: string;
};

type PortfolioState = {
  result: PortfolioResult | null;
  selectedRunIds: string[];
  sortKey: PortfolioSortKey;
  sortDirection: PortfolioSortDirection;
  busy: boolean;
  status: string;
  lastDiffPath: string | null;
};

type WhatIfState = {
  baseRunId: string;
  newRunId: string;
  weightsEnabled: boolean;
  weights: WhatIfWeights;
  referenceVmtPerCapita: string;
  thresholdPct: string;
  includeProjects: string;
  excludeProjects: string;
  sensitivityFloor: string;
  busy: boolean;
  status: string;
  lastResult: Record<string, unknown> | null;
};

type PlannerPackState = {
  kind: PlannerPackKind;
  cycleYear: string;
  analysisYear: string;
  busy: boolean;
  status: string;
  lastResult: Record<string, unknown> | null;
};

type BridgeExecutionState = {
  bridge: string;
  scenarioId: string;
  dryRun: boolean;
  busy: boolean;
  status: string;
  lastResult: Record<string, unknown> | null;
};

type BridgeToolFeedback = {
  id: string;
  command: string;
  available: boolean;
  path: string | null;
  note: string | null;
};

type BridgeOperatorFeedback = {
  operatorSummary: string;
  operatorStatus: string;
  evidenceLevel: string;
  forecastReadinessStatus: string | null;
  commandDisplay: string | null;
  commandCwd: string | null;
  requiredTools: BridgeToolFeedback[];
  expectedOutputs: string[];
  existingOutputs: string[];
  missingOutputs: string[];
  outputSummary: {
    expectedCount: number | null;
    existingCount: number | null;
    missingCount: number | null;
  };
  nextSteps: string[];
};

type AppState = {
  workspace: string;
  runId: string;
  runLabel: string;
  inputPaths: string;
  questionPath: string;
  scenarios: string;
  skipBridges: boolean;
  routingSource: string;
  routingGraphId: string;
  routingImpedance: string;
  busy: boolean;
  status: string;
  doctor: DoctorResult | null;
  artifacts: WorkspaceArtifacts | null;
  artifactPreview: ArtifactPreviewState;
  commandLog: string[];
  onboarded: boolean;
  chatTurns: ChatTurn[];
  chatDraft: string;
  chatBusy: boolean;
  chatNoHistory: boolean;
  chatStatus: string;
  plannerPack: PlannerPackState;
  bridgeExecution: BridgeExecutionState;
  whatIf: WhatIfState;
  portfolio: PortfolioState;
  projectState: ProjectWorkspaceRecord[];
};

const PROJECT_STATE_KEY = "clawmodeler.projectState.v1";
const initialProjectState = parseProjectState(localStorage.getItem(PROJECT_STATE_KEY));
const initialWorkspace =
  localStorage.getItem("clawmodeler.workspace") || "/tmp/clawmodeler-workbench";
const initialRunId = localStorage.getItem("clawmodeler.runId") || "demo";
const initialRunLabel =
  localStorage.getItem("clawmodeler.runLabel") ||
  projectRunLabel(initialProjectState, initialWorkspace, initialRunId) ||
  initialRunId;

const state: AppState = {
  workspace: initialWorkspace,
  runId: initialRunId,
  runLabel: initialRunLabel,
  inputPaths: localStorage.getItem("clawmodeler.inputPaths") || "",
  questionPath: localStorage.getItem("clawmodeler.questionPath") || "",
  scenarios: localStorage.getItem("clawmodeler.scenarios") || "baseline",
  skipBridges: localStorage.getItem("clawmodeler.skipBridges") === "true",
  routingSource: localStorage.getItem("clawmodeler.routingSource") || "question",
  routingGraphId: localStorage.getItem("clawmodeler.routingGraphId") || "",
  routingImpedance: localStorage.getItem("clawmodeler.routingImpedance") || "minutes",
  busy: false,
  status: "Ready",
  doctor: null,
  artifacts: null,
  artifactPreview: {
    selectedPath: "",
    preview: null,
    busy: false,
    status: "Pick an artifact to preview.",
  },
  commandLog: [],
  onboarded: localStorage.getItem("clawmodeler.onboarded") === "true",
  chatTurns: [],
  chatDraft: "",
  chatBusy: false,
  chatNoHistory: false,
  chatStatus: "",
  plannerPack: {
    kind: (localStorage.getItem("clawmodeler.plannerPack.kind") as PlannerPackKind) || "ceqa-vmt",
    cycleYear: localStorage.getItem("clawmodeler.plannerPack.cycleYear") || "2027",
    analysisYear: localStorage.getItem("clawmodeler.plannerPack.analysisYear") || "2027",
    busy: false,
    status: "",
    lastResult: null,
  },
  bridgeExecution: {
    bridge: localStorage.getItem("clawmodeler.bridgeExecution.bridge") || "sumo",
    scenarioId: localStorage.getItem("clawmodeler.bridgeExecution.scenarioId") || "baseline",
    dryRun: localStorage.getItem("clawmodeler.bridgeExecution.dryRun") !== "false",
    busy: false,
    status: "",
    lastResult: null,
  },
  whatIf: {
    baseRunId: localStorage.getItem("clawmodeler.whatIf.baseRunId") || "",
    newRunId: localStorage.getItem("clawmodeler.whatIf.newRunId") || "",
    weightsEnabled: localStorage.getItem("clawmodeler.whatIf.weightsEnabled") === "true",
    weights: { ...DEFAULT_WHAT_IF_WEIGHTS },
    referenceVmtPerCapita: "",
    thresholdPct: "",
    includeProjects: "",
    excludeProjects: "",
    sensitivityFloor: "",
    busy: false,
    status: "",
    lastResult: null,
  },
  portfolio: {
    result: null,
    selectedRunIds: [],
    sortKey: (localStorage.getItem("clawmodeler.portfolio.sortKey") as PortfolioSortKey) || "createdAt",
    sortDirection:
      (localStorage.getItem("clawmodeler.portfolio.sortDirection") as PortfolioSortDirection) ||
      "desc",
    busy: false,
    status: "",
    lastDiffPath: null,
  },
  projectState: initialProjectState,
};

function markOnboarded() {
  state.onboarded = true;
  localStorage.setItem("clawmodeler.onboarded", "true");
}

function requireAppRoot(): HTMLDivElement {
  const element = document.querySelector<HTMLDivElement>("#app");
  if (!element) {
    throw new Error("Missing #app root");
  }
  return element;
}

const appRoot = requireAppRoot();

function escapeHtml(value: unknown): string {
  const text =
    value === null || value === undefined
      ? ""
      : typeof value === "string"
        ? value
        : JSON.stringify(value);
  return text
    .replace(/&/gu, "&amp;")
    .replace(/</gu, "&lt;")
    .replace(/>/gu, "&gt;")
    .replace(/"/gu, "&quot;");
}

function formatOptionalNumber(value: number | null | undefined, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "n/a";
}

function readinessLabel(value: boolean | null | undefined): string {
  if (value === true) return "ready";
  if (value === false) return "blocked";
  return "unknown";
}

function readinessTone(value: boolean | null | undefined): "ok" | "bad" | "unknown" {
  if (value === true) return "ok";
  if (value === false) return "bad";
  return "unknown";
}

function selected(value: string, current: string): string {
  return value === current ? "selected" : "";
}

function stringField(payload: Record<string, unknown>, key: string, fallback = ""): string {
  const value = payload[key];
  return typeof value === "string" ? value : fallback;
}

function recordField(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseBridgeToolFeedback(value: unknown): BridgeToolFeedback[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const tool = recordField(item);
      if (!tool) return null;
      const id = stringOrNull(tool.id) ?? "tool";
      const command = stringOrNull(tool.command) ?? id;
      return {
        id,
        command,
        available: tool.available === true,
        path: stringOrNull(tool.path),
        note: stringOrNull(tool.note),
      };
    })
    .filter((item): item is BridgeToolFeedback => item !== null);
}

function parseBridgeOperatorFeedback(
  payload: Record<string, unknown> | null,
): BridgeOperatorFeedback | null {
  if (!payload) return null;
  const feedback = recordField(payload.operator_feedback);
  const source = feedback ?? payload;
  const summary = stringOrNull(source.operator_summary);
  const status = stringOrNull(source.operator_status) ?? stringOrNull(payload.status);
  if (!summary && !status && !source.command_display) return null;
  const outputSummary = recordField(source.output_summary);
  return {
    operatorSummary: summary ?? "Bridge execution status was recorded.",
    operatorStatus: status ?? "unknown",
    evidenceLevel: stringOrNull(source.evidence_level) ?? "unknown",
    forecastReadinessStatus: stringOrNull(source.forecast_readiness_status),
    commandDisplay: stringOrNull(source.command_display),
    commandCwd: stringOrNull(source.command_cwd),
    requiredTools: parseBridgeToolFeedback(source.required_tools),
    expectedOutputs: stringList(source.expected_outputs),
    existingOutputs: stringList(source.existing_outputs),
    missingOutputs: stringList(source.missing_outputs),
    outputSummary: {
      expectedCount: numberOrNull(outputSummary?.expected_count),
      existingCount: numberOrNull(outputSummary?.existing_count),
      missingCount: numberOrNull(outputSummary?.missing_count),
    },
    nextSteps: stringList(source.next_steps),
  };
}

function saveForm() {
  localStorage.setItem("clawmodeler.workspace", state.workspace);
  localStorage.setItem("clawmodeler.runId", state.runId);
  localStorage.setItem("clawmodeler.runLabel", state.runLabel);
  localStorage.setItem("clawmodeler.inputPaths", state.inputPaths);
  localStorage.setItem("clawmodeler.questionPath", state.questionPath);
  localStorage.setItem("clawmodeler.scenarios", state.scenarios);
  localStorage.setItem("clawmodeler.skipBridges", String(state.skipBridges));
  localStorage.setItem("clawmodeler.routingSource", state.routingSource);
  localStorage.setItem("clawmodeler.routingGraphId", state.routingGraphId);
  localStorage.setItem("clawmodeler.routingImpedance", state.routingImpedance);
}

function saveProjectState(records = state.projectState) {
  state.projectState = records;
  localStorage.setItem(PROJECT_STATE_KEY, serializeProjectState(state.projectState));
}

function currentWorkspaceRecord(): ProjectWorkspaceRecord | null {
  return findProjectWorkspace(state.projectState, state.workspace);
}

function activeRunLabel(workspace = state.workspace, runId = state.runId): string {
  return projectRunLabel(state.projectState, workspace, runId) || runId.trim();
}

function projectStatusFromArtifacts(artifacts: WorkspaceArtifacts | null): string {
  if (!artifacts?.manifest) {
    return "Selected";
  }
  const runSummary = summarizeRunArtifacts(artifacts);
  if (runSummary?.qaExportReady === false) {
    return "QA blocked";
  }
  if ((runSummary?.bridgeExecutionReports.length ?? 0) > 0) {
    return "Bridge review ready";
  }
  if ((runSummary?.plannerPackArtifacts.length ?? 0) > 0) {
    return "Planner Pack ready";
  }
  if (runSummary?.qaExportReady === true) {
    return "QA ready";
  }
  return "Run loaded";
}

function rememberCurrentProject(artifacts: WorkspaceArtifacts | null, status?: string) {
  const workspace = state.workspace.trim();
  const runId = state.runId.trim();
  if (!workspace || !runId) {
    return;
  }
  const runSummary = summarizeRunArtifacts(artifacts);
  const label = state.runLabel.trim() || activeRunLabel(workspace, runId) || runId;
  state.runLabel = label;
  const update: ProjectRunStateInput = {
    workspacePath: workspace,
    runId,
    label,
    status: status ?? projectStatusFromArtifacts(artifacts),
    updatedAt: new Date().toISOString(),
  };
  if (runSummary) {
    update.manifestPath = runSummary.manifestPath;
    update.reportPath = runSummary.reportPath;
    update.qaExportReady = runSummary.qaExportReady;
    update.plannerPackArtifacts = runSummary.plannerPackArtifacts;
    update.bridgeExecutionReportCount = runSummary.bridgeExecutionReports.length;
  }
  saveProjectState(upsertProjectRunState(state.projectState, update));
  saveForm();
}

function rememberCurrentSelection() {
  const workspace = state.workspace.trim();
  const runId = state.runId.trim();
  if (!workspace || !runId) {
    return;
  }
  saveProjectState(
    upsertProjectRunState(state.projectState, {
      workspacePath: workspace,
      runId,
      label: state.runLabel.trim() || runId,
      updatedAt: new Date().toISOString(),
    }),
  );
}

function applyWorkspaceRun(workspace: string, runId: string) {
  state.workspace = workspace;
  state.runId = runId;
  state.runLabel = activeRunLabel(workspace, runId) || runId;
  saveForm();
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;
}

async function tauriApi<T = unknown>(path: string, body?: unknown): Promise<ApiResult<T>> {
  if (path === "/api/clawmodeler/doctor") {
    return await invoke<ApiResult<T>>("clawmodeler_doctor");
  }
  if (path === "/api/clawmodeler/tools") {
    return await invoke<ApiResult<T>>("clawmodeler_tools");
  }
  if (path.startsWith("/api/clawmodeler/workspace")) {
    const url = new URL(path, "http://127.0.0.1");
    return await invoke<ApiResult<T>>("clawmodeler_workspace", {
      workspace: url.searchParams.get("workspace") ?? "",
      runId: url.searchParams.get("runId") ?? "demo",
    });
  }
  const payload = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  if (path === "/api/clawmodeler/init") {
    return await invoke<ApiResult<T>>("clawmodeler_run", {
      args: ["init", "--workspace", stringField(payload, "workspace")],
    });
  }
  if (path === "/api/clawmodeler/demo-full") {
    return await invoke<ApiResult<T>>("clawmodeler_run", {
      args: [
        "workflow",
        "demo-full",
        "--workspace",
        stringField(payload, "workspace"),
        "--run-id",
        stringField(payload, "runId", "demo"),
      ],
    });
  }
  if (path === "/api/clawmodeler/diagnose") {
    const args = ["workflow", "diagnose", "--workspace", stringField(payload, "workspace")];
    const runId = stringField(payload, "runId").trim();
    if (runId) {
      args.push("--run-id", runId);
    }
    return await invoke<ApiResult<T>>("clawmodeler_run", { args });
  }
  if (path === "/api/clawmodeler/report-only") {
    return await invoke<ApiResult<T>>("clawmodeler_run", {
      args: [
        "workflow",
        "report-only",
        "--workspace",
        stringField(payload, "workspace"),
        "--run-id",
        stringField(payload, "runId", "demo"),
      ],
    });
  }
  if (path === "/api/clawmodeler/run") {
    return await invoke<ApiResult<T>>("clawmodeler_run", { args: payload.args });
  }
  if (path === "/api/clawmodeler/artifact") {
    return await invoke<ApiResult<T>>("clawmodeler_read_artifact", {
      path: stringField(payload, "path"),
    });
  }
  if (path === "/api/clawmodeler/chat") {
    return await invoke<ApiResult<T>>("clawmodeler_chat", {
      workspace: stringField(payload, "workspace"),
      runId: stringField(payload, "runId"),
      message: stringField(payload, "message"),
      noHistory: payload.noHistory === true,
    });
  }
  if (path === "/api/clawmodeler/what-if") {
    return await invoke<ApiResult<T>>("clawmodeler_what_if", payload);
  }
  if (path === "/api/clawmodeler/portfolio") {
    return await invoke<ApiResult<T>>("clawmodeler_portfolio", {
      workspace: stringField(payload, "workspace"),
    });
  }
  if (path === "/api/clawmodeler/diff") {
    return await invoke<ApiResult<T>>("clawmodeler_run", {
      args: buildDiffArgs({
        workspace: stringField(payload, "workspace"),
        runA: stringField(payload, "runA"),
        runB: stringField(payload, "runB"),
      }),
    });
  }
  throw new Error(`Unsupported ClawModeler API path: ${path}`);
}

async function api<T = unknown>(path: string, body?: unknown): Promise<ApiResult<T>> {
  if (isTauriRuntime()) {
    const payload = await tauriApi<T>(path, body);
    if (!payload.ok) {
      throw apiError(payload.stderr || payload.error || "ClawModeler command failed", payload);
    }
    return payload;
  }

  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = (await response.json()) as ApiResult<T>;
  if (!response.ok || !payload.ok) {
    throw apiError(payload.stderr || payload.error || `HTTP ${response.status}`, payload);
  }
  return payload;
}

type ApiError<T> = Error & { payload?: ApiResult<T> };

function apiError<T>(message: string, payload: ApiResult<T>): ApiError<T> {
  const error = new Error(message) as ApiError<T>;
  error.payload = payload;
  return error;
}

async function runAction<T>(label: string, task: () => Promise<ApiResult<T>>) {
  state.busy = true;
  state.status = label;
  state.commandLog = [`${new Date().toLocaleTimeString()} ${label}`, ...state.commandLog].slice(
    0,
    12,
  );
  render();
  try {
    const result = await task();
    state.status = "Done";
    if (result.stdout) {
      state.commandLog = [result.stdout.trim(), ...state.commandLog].slice(0, 12);
    }
    await refreshArtifacts(false);
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.status = friendlyError(raw);
  } finally {
    state.busy = false;
    render();
  }
}

async function refreshDoctor() {
  await runAction("Checking local modeling stack", async () => {
    try {
      const result = await api<DoctorResult>("/api/clawmodeler/doctor");
      state.doctor = result.json ?? null;
      return result;
    } catch (error) {
      const payload = (error as ApiError<DoctorResult>).payload;
      if (payload?.json) {
        state.doctor = payload.json;
      }
      throw error;
    }
  });
}

async function refreshArtifacts(showBusy = true) {
  saveForm();
  const path = `/api/clawmodeler/workspace?workspace=${encodeURIComponent(
    state.workspace,
  )}&runId=${encodeURIComponent(state.runId)}`;
  if (showBusy) {
    state.busy = true;
    state.status = "Reading workspace artifacts";
    render();
  }
  try {
    const result = await api<WorkspaceArtifacts>(path);
    state.artifacts = result.json ?? null;
    rememberCurrentProject(state.artifacts);
    if (
      state.artifactPreview.selectedPath &&
      !state.artifacts?.files.includes(state.artifactPreview.selectedPath)
    ) {
      state.artifactPreview = {
        selectedPath: "",
        preview: null,
        busy: false,
        status: "Pick an artifact to preview.",
      };
    }
    if (state.artifacts?.manifest && !state.whatIf.baseRunId.trim()) {
      state.whatIf.baseRunId = state.artifacts.runId;
      saveWhatIfForm();
    }
    state.status = state.artifacts?.workspaceIndex
      ? "Workspace loaded from index"
      : "Workspace loaded with direct artifact fallback";
  } catch (error) {
    rememberCurrentProject(null, "Not loaded");
    if (showBusy) {
      const raw = error instanceof Error ? error.message : String(error);
      state.status = friendlyError(raw);
    }
  } finally {
    if (showBusy) {
      state.busy = false;
      render();
    }
  }
}

async function previewArtifact(path: string) {
  if (!isPreviewableArtifact(path)) {
    state.artifactPreview.status = "This artifact type is not previewed as text.";
    render();
    return;
  }
  state.artifactPreview.selectedPath = path;
  state.artifactPreview.busy = true;
  state.artifactPreview.status = `Reading ${artifactBasename(path)}…`;
  render();
  try {
    const result = await api<ArtifactPreview>("/api/clawmodeler/artifact", { path });
    state.artifactPreview.preview = result.json ?? null;
    state.artifactPreview.status = result.json?.truncated
      ? `Preview truncated at 128 KB from ${result.json.sizeBytes} bytes.`
      : `Previewing ${artifactBasename(path)}.`;
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.artifactPreview.status = friendlyError(raw);
  } finally {
    state.artifactPreview.busy = false;
    render();
  }
}

async function sendChat() {
  const message = state.chatDraft.trim();
  if (!message) {
    state.chatStatus = "Type a question first.";
    render();
    return;
  }
  if (!state.workspace.trim() || !state.runId.trim()) {
    state.chatStatus = "Pick a workspace and run id before chatting.";
    render();
    return;
  }
  state.chatBusy = true;
  state.chatStatus = "Asking the run…";
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/chat", {
      workspace: state.workspace,
      runId: state.runId,
      message,
      noHistory: state.chatNoHistory,
    });
    const turn = parseChatTurn(result.json ?? null);
    if (turn) {
      state.chatTurns = [...state.chatTurns, turn];
      state.chatDraft = "";
      state.chatStatus = turn.isFullyGrounded
        ? `Grounded reply from ${turn.provider}/${turn.model}.`
        : `Reply had ${turn.ungroundedSentenceCount} ungrounded sentence(s) dropped.`;
    } else {
      state.chatStatus = "Chat call returned no turn payload.";
    }
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.chatStatus = friendlyError(raw);
  } finally {
    state.chatBusy = false;
    render();
  }
}

function saveWhatIfForm() {
  localStorage.setItem("clawmodeler.whatIf.baseRunId", state.whatIf.baseRunId);
  localStorage.setItem("clawmodeler.whatIf.newRunId", state.whatIf.newRunId);
  localStorage.setItem(
    "clawmodeler.whatIf.weightsEnabled",
    String(state.whatIf.weightsEnabled),
  );
}

function savePlannerPackForm() {
  localStorage.setItem("clawmodeler.plannerPack.kind", state.plannerPack.kind);
  localStorage.setItem("clawmodeler.plannerPack.cycleYear", state.plannerPack.cycleYear);
  localStorage.setItem("clawmodeler.plannerPack.analysisYear", state.plannerPack.analysisYear);
}

function saveBridgeExecutionForm() {
  localStorage.setItem("clawmodeler.bridgeExecution.bridge", state.bridgeExecution.bridge);
  localStorage.setItem(
    "clawmodeler.bridgeExecution.scenarioId",
    state.bridgeExecution.scenarioId,
  );
  localStorage.setItem(
    "clawmodeler.bridgeExecution.dryRun",
    String(state.bridgeExecution.dryRun),
  );
}

async function submitPlannerPack() {
  const validation = validatePlannerPackForm({
    workspace: state.workspace,
    runId: state.runId,
    kind: state.plannerPack.kind,
    cycleYear: state.plannerPack.cycleYear,
    analysisYear: state.plannerPack.analysisYear,
  });
  if (!validation.ok) {
    state.plannerPack.status = validation.error;
    render();
    return;
  }

  state.plannerPack.busy = true;
  state.plannerPack.status = `Generating ${validation.payload.kind}…`;
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/run", {
      args: buildPlannerPackArgs(validation.payload),
    });
    state.plannerPack.lastResult = result.json ?? null;
    const reportPath =
      result.json && typeof result.json === "object"
        ? (result.json as Record<string, unknown>).report_path
        : null;
    state.plannerPack.status =
      typeof reportPath === "string"
        ? `Wrote ${validation.payload.kind} to ${reportPath}.`
        : `Generated ${validation.payload.kind}.`;
    await refreshArtifacts(false);
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.plannerPack.status = friendlyError(raw);
  } finally {
    state.plannerPack.busy = false;
    render();
  }
}

async function executeBridge() {
  const workspace = state.workspace.trim();
  const runId = state.runId.trim();
  const bridge = state.bridgeExecution.bridge.trim();
  if (!workspace || !runId || !bridge) {
    state.bridgeExecution.status = "Workspace, run ID, and bridge are required.";
    render();
    return;
  }

  state.bridgeExecution.busy = true;
  state.bridgeExecution.status = state.bridgeExecution.dryRun
    ? `Checking ${bridge} execution readiness…`
    : `Executing ${bridge} bridge…`;
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/run", {
      args: buildBridgeExecuteArgs({
        workspace,
        runId,
        bridge,
        scenarioId: state.bridgeExecution.scenarioId.trim() || "baseline",
        dryRun: state.bridgeExecution.dryRun,
      }),
    });
    state.bridgeExecution.lastResult = result.json ?? null;
    const payload = (result.json ?? {}) as Record<string, unknown>;
    state.bridgeExecution.status =
      typeof payload.bridge_execution_report === "string"
        ? `${payload.status ?? "done"}: ${payload.bridge_execution_report}`
        : `${payload.status ?? "done"}`;
    await refreshArtifacts(false);
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.bridgeExecution.status = friendlyError(raw);
  } finally {
    state.bridgeExecution.busy = false;
    render();
  }
}

async function submitWhatIf() {
  const validation = validateWhatIfForm({
    workspace: state.workspace,
    baseRunId: state.whatIf.baseRunId,
    newRunId: state.whatIf.newRunId,
    weightsEnabled: state.whatIf.weightsEnabled,
    weights: state.whatIf.weights,
    referenceVmtPerCapita: state.whatIf.referenceVmtPerCapita,
    thresholdPct: state.whatIf.thresholdPct,
    includeProjects: state.whatIf.includeProjects,
    excludeProjects: state.whatIf.excludeProjects,
    sensitivityFloor: state.whatIf.sensitivityFloor,
  });
  if (!validation.ok) {
    state.whatIf.status = validation.error;
    render();
    return;
  }
  const payload = validation.payload;
  state.whatIf.busy = true;
  state.whatIf.status = `Running what-if into ${payload.newRunId}…`;
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/what-if", {
      workspace: payload.workspace,
      baseRunId: payload.baseRunId,
      newRunId: payload.newRunId,
      weightSafety: payload.weights?.safety ?? null,
      weightEquity: payload.weights?.equity ?? null,
      weightClimate: payload.weights?.climate ?? null,
      weightFeasibility: payload.weights?.feasibility ?? null,
      referenceVmtPerCapita: payload.referenceVmtPerCapita,
      thresholdPct: payload.thresholdPct,
      includeProjects: payload.includeProjects,
      excludeProjects: payload.excludeProjects,
      sensitivityFloor: payload.sensitivityFloor,
    });
    state.whatIf.lastResult = result.json ?? null;
    state.whatIf.status = `Created run ${payload.newRunId}.`;
    state.runId = payload.newRunId;
    state.runLabel =
      projectRunLabel(state.projectState, state.workspace, payload.newRunId) || payload.newRunId;
    saveForm();
    await refreshArtifacts(false);
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.whatIf.status = friendlyError(raw);
  } finally {
    state.whatIf.busy = false;
    render();
  }
}

async function loadPortfolio() {
  const workspace = state.workspace.trim();
  if (!workspace) {
    state.portfolio.status = "Pick a workspace folder first.";
    render();
    return;
  }
  state.portfolio.busy = true;
  state.portfolio.status = "Reading workspace portfolio…";
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/portfolio", {
      workspace,
    });
    const parsed = parsePortfolioPayload(result.json ?? null);
    state.portfolio.result = parsed;
    state.portfolio.status = parsed
      ? `Loaded ${parsed.runCount} run(s).`
      : "Portfolio call returned no payload.";
    // Drop selection entries that no longer exist in the result.
    if (parsed) {
      const runIds = new Set(parsed.runs.map((run) => run.runId));
      state.portfolio.selectedRunIds = state.portfolio.selectedRunIds.filter((id) =>
        runIds.has(id),
      );
    }
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.portfolio.status = friendlyError(raw);
  } finally {
    state.portfolio.busy = false;
    render();
  }
}

async function diffSelectedRuns() {
  const validation = validateDiffSelection(state.portfolio.selectedRunIds);
  if (!validation.ok) {
    state.portfolio.status = validation.error;
    render();
    return;
  }
  const workspace = state.workspace.trim();
  if (!workspace) {
    state.portfolio.status = "Pick a workspace folder first.";
    render();
    return;
  }
  state.portfolio.busy = true;
  state.portfolio.status = `Diffing ${validation.runA} → ${validation.runB}…`;
  render();
  try {
    const result = await api<Record<string, unknown>>("/api/clawmodeler/diff", {
      workspace,
      runA: validation.runA,
      runB: validation.runB,
    });
    const diffPayload =
      result.json && typeof result.json === "object"
        ? (result.json as Record<string, unknown>)
        : {};
    const diffPath = diffPayload.report_path ?? diffPayload.diff_report_path ?? null;
    state.portfolio.lastDiffPath = typeof diffPath === "string" ? diffPath : null;
    state.portfolio.status = state.portfolio.lastDiffPath
      ? `Diff report written to ${state.portfolio.lastDiffPath}.`
      : `Diff completed for ${validation.runA} → ${validation.runB}.`;
  } catch (error) {
    const raw = error instanceof Error ? error.message : String(error);
    state.portfolio.status = friendlyError(raw);
  } finally {
    state.portfolio.busy = false;
    render();
  }
}

function setPortfolioSort(key: PortfolioSortKey) {
  if (state.portfolio.sortKey === key) {
    state.portfolio.sortDirection = state.portfolio.sortDirection === "asc" ? "desc" : "asc";
  } else {
    state.portfolio.sortKey = key;
    state.portfolio.sortDirection = "asc";
  }
  localStorage.setItem("clawmodeler.portfolio.sortKey", state.portfolio.sortKey);
  localStorage.setItem("clawmodeler.portfolio.sortDirection", state.portfolio.sortDirection);
  render();
}

function togglePortfolioSelection(runId: string) {
  state.portfolio.selectedRunIds = toggleRunSelection(state.portfolio.selectedRunIds, runId);
  render();
}

function openRunFromPortfolio(runId: string) {
  applyWorkspaceRun(state.workspace, runId);
  void refreshArtifacts();
}

async function pickWorkspaceFolder() {
  try {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "Pick workspace folder",
    });
    if (typeof selected === "string" && selected) {
      const remembered = findProjectWorkspace(state.projectState, selected);
      applyWorkspaceRun(selected, remembered?.activeRunId || state.runId);
      saveForm();
      render();
    }
  } catch (error) {
    state.status = friendlyError(error instanceof Error ? error.message : String(error));
    render();
  }
}

async function pickInputFiles() {
  try {
    const selected = await open({
      directory: false,
      multiple: true,
      title: "Pick input files",
      filters: [
        { name: "Planning data", extensions: ["geojson", "json", "csv", "parquet", "tsv"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (Array.isArray(selected) && selected.length > 0) {
      const existing = state.inputPaths.trim();
      const existingSet = new Set(
        existing
          ? existing
              .split(/\r?\n/)
              .map((line) => line.trim())
              .filter(Boolean)
          : [],
      );
      const toAdd = selected.filter((path) => !existingSet.has(path.trim()));
      if (toAdd.length > 0) {
        const appended = toAdd.join("\n");
        state.inputPaths = existing ? `${existing}\n${appended}` : appended;
        saveForm();
        render();
      }
    }
  } catch (error) {
    state.status = friendlyError(error instanceof Error ? error.message : String(error));
    render();
  }
}

async function pickQuestionFile() {
  try {
    const selected = await open({
      directory: false,
      multiple: false,
      title: "Pick question.json",
      filters: [
        { name: "JSON", extensions: ["json"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (typeof selected === "string" && selected) {
      state.questionPath = selected;
      saveForm();
      render();
    }
  } catch (error) {
    state.status = friendlyError(error instanceof Error ? error.message : String(error));
    render();
  }
}

async function createStarterQuestion() {
  let selected: string | null;
  try {
    selected = await save({
      title: "Save starter question.json",
      defaultPath: deriveQuestionSavePath(state.workspace, state.questionPath),
      filters: [
        { name: "JSON", extensions: ["json"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
  } catch (error) {
    state.status = friendlyError(error instanceof Error ? error.message : String(error));
    render();
    return;
  }
  if (typeof selected !== "string" || !selected) {
    return;
  }
  await runAction("Creating starter question.json", async () => {
    const result = await api<{ question_path: string; created: boolean }>("/api/clawmodeler/run", {
      args: ["scaffold", "question", "--path", selected, "--force"],
    });
    const created = result.json?.question_path ?? selected;
    state.questionPath = created;
    saveForm();
    return result;
  });
}

function bindControls() {
  appRoot.querySelector<HTMLInputElement>("#workspace")?.addEventListener("input", (event) => {
    state.workspace = (event.target as HTMLInputElement).value;
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#run-id")?.addEventListener("input", (event) => {
    const previousRunId = state.runId;
    state.runId = (event.target as HTMLInputElement).value;
    if (!state.runLabel.trim() || state.runLabel === previousRunId) {
      state.runLabel = activeRunLabel(state.workspace, state.runId) || state.runId;
    }
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#run-id")?.addEventListener("change", () => {
    state.runLabel = activeRunLabel(state.workspace, state.runId) || state.runId;
    saveForm();
    render();
  });
  appRoot.querySelector<HTMLInputElement>("#run-label")?.addEventListener("input", (event) => {
    state.runLabel = (event.target as HTMLInputElement).value;
    saveForm();
    rememberCurrentSelection();
  });
  appRoot.querySelector<HTMLTextAreaElement>("#input-paths")?.addEventListener("input", (event) => {
    state.inputPaths = (event.target as HTMLTextAreaElement).value;
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#question-path")?.addEventListener("input", (event) => {
    state.questionPath = (event.target as HTMLInputElement).value;
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#scenarios")?.addEventListener("input", (event) => {
    state.scenarios = (event.target as HTMLInputElement).value;
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#skip-bridges")?.addEventListener("change", (event) => {
    state.skipBridges = (event.target as HTMLInputElement).checked;
    saveForm();
  });
  appRoot.querySelector<HTMLSelectElement>("#routing-source")?.addEventListener("change", (event) => {
    state.routingSource = (event.target as HTMLSelectElement).value;
    saveForm();
  });
  appRoot.querySelector<HTMLInputElement>("#routing-graph-id")?.addEventListener("input", (event) => {
    state.routingGraphId = (event.target as HTMLInputElement).value;
    saveForm();
  });
  appRoot
    .querySelector<HTMLSelectElement>("#routing-impedance")
    ?.addEventListener("change", (event) => {
      state.routingImpedance = (event.target as HTMLSelectElement).value;
      saveForm();
    });

  appRoot
    .querySelector<HTMLButtonElement>("[data-action='doctor']")
    ?.addEventListener("click", () => {
      void refreshDoctor();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='init']")
    ?.addEventListener("click", () => {
      void runAction("Creating workspace", () =>
        api("/api/clawmodeler/init", { workspace: state.workspace }),
      );
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='demo']")
    ?.addEventListener("click", () => {
      markOnboarded();
      void runAction("Running demo workflow", () =>
        api("/api/clawmodeler/demo-full", { workspace: state.workspace, runId: state.runId }),
      );
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='dismiss-welcome']")
    ?.addEventListener("click", () => {
      markOnboarded();
      render();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='pick-workspace']")
    ?.addEventListener("click", () => {
      void pickWorkspaceFolder();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='pick-inputs']")
    ?.addEventListener("click", () => {
      void pickInputFiles();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='pick-question']")
    ?.addEventListener("click", () => {
      void pickQuestionFile();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='create-question']")
    ?.addEventListener("click", () => {
      void createStarterQuestion();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='full']")
    ?.addEventListener("click", () => {
      const inputs = normalizePathList(state.inputPaths);
      const question = state.questionPath.trim();
      if (inputs.length === 0 || !question) {
        state.status =
          "Before running the full workflow, fill in at least one input path and a question.json path. New? Try 'Run the demo' first — no files required.";
        render();
        return;
      }
      void runAction("Running full workflow", () =>
        api("/api/clawmodeler/run", {
          args: buildFullWorkflowArgs({
            workspace: state.workspace,
            inputs,
            question,
            runId: state.runId,
            scenarios: normalizeScenarios(state.scenarios),
            skipBridges: state.skipBridges,
            routingSource: state.routingSource,
            routingGraphId: state.routingGraphId,
            routingImpedance: state.routingImpedance,
          }),
        }),
      );
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='diagnose']")
    ?.addEventListener("click", () => {
      void runAction("Diagnosing workspace", () =>
        api("/api/clawmodeler/diagnose", { workspace: state.workspace, runId: state.runId }),
      );
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='report']")
    ?.addEventListener("click", () => {
      void runAction("Regenerating report", () =>
        api("/api/clawmodeler/report-only", { workspace: state.workspace, runId: state.runId }),
      );
    });

  appRoot
    .querySelector<HTMLSelectElement>("#bridge-execution-bridge")
    ?.addEventListener("change", (event) => {
      state.bridgeExecution.bridge = (event.target as HTMLSelectElement).value;
      saveBridgeExecutionForm();
    });
  appRoot
    .querySelector<HTMLInputElement>("#bridge-execution-scenario")
    ?.addEventListener("input", (event) => {
      state.bridgeExecution.scenarioId = (event.target as HTMLInputElement).value;
      saveBridgeExecutionForm();
    });
  appRoot
    .querySelector<HTMLInputElement>("#bridge-execution-dry-run")
    ?.addEventListener("change", (event) => {
      state.bridgeExecution.dryRun = (event.target as HTMLInputElement).checked;
      saveBridgeExecutionForm();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='bridge-execute']")
    ?.addEventListener("click", () => {
      void executeBridge();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='refresh']")
    ?.addEventListener("click", () => {
      void refreshArtifacts();
    });

  appRoot.querySelector<HTMLTextAreaElement>("#chat-draft")?.addEventListener("input", (event) => {
    state.chatDraft = (event.target as HTMLTextAreaElement).value;
  });
  appRoot
    .querySelector<HTMLTextAreaElement>("#chat-draft")
    ?.addEventListener("keydown", (event) => {
      const ke = event as KeyboardEvent;
      if ((ke.ctrlKey || ke.metaKey) && ke.key === "Enter") {
        ke.preventDefault();
        void sendChat();
      }
    });
  appRoot.querySelector<HTMLInputElement>("#chat-no-history")?.addEventListener("change", (event) => {
    state.chatNoHistory = (event.target as HTMLInputElement).checked;
  });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='chat-send']")
    ?.addEventListener("click", () => {
      void sendChat();
    });

  appRoot
    .querySelector<HTMLSelectElement>("#planner-pack-kind")
    ?.addEventListener("change", (event) => {
      state.plannerPack.kind = (event.target as HTMLSelectElement).value as PlannerPackKind;
      savePlannerPackForm();
      render();
    });
  appRoot
    .querySelector<HTMLInputElement>("#planner-pack-cycle-year")
    ?.addEventListener("input", (event) => {
      state.plannerPack.cycleYear = (event.target as HTMLInputElement).value;
      savePlannerPackForm();
    });
  appRoot
    .querySelector<HTMLInputElement>("#planner-pack-analysis-year")
    ?.addEventListener("input", (event) => {
      state.plannerPack.analysisYear = (event.target as HTMLInputElement).value;
      savePlannerPackForm();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='planner-pack-submit']")
    ?.addEventListener("click", () => {
      void submitPlannerPack();
    });

  appRoot.querySelector<HTMLInputElement>("#what-if-base")?.addEventListener("input", (event) => {
    state.whatIf.baseRunId = (event.target as HTMLInputElement).value;
    saveWhatIfForm();
  });
  appRoot.querySelector<HTMLInputElement>("#what-if-new")?.addEventListener("input", (event) => {
    state.whatIf.newRunId = (event.target as HTMLInputElement).value;
    saveWhatIfForm();
  });
  appRoot
    .querySelector<HTMLInputElement>("#what-if-weights-enabled")
    ?.addEventListener("change", (event) => {
      state.whatIf.weightsEnabled = (event.target as HTMLInputElement).checked;
      saveWhatIfForm();
      render();
    });
  appRoot.querySelectorAll<HTMLInputElement>("input[data-weight-key]").forEach((el) => {
    el.addEventListener("input", (event) => {
      const target = event.target as HTMLInputElement;
      const key = target.dataset.weightKey as keyof WhatIfWeights | undefined;
      if (!key) return;
      const value = Number(target.value);
      state.whatIf.weights = rebalanceWhatIfWeights(state.whatIf.weights, key, value);
      render();
    });
  });
  appRoot
    .querySelector<HTMLInputElement>("#what-if-ref-vmt")
    ?.addEventListener("input", (event) => {
      state.whatIf.referenceVmtPerCapita = (event.target as HTMLInputElement).value;
    });
  appRoot
    .querySelector<HTMLInputElement>("#what-if-threshold")
    ?.addEventListener("input", (event) => {
      state.whatIf.thresholdPct = (event.target as HTMLInputElement).value;
    });
  appRoot
    .querySelector<HTMLTextAreaElement>("#what-if-include")
    ?.addEventListener("input", (event) => {
      state.whatIf.includeProjects = (event.target as HTMLTextAreaElement).value;
    });
  appRoot
    .querySelector<HTMLTextAreaElement>("#what-if-exclude")
    ?.addEventListener("input", (event) => {
      state.whatIf.excludeProjects = (event.target as HTMLTextAreaElement).value;
    });
  appRoot
    .querySelector<HTMLSelectElement>("#what-if-floor")
    ?.addEventListener("change", (event) => {
      state.whatIf.sensitivityFloor = (event.target as HTMLSelectElement).value;
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='what-if-submit']")
    ?.addEventListener("click", () => {
      void submitWhatIf();
    });

  appRoot
    .querySelector<HTMLButtonElement>("[data-action='portfolio-refresh']")
    ?.addEventListener("click", () => {
      void loadPortfolio();
    });
  appRoot
    .querySelector<HTMLButtonElement>("[data-action='portfolio-diff']")
    ?.addEventListener("click", () => {
      void diffSelectedRuns();
    });
  appRoot.querySelectorAll<HTMLButtonElement>("[data-sort-key]").forEach((el) => {
    el.addEventListener("click", () => {
      const key = el.dataset.sortKey as PortfolioSortKey | undefined;
      if (key) setPortfolioSort(key);
    });
  });
  appRoot.querySelectorAll<HTMLInputElement>("[data-portfolio-select]").forEach((el) => {
    el.addEventListener("change", () => {
      const runId = el.dataset.portfolioSelect;
      if (runId) togglePortfolioSelection(runId);
    });
  });
  appRoot.querySelectorAll<HTMLButtonElement>("[data-portfolio-open]").forEach((el) => {
    el.addEventListener("click", () => {
      const runId = el.dataset.portfolioOpen;
      if (runId) openRunFromPortfolio(runId);
    });
  });
  appRoot.querySelectorAll<HTMLButtonElement>("[data-project-open]").forEach((el) => {
    el.addEventListener("click", () => {
      const index = Number(el.dataset.projectOpen);
      const workspace = state.projectState[index];
      if (!workspace) return;
      applyWorkspaceRun(
        workspace.workspacePath,
        workspace.activeRunId || workspace.runs[0]?.runId || state.runId,
      );
      void refreshArtifacts();
    });
  });
  appRoot.querySelectorAll<HTMLButtonElement>("[data-run-open]").forEach((el) => {
    el.addEventListener("click", () => {
      const runId = el.dataset.runOpen;
      if (!runId) return;
      applyWorkspaceRun(state.workspace, runId);
      void refreshArtifacts();
    });
  });
  appRoot.querySelectorAll<HTMLButtonElement>("[data-artifact-preview]").forEach((el) => {
    el.addEventListener("click", () => {
      const path = el.dataset.artifactPreview;
      if (path) void previewArtifact(path);
    });
  });
}

function renderWelcome(): string {
  if (state.onboarded || state.artifacts?.manifest) {
    return "";
  }
  return `
    <section class="welcome-banner">
      <div class="welcome-copy">
        <p class="eyebrow">Start here</p>
        <h2>New to ClawModeler? Run the demo first.</h2>
        <p>One click builds a complete sample analysis — workspace, scenarios, QA gates, and a plain-English report. No files or setup required.</p>
      </div>
      <div class="welcome-cta">
        <button data-action="demo" class="primary-cta" ${state.busy ? "disabled" : ""}>Run the demo</button>
        <button data-action="dismiss-welcome" class="link-btn" ${state.busy ? "disabled" : ""}>Skip — I'll set up my own project</button>
      </div>
    </section>
  `;
}

function renderDoctor() {
  if (!state.doctor) {
    return `<p class="muted">Doctor checks which local tools are installed. You need Python 3 — everything else is optional for the demo.</p>`;
  }
  const checks = state.doctor.checks.slice(0, 18);
  return `
    <div class="tool-grid">
      ${checks
        .map(
          (check) => `
            <div class="tool-row">
              <span class="status-dot ${escapeHtml(check.status)}"></span>
              <span>${escapeHtml(check.name)}</span>
              <small>${escapeHtml(check.profile)} / ${escapeHtml(check.category)}</small>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderWorkflowGuideStep(step: WorkflowGuideStep, currentStepId: string | null): string {
  const isCurrent = step.id === currentStepId;
  return `
    <article class="workflow-step ${escapeHtml(step.state)} ${isCurrent ? "current" : ""}">
      <div class="workflow-step-head">
        <strong>${escapeHtml(step.label)}</strong>
        <span>${escapeHtml(step.state)}</span>
      </div>
      <p>${escapeHtml(step.status)}</p>
      ${step.blocker ? `<small>${escapeHtml(step.blocker)}</small>` : ""}
      <a href="${escapeHtml(step.anchor)}">${escapeHtml(step.actionLabel)}</a>
    </article>
  `;
}

function renderWorkflowGuide(): string {
  const guide = deriveWorkflowGuide({
    workspace: state.workspace,
    runId: state.runId,
    inputPaths: state.inputPaths,
    questionPath: state.questionPath,
    busy: state.busy,
    artifacts: state.artifacts,
    plannerPackBusy: state.plannerPack.busy,
    chatBusy: state.chatBusy,
    chatTurnCount: state.chatTurns.length,
    whatIfBusy: state.whatIf.busy,
    hasWhatIfResult: Boolean(state.whatIf.lastResult),
    portfolioBusy: state.portfolio.busy,
    portfolioResult: state.portfolio.result,
    selectedPortfolioRunIds: state.portfolio.selectedRunIds,
    hasDiffReport: Boolean(state.portfolio.lastDiffPath),
  });
  const nextAction =
    guide.nextActionLabel && guide.nextActionAnchor
      ? `<a class="workflow-next-action" href="${escapeHtml(guide.nextActionAnchor)}">${escapeHtml(
          guide.nextActionLabel,
        )}</a>`
      : "";
  return `
    <section class="workflow-guide" id="guide">
      <div class="workflow-guide-head">
        <div>
          <p class="eyebrow">Workflow Guide</p>
          <h2>Move this analysis from setup to review.</h2>
        </div>
        ${nextAction}
      </div>
      <div class="workflow-steps">
        ${guide.steps.map((step) => renderWorkflowGuideStep(step, guide.currentStepId)).join("")}
      </div>
    </section>
  `;
}

function renderProjectMemory(): string {
  const current = currentWorkspaceRecord();
  const activeRun = current?.runs.find((run) => run.runId === state.runId);
  const currentStatus =
    activeRun?.status ??
    (state.artifacts?.manifest ? projectStatusFromArtifacts(state.artifacts) : "New setup");
  const recentWorkspaces =
    state.projectState.length > 0
      ? `<ul class="project-memory-list">${state.projectState
          .slice(0, 5)
          .map(
            (workspace, index) => `
              <li>
                <div>
                  <strong>${escapeHtml(workspace.label)}</strong>
                  <span>${escapeHtml(workspace.workspacePath)}</span>
                  <small>${escapeHtml(workspace.runs.length)} run(s), active <code>${escapeHtml(
                    workspace.activeRunId || "none",
                  )}</code></small>
                </div>
                <button type="button" class="link-btn" data-project-open="${index}" ${
                  state.busy ? "disabled" : ""
                }>Open</button>
              </li>
            `,
          )
          .join("")}</ul>`
      : `<p class="muted">Recent workspaces appear here after you load or run one.</p>`;
  const runHistory =
    current && current.runs.length > 0
      ? `<ul class="project-memory-list">${current.runs
          .slice(0, 6)
          .map(
            (run) => `
              <li>
                <div>
                  <strong>${escapeHtml(run.label)}</strong>
                  <span><code>${escapeHtml(run.runId)}</code> ${escapeHtml(run.status)}</span>
                  <small>${escapeHtml(
                    run.lastOpenedAt ? run.lastOpenedAt.slice(0, 19).replace("T", " ") : "Not opened",
                  )}</small>
                </div>
                <button type="button" class="link-btn" data-run-open="${escapeHtml(
                  run.runId,
                )}" ${state.busy ? "disabled" : ""}>Open</button>
              </li>
            `,
          )
          .join("")}</ul>`
      : `<p class="muted">No saved run history for this workspace yet.</p>`;
  return `
    <div class="project-memory">
      <div class="project-memory-head">
        <div>
          <strong>${escapeHtml(workspaceDisplayName(state.workspace))}</strong>
          <span>${escapeHtml(currentStatus)}</span>
        </div>
        <small>${current ? `${current.runs.length} remembered run(s)` : "New workspace"}</small>
      </div>
      <details>
        <summary>Recent workspaces</summary>
        ${recentWorkspaces}
      </details>
      <details>
        <summary>Run history</summary>
        ${runHistory}
      </details>
    </div>
  `;
}

function renderChatTurn(turn: ChatTurn): string {
  const badge = chatTurnBadge(turn);
  const segments = segmentChatText(turn.text)
    .map((segment) =>
      segment.kind === "chip"
        ? `<span class="chat-chip" title="fact_id ${escapeHtml(segment.factId)}">[fact:${escapeHtml(segment.factId)}]</span>`
        : escapeHtml(segment.value),
    )
    .join("");
  const unknown =
    turn.unknownFactIds.length > 0
      ? `<p class="chat-warning">Unknown fact_ids in model output: ${escapeHtml(turn.unknownFactIds.join(", "))}</p>`
      : "";
  const dropped =
    turn.ungroundedSentenceCount > 0
      ? `<p class="chat-warning">Dropped ${turn.ungroundedSentenceCount} ungrounded sentence(s).</p>`
      : "";
  return `
    <article class="chat-turn">
      <div class="chat-user"><strong>You</strong><p>${escapeHtml(turn.userMessage)}</p></div>
      <div class="chat-reply">
        <div class="chat-reply-head">
          <strong>${escapeHtml(turn.provider)}/${escapeHtml(turn.model)}</strong>
          <span class="chat-badge ${escapeHtml(badge)}">${escapeHtml(badge)}</span>
        </div>
        <p>${segments || "<em>(empty)</em>"}</p>
        ${unknown}
        ${dropped}
      </div>
    </article>
  `;
}

function renderChat(): string {
  const hasRun = Boolean(state.artifacts?.manifest);
  const transcript =
    state.chatTurns.length > 0
      ? `<div class="chat-transcript">${state.chatTurns.map(renderChatTurn).join("")}</div>`
      : `<p class="muted">Ask a grounded question about this run. Every reply sentence will cite a real <code>[fact:&lt;id&gt;]</code> or the reply collapses to "I do not have evidence for that in this run's fact_blocks."</p>`;
  const disabled = state.chatBusy || !hasRun;
  return `
    <section class="panel chat-panel" id="chat">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">6</span> Chat</p>
          <h2>Chat With the Run</h2>
        </div>
        <span>${escapeHtml(state.chatStatus || (hasRun ? "Ready" : "Run a workflow first"))}</span>
      </div>
      ${transcript}
      <label class="chat-composer">
        <textarea
          id="chat-draft"
          rows="3"
          spellcheck="true"
          placeholder="Ask a grounded question about this run…"
          ${disabled ? "disabled" : ""}
        >${escapeHtml(state.chatDraft)}</textarea>
      </label>
      <div class="chat-controls">
        <label class="check-row">
          <input id="chat-no-history" type="checkbox" ${state.chatNoHistory ? "checked" : ""} ${disabled ? "disabled" : ""} />
          Ignore prior chat history
        </label>
        <button data-action="chat-send" ${disabled ? "disabled" : ""}>${state.chatBusy ? "Thinking…" : "Send"}</button>
      </div>
    </section>
  `;
}

function renderPlannerPack(): string {
  const planner = state.plannerPack;
  const hasRun = Boolean(state.artifacts?.manifest);
  const disabled = planner.busy || !hasRun;
  const spec = PLANNER_PACK_SPECS.find((item) => item.kind === planner.kind);
  const needsCycleYear = planner.kind === "hsip";
  const needsAnalysisYear = planner.kind === "cmaq";
  const lastResult = (() => {
    const r = planner.lastResult;
    if (!r) return "";
    const reportPath = typeof r.report_path === "string" ? r.report_path : "";
    const csvPath = typeof r.csv_path === "string" ? r.csv_path : "";
    return `
      <div class="planner-pack-result">
        <p><strong>Last packet:</strong> ${escapeHtml(spec?.label ?? planner.kind)}</p>
        ${reportPath ? `<p>Report: <code>${escapeHtml(reportPath)}</code></p>` : ""}
        ${csvPath ? `<p>Table: <code>${escapeHtml(csvPath)}</code></p>` : ""}
      </div>
    `;
  })();
  return `
    <section class="panel planner-pack-panel" id="planner-pack">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">5</span> Planner Pack</p>
          <h2>Generate Planning Artifacts</h2>
        </div>
        <span>${escapeHtml(planner.status || (hasRun ? "Ready" : "Run a workflow first"))}</span>
      </div>
      <p class="muted">Generate regulatory and grant-facing packets from the active run's manifest, tables, and fact blocks.</p>
      <div class="planner-pack-grid">
        <label>
          Artifact
          <select id="planner-pack-kind" ${planner.busy ? "disabled" : ""}>
            ${PLANNER_PACK_SPECS.map(
              (item) =>
                `<option value="${escapeHtml(item.kind)}" ${
                  item.kind === planner.kind ? "selected" : ""
                }>${escapeHtml(item.label)}</option>`,
            ).join("")}
          </select>
        </label>
        <label class="${needsCycleYear ? "" : "conditional-field"}">
          HSIP cycle year
          <input id="planner-pack-cycle-year" value="${escapeHtml(planner.cycleYear)}" spellcheck="false" ${disabled || !needsCycleYear ? "disabled" : ""} />
        </label>
        <label class="${needsAnalysisYear ? "" : "conditional-field"}">
          CMAQ analysis year
          <input id="planner-pack-analysis-year" value="${escapeHtml(planner.analysisYear)}" spellcheck="false" ${disabled || !needsAnalysisYear ? "disabled" : ""} />
        </label>
      </div>
      <div class="planner-pack-actions">
        <button data-action="planner-pack-submit" ${disabled ? "disabled" : ""}>
          ${planner.busy ? "Generating…" : "Generate artifact"}
        </button>
      </div>
      ${lastResult}
    </section>
  `;
}

function renderWhatIf(): string {
  const w = state.whatIf;
  const sum = whatIfWeightSum(w.weights);
  const sumLabel = sum.toFixed(3);
  const sumOk = Math.abs(sum - 1) < 1e-6;
  const disabled = w.busy;
  const summary = (() => {
    const r = w.lastResult;
    if (!r) return "";
    const deltas = Array.isArray(r.project_deltas) ? r.project_deltas : [];
    const dropped = Array.isArray(r.dropped_project_ids) ? r.dropped_project_ids : [];
    return `
      <div class="what-if-summary">
        <p><strong>Result:</strong> base <code>${escapeHtml(r.base_run_id)}</code> → new <code>${escapeHtml(r.new_run_id)}</code></p>
        <p>${deltas.length} project delta(s); ${dropped.length} dropped.</p>
      </div>
    `;
  })();
  return `
    <section class="panel what-if-panel" id="what-if">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">7</span> What-if</p>
          <h2>What-if Simulator</h2>
        </div>
        <span>${escapeHtml(w.status || "Derive a new run from a finished baseline")}</span>
      </div>
      <p class="muted">Pick a finished run as the baseline, apply overrides (scoring weights, CEQA threshold, project filters, sensitivity floor), and produce a new run tree that flows through diff, Planner Pack, chat, and export.</p>
      <div class="what-if-grid">
        <label>
          Base run ID
          <input id="what-if-base" value="${escapeHtml(w.baseRunId)}" spellcheck="false" ${disabled ? "disabled" : ""} />
        </label>
        <label>
          New run ID
          <input id="what-if-new" value="${escapeHtml(w.newRunId)}" spellcheck="false" placeholder="e.g., ${escapeHtml(w.baseRunId || "demo")}-safety-heavy" ${disabled ? "disabled" : ""} />
        </label>
      </div>
      <label class="check-row">
        <input id="what-if-weights-enabled" type="checkbox" ${w.weightsEnabled ? "checked" : ""} ${disabled ? "disabled" : ""} />
        Override scoring weights
      </label>
      <div class="what-if-weights ${w.weightsEnabled ? "" : "disabled"}">
        ${(["safety", "equity", "climate", "feasibility"] as const)
          .map(
            (key) => `
          <label class="weight-slider">
            <span>${escapeHtml(key)}: <strong>${w.weights[key].toFixed(3)}</strong></span>
            <input type="range" min="0" max="1" step="0.01" value="${w.weights[key]}" data-weight-key="${key}" ${!w.weightsEnabled || disabled ? "disabled" : ""} />
          </label>
        `,
          )
          .join("")}
        <small class="help">Sum: <strong class="${sumOk ? "ok" : "bad"}">${escapeHtml(sumLabel)}</strong> (must equal 1.000). Sliders rebalance the remaining three proportionally.</small>
      </div>
      <div class="what-if-grid">
        <label>
          Reference VMT/capita
          <input id="what-if-ref-vmt" value="${escapeHtml(w.referenceVmtPerCapita)}" placeholder="e.g., 20.5" spellcheck="false" ${disabled ? "disabled" : ""} />
        </label>
        <label>
          CEQA threshold fraction
          <input id="what-if-threshold" value="${escapeHtml(w.thresholdPct)}" placeholder="0.15 (OPR default)" spellcheck="false" ${disabled ? "disabled" : ""} />
        </label>
      </div>
      <label>
        Include project IDs (one per line or comma-separated; blank = all)
        <textarea id="what-if-include" rows="2" spellcheck="false" ${disabled ? "disabled" : ""}>${escapeHtml(w.includeProjects)}</textarea>
      </label>
      <label>
        Exclude project IDs (one per line or comma-separated)
        <textarea id="what-if-exclude" rows="2" spellcheck="false" ${disabled ? "disabled" : ""}>${escapeHtml(w.excludeProjects)}</textarea>
      </label>
      <label>
        Sensitivity floor
        <select id="what-if-floor" ${disabled ? "disabled" : ""}>
          <option value="" ${w.sensitivityFloor === "" ? "selected" : ""}>(no floor)</option>
          <option value="LOW" ${w.sensitivityFloor === "LOW" ? "selected" : ""}>LOW — only rock-solid projects</option>
          <option value="MEDIUM" ${w.sensitivityFloor === "MEDIUM" ? "selected" : ""}>MEDIUM — drop assumption-heavy</option>
          <option value="HIGH" ${w.sensitivityFloor === "HIGH" ? "selected" : ""}>HIGH — keep everything</option>
        </select>
      </label>
      <div class="what-if-actions">
        <button data-action="what-if-submit" ${disabled ? "disabled" : ""}>${w.busy ? "Running…" : "Run what-if"}</button>
      </div>
      ${summary}
    </section>
  `;
}

type PortfolioColumn = {
  key: PortfolioSortKey | null;
  label: string;
  align?: "right" | "center";
};

const PORTFOLIO_COLUMNS: PortfolioColumn[] = [
  { key: "runId", label: "Run" },
  { key: "createdAt", label: "Created" },
  { key: "engineVersion", label: "Engine" },
  { key: "baseRunId", label: "Base" },
  { key: "projectCount", label: "Projects", align: "right" },
  { key: "meanTotalScore", label: "Mean score", align: "right" },
  { key: "vmtFlaggedCount", label: "VMT flagged", align: "right" },
  { key: "dacShare", label: "DAC share", align: "right" },
  { key: null, label: "Planner Pack" },
  { key: "exportReady", label: "Ready", align: "center" },
  { key: null, label: "Actions" },
];

function renderPortfolioRow(run: PortfolioRun): string {
  const selected = state.portfolio.selectedRunIds.includes(run.runId);
  const label = projectRunLabel(state.projectState, state.workspace, run.runId);
  const labelMarkup =
    label && label !== run.runId ? `<span class="run-label">${escapeHtml(label)}</span>` : "";
  const base = run.baseRunId ? `<code>${escapeHtml(run.baseRunId)}</code>` : "—";
  const ppack = run.plannerPackArtifacts.length
    ? run.plannerPackArtifacts.map((a) => `<code>${escapeHtml(a)}</code>`).join(" ")
    : "—";
  const ready = run.exportReady
    ? `<span class="pf-ready ok">ready</span>`
    : `<span class="pf-ready bad">blocked</span>`;
  const created = run.createdAt ? run.createdAt.slice(0, 19).replace("T", " ") : "—";
  return `
    <tr class="${selected ? "pf-row selected" : "pf-row"}">
      <td class="pf-select">
        <input type="checkbox" data-portfolio-select="${escapeHtml(run.runId)}" ${selected ? "checked" : ""} />
      </td>
      <td><code>${escapeHtml(run.runId)}</code>${labelMarkup}${run.hasWhatIfOverrides ? '<span class="pf-tag">what-if</span>' : ""}</td>
      <td>${escapeHtml(created)}</td>
      <td>${escapeHtml(run.engineVersion ?? "—")}</td>
      <td>${base}</td>
      <td class="pf-num">${run.projectCount}</td>
      <td class="pf-num">${escapeHtml(formatMeanScore(run.meanTotalScore))}</td>
      <td class="pf-num">${run.vmtFlaggedCount}</td>
      <td class="pf-num">${escapeHtml(formatDacShare(run.dacShare))}</td>
      <td>${ppack}</td>
      <td class="pf-center">${ready}</td>
      <td><button type="button" data-portfolio-open="${escapeHtml(run.runId)}" class="link-btn">Open</button></td>
    </tr>
  `;
}

function renderPortfolioHeader(): string {
  const { sortKey, sortDirection } = state.portfolio;
  return PORTFOLIO_COLUMNS.map((col) => {
    if (!col.key) {
      return `<th class="${col.align === "center" ? "pf-center" : ""}">${escapeHtml(col.label)}</th>`;
    }
    const active = sortKey === col.key;
    const arrow = active ? (sortDirection === "asc" ? " ▲" : " ▼") : "";
    const cls = [
      col.align === "right" ? "pf-num" : col.align === "center" ? "pf-center" : "",
      "pf-sortable",
      active ? "active" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return `
      <th class="${cls}">
        <button type="button" data-sort-key="${col.key}" class="pf-sort-btn">${escapeHtml(col.label)}${arrow}</button>
      </th>
    `;
  }).join("");
}

function renderPortfolio(): string {
  const pf = state.portfolio;
  const result = pf.result;
  const selection = pf.selectedRunIds;
  const canDiff = selection.length === 2 && selection[0] !== selection[1];
  const status = pf.status || (result ? "Ready" : "Refresh to load runs");
  const totals = (() => {
    const summary = result?.summary;
    if (!summary) return "";
    const meanScore =
      summary.meanPortfolioScore === null ? "—" : summary.meanPortfolioScore.toFixed(3);
    const dac = formatDacShare(summary.meanDacShare);
    const engines = summary.engineVersions.length
      ? summary.engineVersions.map((v) => `<code>${escapeHtml(v)}</code>`).join(", ")
      : "—";
    return `
      <div class="pf-totals">
        <span><strong>${summary.exportReadyCount}</strong> / ${summary.runCount} export-ready</span>
        <span>Mean portfolio score: <strong>${escapeHtml(meanScore)}</strong></span>
        <span>VMT flagged (total): <strong>${summary.totalVmtFlaggedCount}</strong></span>
        <span>Mean DAC share: <strong>${escapeHtml(dac)}</strong></span>
        <span>Engines: ${engines}</span>
        <span>What-if edges: <strong>${summary.lineageEdges.length}</strong></span>
      </div>
    `;
  })();
  const table =
    result && result.runs.length > 0
      ? `
        <div class="pf-scroll">
          <table class="pf-table">
            <thead>
              <tr>
                <th class="pf-select-head">Pick</th>
                ${renderPortfolioHeader()}
              </tr>
            </thead>
            <tbody>
              ${sortPortfolioRuns(result.runs, pf.sortKey, pf.sortDirection)
                .map(renderPortfolioRow)
                .join("")}
            </tbody>
          </table>
        </div>
      `
      : `<p class="muted">No runs loaded yet. Run the demo or any workflow, then click <strong>Refresh portfolio</strong>.</p>`;
  const selectionHint =
    selection.length === 0
      ? "Tick two runs to diff them."
      : selection.length === 1
        ? `Selected <code>${escapeHtml(selection[0])}</code>. Pick one more.`
        : `Selected <code>${escapeHtml(selection[0])}</code> and <code>${escapeHtml(selection[1])}</code>.`;
  const lastDiff = pf.lastDiffPath
    ? `<p class="pf-last-diff">Last diff report: <code>${escapeHtml(pf.lastDiffPath)}</code></p>`
    : "";
  return `
    <section class="panel portfolio-panel" id="portfolio">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">8</span> Portfolio</p>
          <h2>Workspace Portfolio</h2>
        </div>
        <span>${escapeHtml(status)}</span>
      </div>
      <p class="muted">Every run in this workspace at a glance — mean score, VMT flags, DAC share, Planner Pack coverage, QA readiness, and what-if lineage. Pick any two rows to diff them.</p>
      <div class="pf-toolbar">
        <button data-action="portfolio-refresh" ${pf.busy ? "disabled" : ""}>${pf.busy ? "Loading…" : "Refresh portfolio"}</button>
        <button data-action="portfolio-diff" ${pf.busy || !canDiff ? "disabled" : ""}>Diff selected</button>
        <span class="pf-selection-hint">${selectionHint}</span>
      </div>
      ${totals}
      ${table}
      ${lastDiff}
    </section>
  `;
}

function renderArtifacts() {
  const artifacts = state.artifacts;
  const qa = summarizeQa(artifacts?.qaReport ?? null);
  const categories = manifestOutputCategories(artifacts?.manifest ?? null);
  const report = artifacts?.reportMarkdown?.trim();
  const runSummary = summarizeRunArtifacts(artifacts ?? null);
  const generated = runSummary?.generatedArtifacts.length
    ? runSummary.generatedArtifacts
        .map((entry) => `${entry.category}: ${entry.count}`)
        .join(", ")
    : "No manifest outputs yet";
  const plannerPack = runSummary?.plannerPackArtifacts.length
    ? runSummary.plannerPackArtifacts.map((artifact) => `<code>${escapeHtml(artifact)}</code>`).join(" ")
    : "No Planner Pack artifacts yet";
  const bridgeGenerated =
    runSummary?.bridgeGeneratedFileCount === null || runSummary?.bridgeGeneratedFileCount === undefined
      ? "No bridge file links recorded"
      : `${runSummary.bridgeGeneratedFileCount} generated bridge file link(s)`;
  const bridgeExecutionReportCount = runSummary?.bridgeExecutionReports.length ?? 0;
  const indexStatus = artifacts?.indexStatus ?? "not indexed";
  const indexUpdatedAt = artifacts?.indexUpdatedAt ?? "not recorded";
  const indexArtifactCount = artifacts?.files.length ?? 0;
  const routing = runSummary?.routing;
  const routingText = routing
    ? `${routing.selectedSource} (${routing.impedance})`
    : "No routing diagnosis recorded";
  const routingDetail = routing?.detail ?? "";
  const routingComparison = routing?.proxyComparison;
  const routingComparisonText = routingComparison
    ? `${routingComparison.coverageStatus ?? "coverage unknown"}: ${routingComparison.reachablePairs ?? 0}/${routingComparison.comparedPairs ?? 0} zone pairs compared; mean absolute delta ${formatOptionalNumber(
        routingComparison.meanAbsDeltaMinutes,
        1,
      )} min.`
    : "No network/proxy comparison recorded.";
  const routingComparisonDetail = routingComparison
    ? `Network mean ${formatOptionalNumber(
        routingComparison.meanNetworkMinutes,
        1,
      )} min; proxy mean ${formatOptionalNumber(
        routingComparison.meanProxyMinutes,
        1,
      )} min at ${formatOptionalNumber(routingComparison.proxySpeedKph, 1)} kph; max delta ${formatOptionalNumber(
        routingComparison.maxAbsDeltaMinutes,
        1,
      )} min; unreachable pairs ${routingComparison.unreachablePairs ?? 0}.`
    : "";
  const qaExportReady = runSummary?.qaExportReady;
  const bridgePackageReady = runSummary?.bridgeExportReady;
  const detailedForecastReady = runSummary?.detailedForecastReady;
  const detailedForecastStatus = readinessLabel(detailedForecastReady);
  const detailedForecastBreakdown =
    runSummary && runSummary.detailedForecastStatuses.length > 0
      ? `<ul>${runSummary.detailedForecastStatuses
          .map((item) => {
            const blockers = item.blockers.length > 0 ? ` Missing: ${escapeHtml(item.blockers.join(", "))}.` : "";
            const summary = item.summary ? ` ${escapeHtml(item.summary)}` : "";
            return `<li><strong>${escapeHtml(item.bridge)}</strong>: ${escapeHtml(item.statusLabel)}.${summary}${blockers}</li>`;
          })
          .join("")}</ul>`
      : "<p>No detailed-forecast readiness summary recorded.</p>";
  const skippedBridges =
    runSummary && runSummary.bridgeSkippedInputs.length > 0
      ? `<ul>${runSummary.bridgeSkippedInputs
          .map((item) => {
            const missing = item.missingInputs.length
              ? item.missingInputs.join(", ")
              : item.reason || "not recorded";
            return `<li><strong>${escapeHtml(item.bridge)}</strong>: missing ${escapeHtml(missing)}</li>`;
          })
          .join("")}</ul>`
      : "<p>No skipped bridges recorded.</p>";
  const warnings =
    runSummary && runSummary.warnings.length > 0
      ? `<ul>${runSummary.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
      : "<p>No warnings recorded.</p>";
  const missingSidecars =
    runSummary && runSummary.missingSidecars.length > 0
      ? `<ul>${runSummary.missingSidecars.map((sidecar) => `<li>${escapeHtml(sidecar)}</li>`).join("")}</ul>`
      : "<p>No missing manifest sidecars recorded.</p>";
  const artifactPreview = state.artifactPreview;
  const artifactPreviewMarkup = artifactPreview.preview
    ? `
      <div class="artifact-preview-meta">
        <strong>${escapeHtml(artifactBasename(artifactPreview.preview.path))}</strong>
        <code>${escapeHtml(artifactPreview.preview.path)}</code>
      </div>
      <pre>${escapeHtml(artifactPreview.preview.content)}</pre>
    `
    : `<p class="muted">Select a text artifact to preview its contents.</p>`;

  return `
    <section class="panel run-summary-panel">
      <div class="section-head">
        <div>
          <p class="eyebrow">Run Summary</p>
          <h2>${escapeHtml(runSummary?.runId ?? state.runId)}</h2>
        </div>
        <span>${escapeHtml(runSummary?.scenarioIds.join(", ") || "No scenarios loaded")}</span>
      </div>
      <div class="run-summary-grid">
        <div>
          <strong>Manifest</strong>
          <code>${escapeHtml(runSummary?.manifestPath ?? "No manifest yet")}</code>
        </div>
        <div>
          <strong>QA export</strong>
          <span class="pf-ready ${readinessTone(qaExportReady)}">${readinessLabel(qaExportReady)}</span>
        </div>
        <div>
          <strong>Bridge package validation</strong>
          <span class="pf-ready ${readinessTone(bridgePackageReady)}">${readinessLabel(bridgePackageReady)}</span>
        </div>
        <div>
          <strong>Detailed forecast readiness</strong>
          <span class="pf-ready ${readinessTone(detailedForecastReady)}">${escapeHtml(detailedForecastStatus)}</span>
        </div>
        <div>
          <strong>Bridge files</strong>
          <span>${escapeHtml(bridgeGenerated)}</span>
        </div>
        <div>
          <strong>Bridge execution</strong>
          <span>${escapeHtml(`${bridgeExecutionReportCount} report(s)`)}</span>
        </div>
        <div>
          <strong>Routing</strong>
          <span>${escapeHtml(routingText)}</span>
        </div>
        <div>
          <strong>Generated artifacts</strong>
          <span>${escapeHtml(generated)}</span>
        </div>
        <div>
          <strong>Planner Pack</strong>
          <span>${plannerPack}</span>
        </div>
        <div>
          <strong>Report</strong>
          <code>${escapeHtml(runSummary?.reportPath ?? "No report path recorded")}</code>
        </div>
        <div>
          <strong>Workspace index</strong>
          <span>${escapeHtml(`${indexStatus}; ${indexArtifactCount} artifact(s)`)}</span>
        </div>
      </div>
      <p class="muted">Index refreshed: ${escapeHtml(indexUpdatedAt)}</p>
      <details>
        <summary>Warnings</summary>
        ${warnings}
      </details>
      <details>
        <summary>Manifest sidecars</summary>
        ${missingSidecars}
      </details>
      <details>
        <summary>Detailed forecast readiness</summary>
        ${detailedForecastBreakdown}
      </details>
      <details>
        <summary>Bridge package inputs</summary>
        ${skippedBridges}
      </details>
      <details>
        <summary>Routing diagnosis</summary>
        <p>${escapeHtml(routingDetail || "No routing diagnosis recorded.")}</p>
        <p>Requested: <code>${escapeHtml(routing?.requestedSource ?? "unknown")}</code>. Graph ID: <code>${escapeHtml(routing?.graphId ?? "none")}</code>.</p>
        <p>${escapeHtml(routingComparisonText)}</p>
        ${
          routingComparison
            ? `<p>${escapeHtml(routingComparisonDetail)}</p><p>${escapeHtml(
                routingComparison.coverageDetail ?? "No routing coverage detail recorded.",
              )}</p><p>${escapeHtml(
                routingComparison.note ?? "Comparison is a screening diagnostic, not calibration.",
              )}</p>`
            : ""
        }
      </details>
      <details>
        <summary>Bridge execution reports</summary>
        ${
          runSummary && runSummary.bridgeExecutionReports.length > 0
            ? `<ul>${runSummary.bridgeExecutionReports.map((path) => `<li><code>${escapeHtml(path)}</code></li>`).join("")}</ul>`
            : "<p>No bridge execution reports recorded.</p>"
        }
      </details>
    </section>

    <section class="panel qa-panel ${qa.tone}">
      <div>
        <p class="eyebrow"><span class="step-num">3</span> ClawQA</p>
        <h2>${escapeHtml(qa.label)}</h2>
        <p>${qa.blockers.length > 0 ? escapeHtml(qa.blockers.join(", ")) : "No blockers recorded."}</p>
      </div>
      <div class="metric-stack">
        <span>${escapeHtml(artifacts?.runId ?? state.runId)}</span>
        <small>run id</small>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <p class="eyebrow">Outputs</p>
          <h2>Artifacts</h2>
        </div>
        <span>${categories.length} categories</span>
      </div>
      ${
        artifacts?.files.length
          ? `<ul class="artifact-list">${artifacts.files
              .slice(0, 80)
              .map((file) => {
                const previewable = isPreviewableArtifact(file);
                return `
                  <li>
                    <span title="${escapeHtml(file)}">${escapeHtml(artifactBasename(file))}</span>
                    <button
                      type="button"
                      class="artifact-preview-btn"
                      data-artifact-preview="${escapeHtml(file)}"
                      ${!previewable || artifactPreview.busy ? "disabled" : ""}
                    >Preview</button>
                  </li>
                `;
              })
              .join("")}</ul>`
          : `<p class="muted">Run a workflow to create manifests, tables, bridge packages, and reports.</p>`
      }
      <div class="artifact-preview">
        <div class="section-head">
          <strong>Artifact Preview</strong>
          <span>${escapeHtml(artifactPreview.status)}</span>
        </div>
        ${artifactPreviewMarkup}
      </div>
    </section>

    <section class="panel report-panel">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">4</span> Narrative</p>
          <h2>Report Preview</h2>
        </div>
        <span>${report ? "Markdown" : "Waiting"}</span>
      </div>
      <pre>${escapeHtml(report || "No report yet. Run a workflow to generate a plain-English summary you can share with a client or stakeholder.")}</pre>
    </section>
  `;
}

function renderBridgeExecutionResult(payload: Record<string, unknown> | null): string {
  if (!payload) {
    return `<p class="muted">Run a dry-run check first. It writes the same execution report shape without starting the external engine.</p>`;
  }
  const feedback = parseBridgeOperatorFeedback(payload);
  if (!feedback) {
    return `<pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
  }
  const expectedCount =
    feedback.outputSummary.expectedCount ?? feedback.expectedOutputs.length;
  const existingCount =
    feedback.outputSummary.existingCount ?? feedback.existingOutputs.length;
  const missingCount = feedback.outputSummary.missingCount ?? feedback.missingOutputs.length;
  const tools =
    feedback.requiredTools.length > 0
      ? `<ul class="bridge-tool-list">${feedback.requiredTools
          .map((tool) => {
            const tone = tool.available ? "ok" : "missing";
            const detail = tool.available
              ? tool.path
                ? `Found at ${tool.path}`
                : "Available"
              : "Missing";
            return `
              <li>
                <span class="status-dot ${tone}"></span>
                <div>
                  <strong>${escapeHtml(tool.id)}</strong>
                  <span><code>${escapeHtml(tool.command)}</code> ${escapeHtml(detail)}</span>
                  ${tool.note ? `<small>${escapeHtml(tool.note)}</small>` : ""}
                </div>
              </li>
            `;
          })
          .join("")}</ul>`
      : `<p class="muted">No external command checks were recorded.</p>`;
  const nextSteps =
    feedback.nextSteps.length > 0
      ? `<ul>${feedback.nextSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>`
      : `<p class="muted">No follow-up actions were recorded.</p>`;
  const missingOutputs =
    feedback.missingOutputs.length > 0
      ? `<details>
          <summary>Missing expected outputs (${feedback.missingOutputs.length})</summary>
          <ul>${feedback.missingOutputs
            .slice(0, 20)
            .map((path) => `<li><code>${escapeHtml(path)}</code></li>`)
            .join("")}</ul>
        </details>`
      : `<p class="muted">All expected outputs that can be checked locally are present.</p>`;
  return `
    <div class="bridge-feedback">
      <strong>${escapeHtml(feedback.operatorSummary)}</strong>
      <dl class="bridge-feedback-meta">
        <div>
          <dt>Status</dt>
          <dd><code>${escapeHtml(feedback.operatorStatus)}</code></dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd><code>${escapeHtml(feedback.evidenceLevel)}</code></dd>
        </div>
        <div>
          <dt>Readiness</dt>
          <dd><code>${escapeHtml(feedback.forecastReadinessStatus ?? "unknown")}</code></dd>
        </div>
        <div>
          <dt>Package Files</dt>
          <dd>${escapeHtml(existingCount)} / ${escapeHtml(expectedCount)} present, ${escapeHtml(missingCount)} missing</dd>
        </div>
      </dl>
      ${
        feedback.commandDisplay
          ? `<p><strong>Command:</strong> <code>${escapeHtml(feedback.commandDisplay)}</code></p>`
          : `<p class="muted">No generated command was recorded.</p>`
      }
      ${
        feedback.commandCwd
          ? `<p><strong>Run folder:</strong> <code>${escapeHtml(feedback.commandCwd)}</code></p>`
          : ""
      }
      <div class="bridge-feedback-section">
        <h3>Tool Checks</h3>
        ${tools}
      </div>
      <div class="bridge-feedback-section">
        <h3>Package Files</h3>
        ${missingOutputs}
      </div>
      <div class="bridge-feedback-section">
        <h3>Next Steps</h3>
        ${nextSteps}
      </div>
      <details>
        <summary>Raw command response</summary>
        <pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
      </details>
    </div>
  `;
}

function renderBridgeExecution() {
  const execution = state.bridgeExecution;
  const scenario = execution.scenarioId || normalizeScenarios(state.scenarios)[0] || "baseline";
  const last = renderBridgeExecutionResult(execution.lastResult);
  return `
    <section class="panel bridge-execution-panel" id="bridge-execution">
      <div class="section-head">
        <div>
          <p class="eyebrow"><span class="step-num">4</span> Bridge Execution</p>
          <h2>External Engine Check</h2>
        </div>
        <span>${escapeHtml(execution.status || "Ready")}</span>
      </div>
      <p class="muted">Execution reports confirm a bridge command ran or was blocked. Forecast claims still require validation-ready detailed-engine evidence.</p>
      <div class="bridge-exec-grid">
        <label>
          Bridge
          <select id="bridge-execution-bridge">
            <option value="sumo" ${selected("sumo", execution.bridge)}>SUMO</option>
            <option value="matsim" ${selected("matsim", execution.bridge)}>MATSim</option>
            <option value="urbansim" ${selected("urbansim", execution.bridge)}>UrbanSim</option>
            <option value="dtalite" ${selected("dtalite", execution.bridge)}>DTALite</option>
            <option value="tbest" ${selected("tbest", execution.bridge)}>TBEST</option>
          </select>
        </label>
        <label>
          Scenario
          <input id="bridge-execution-scenario" value="${escapeHtml(scenario)}" spellcheck="false" />
        </label>
        <label class="check-row">
          <input id="bridge-execution-dry-run" type="checkbox" ${execution.dryRun ? "checked" : ""} />
          Dry run
        </label>
      </div>
      <button data-action="bridge-execute" ${execution.busy ? "disabled" : ""}>${execution.dryRun ? "Check readiness" : "Execute bridge"}</button>
      <div class="log bridge-exec-result">
        ${last}
      </div>
    </section>
  `;
}

function render() {
  appRoot.innerHTML = `
    <main class="shell">
      <aside class="rail">
        <div class="brand">
          <div class="brand-mark">CM</div>
          <div>
            <strong>ClawModeler</strong>
            <span>Screening workbench</span>
          </div>
        </div>
        <nav>
          <a href="#guide">Guide</a>
          <a href="#workspace">Workspace</a>
          <a href="#run">Run</a>
          <a href="#qa">QA</a>
          <a href="#bridge-execution">Bridge</a>
          <a href="#report">Report</a>
          <a href="#planner-pack">Planner Pack</a>
          <a href="#chat">Chat</a>
          <a href="#what-if">What-if</a>
          <a href="#portfolio">Portfolio</a>
        </nav>
        <p class="rail-note">Screening-level outputs. Use a detailed modeling workflow for final engineering decisions.</p>
      </aside>

      <section class="content">
        <header class="topbar">
          <div>
            <p class="eyebrow">Transportation sketch-planning, on your computer</p>
            <h1>Run a screening analysis without spreadsheets or cloud uploads.</h1>
          </div>
          <div class="run-state ${state.busy ? "busy" : ""}">
            <span></span>
            ${escapeHtml(state.status)}
          </div>
        </header>

        ${renderWelcome()}

        ${renderWorkflowGuide()}

        <section class="map-strip" aria-label="Planning map">
          <div class="route r1"></div>
          <div class="route r2"></div>
          <div class="route r3"></div>
          <div class="zone z1">North</div>
          <div class="zone z2">Core</div>
          <div class="zone z3">South</div>
        </section>

        <div class="layout">
          <section class="panel workspace-panel" id="workspace">
            <div class="section-head">
              <div>
                <p class="eyebrow"><span class="step-num">1</span> Workspace</p>
                <h2>Project Setup</h2>
              </div>
              <button data-action="doctor" ${state.busy ? "disabled" : ""}>Doctor</button>
            </div>

            <label>
              <span class="label-row">
                <span>Workspace path</span>
                <button type="button" data-action="pick-workspace" class="pick-btn" ${!isTauriRuntime() || state.busy ? "disabled" : ""} title="${isTauriRuntime() ? "Browse for a folder" : "Available in the desktop app"}">Pick folder…</button>
              </span>
              <input id="workspace" value="${escapeHtml(state.workspace)}" spellcheck="false" />
              <small class="help">Folder on your computer where ClawModeler stores this project's files. Pick an empty folder — it will be created if it doesn't exist.</small>
            </label>
            ${renderProjectMemory()}
            <label>
              Run ID
              <input id="run-id" value="${escapeHtml(state.runId)}" spellcheck="false" />
              <small class="help">Short name for this analysis run (e.g., "demo", "2026-baseline"). Used to name the output folder.</small>
            </label>
            <label>
              Run label
              <input id="run-label" value="${escapeHtml(state.runLabel)}" spellcheck="true" />
              <small class="help">Planner-facing name shown in recent runs and portfolio review. It does not rename files.</small>
            </label>
            <label>
              <span class="label-row">
                <span>Input paths</span>
                <button type="button" data-action="pick-inputs" class="pick-btn" ${!isTauriRuntime() || state.busy ? "disabled" : ""} title="${isTauriRuntime() ? "Browse for data files to add" : "Available in the desktop app"}">Add files…</button>
              </span>
              <textarea id="input-paths" rows="5" spellcheck="false" placeholder="/path/zones.geojson&#10;/path/socio.csv&#10;/path/projects.csv">${escapeHtml(
                state.inputPaths,
              )}</textarea>
              <small class="help">One path per line. Typical inputs: zones (GeoJSON), socio-economic data (CSV), projects (CSV). Leave blank to use the built-in demo.</small>
            </label>
            <label>
              <span class="label-row">
                <span>Question JSON</span>
                <span class="label-row-actions">
                  <button type="button" data-action="create-question" class="pick-btn" ${!isTauriRuntime() || state.busy ? "disabled" : ""} title="${isTauriRuntime() ? "Write a starter question.json you can edit" : "Available in the desktop app"}">Create starter…</button>
                  <button type="button" data-action="pick-question" class="pick-btn" ${!isTauriRuntime() || state.busy ? "disabled" : ""} title="${isTauriRuntime() ? "Browse for a question.json file" : "Available in the desktop app"}">Pick file…</button>
                </span>
              </span>
              <input id="question-path" value="${escapeHtml(
                state.questionPath,
              )}" placeholder="/path/question.json" spellcheck="false" />
              <small class="help">Path to a question.json file describing what you want to analyze (scope, metrics, timeframe). Not needed for the demo.</small>
            </label>
            <label>
              Scenarios
              <input id="scenarios" value="${escapeHtml(
                state.scenarios,
              )}" placeholder="baseline build" spellcheck="false" />
              <small class="help">Space- or comma-separated names for the scenarios to run (e.g., "baseline build"). Defaults to "baseline".</small>
            </label>
            <div class="routing-grid">
              <label>
                Routing source
                <select id="routing-source">
                  <option value="question" ${selected("question", state.routingSource)}>Use question.json</option>
                  <option value="auto" ${selected("auto", state.routingSource)}>Auto</option>
                  <option value="network_edges_csv" ${selected("network_edges_csv", state.routingSource)}>Network edges CSV</option>
                  <option value="graphml" ${selected("graphml", state.routingSource)}>GraphML cache</option>
                  <option value="euclidean_proxy" ${selected("euclidean_proxy", state.routingSource)}>Proxy travel times</option>
                </select>
                <small class="help">Controls the run's accessibility routing source without editing question.json.</small>
              </label>
              <label>
                Graph ID
                <input id="routing-graph-id" value="${escapeHtml(
                  state.routingGraphId,
                )}" placeholder="davis-drive" spellcheck="false" />
                <small class="help">Optional GraphML cache name in cache/graphs, used with GraphML routing.</small>
              </label>
              <label>
                Impedance
                <select id="routing-impedance">
                  <option value="minutes" ${selected("minutes", state.routingImpedance)}>Minutes</option>
                </select>
                <small class="help">Minutes is the supported routing impedance for this release.</small>
              </label>
            </div>
            <label class="check-row">
              <input id="skip-bridges" type="checkbox" ${state.skipBridges ? "checked" : ""} />
              Skip bridge packages
            </label>
            <small class="help check-help">Bridge packages prep handoff to SUMO/MATSim/UrbanSim/TBEST/DTALite. Skip this unless you're handing off to those tools.</small>
          </section>

          <section class="panel actions-panel" id="run">
            <div class="section-head">
              <div>
                <p class="eyebrow"><span class="step-num">2</span> Run</p>
                <h2>Workflow</h2>
              </div>
              <button data-action="refresh" ${state.busy ? "disabled" : ""}>Refresh</button>
            </div>
            <p class="panel-hint">New here? Click <strong>Run Demo</strong> to see a complete sample analysis — no inputs needed.</p>
            <div class="button-grid">
              <button data-action="init" ${state.busy ? "disabled" : ""}>Create Workspace</button>
              <button data-action="demo" ${state.busy ? "disabled" : ""}>Run Demo</button>
              <button data-action="full" ${state.busy ? "disabled" : ""}>Run Full Workflow</button>
              <button data-action="diagnose" ${state.busy ? "disabled" : ""}>Diagnose</button>
              <button data-action="report" ${state.busy ? "disabled" : ""}>Regenerate Report</button>
            </div>

            <div class="doctor">
              ${renderDoctor()}
            </div>

            <div class="log">
              ${state.commandLog.map((entry) => `<pre>${escapeHtml(entry)}</pre>`).join("")}
            </div>
          </section>
        </div>

        <div id="qa" class="results">
          ${renderArtifacts()}
        </div>

        ${renderBridgeExecution()}

        ${renderPlannerPack()}

        ${renderChat()}

        ${renderWhatIf()}

        ${renderPortfolio()}
      </section>
    </main>
  `;
  bindControls();
}

render();
void refreshDoctor();
