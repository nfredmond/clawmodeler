export type RunMode = "demo-full" | "full" | "diagnose" | "report-only";

export type QaSummary = {
  label: string;
  tone: "ready" | "blocked" | "unknown";
  blockers: string[];
};

export type WorkspaceArtifacts = {
  workspace: string;
  runId: string;
  manifest: Record<string, unknown> | null;
  qaReport: Record<string, unknown> | null;
  workflowReport: Record<string, unknown> | null;
  reportMarkdown: string | null;
  files: string[];
  filesTruncated: boolean;
};

export type GeneratedArtifactSummary = {
  category: string;
  count: number;
};

export type BridgeSkippedSummary = {
  bridge: string;
  requiredInputs: string[];
  missingInputs: string[];
  reason: string | null;
};

export type DetailedForecastStatusSummary = {
  bridge: string;
  status: string;
  statusLabel: string;
  blockers: string[];
  summary: string | null;
};

export type RoutingSummary = {
  requestedSource: string;
  selectedSource: string;
  graphId: string | null;
  impedance: string;
  detail: string | null;
};

export type RunSummary = {
  runId: string;
  workspacePath: string;
  manifestPath: string;
  reportPath: string | null;
  scenarioIds: string[];
  qaExportReady: boolean | null;
  bridgeExportReady: boolean | null;
  detailedForecastReady: boolean | null;
  detailedForecastStatuses: DetailedForecastStatusSummary[];
  bridgeGeneratedFileCount: number | null;
  bridgeExecutionReports: string[];
  bridgeSkippedInputs: BridgeSkippedSummary[];
  routing: RoutingSummary | null;
  plannerPackArtifacts: string[];
  generatedArtifacts: GeneratedArtifactSummary[];
  missingSidecars: string[];
  warnings: string[];
};

export type WorkflowStepId =
  | "workspace"
  | "run"
  | "qa-artifacts"
  | "planner-pack"
  | "chat"
  | "what-if"
  | "portfolio-diff";

export type WorkflowStepState = "ready" | "running" | "done" | "blocked" | "optional";

export type WorkflowGuideStep = {
  id: WorkflowStepId;
  label: string;
  state: WorkflowStepState;
  status: string;
  actionLabel: string;
  anchor: string;
  blocker: string | null;
};

export type WorkflowGuide = {
  steps: WorkflowGuideStep[];
  currentStepId: WorkflowStepId | null;
  nextActionLabel: string | null;
  nextActionAnchor: string | null;
};

type PlannerPackSpec = {
  kind: PlannerPackKind;
  label: string;
  tableSuffixes: string[];
};

export type PlannerPackKind =
  | "ceqa-vmt"
  | "lapm-exhibit"
  | "rtp-chapter"
  | "equity-lens"
  | "atp-packet"
  | "hsip"
  | "cmaq"
  | "stip";

export const PLANNER_PACK_SPECS: PlannerPackSpec[] = [
  { kind: "ceqa-vmt", label: "CEQA VMT", tableSuffixes: ["outputs/tables/ceqa_vmt.csv"] },
  { kind: "lapm-exhibit", label: "LAPM", tableSuffixes: ["outputs/tables/lapm_exhibit.csv"] },
  {
    kind: "rtp-chapter",
    label: "RTP",
    tableSuffixes: ["outputs/tables/rtp_chapter_projects.csv"],
  },
  { kind: "equity-lens", label: "Equity", tableSuffixes: ["outputs/tables/equity_lens.csv"] },
  { kind: "atp-packet", label: "ATP", tableSuffixes: ["outputs/tables/atp_packet.csv"] },
  { kind: "hsip", label: "HSIP", tableSuffixes: ["outputs/tables/hsip.csv"] },
  { kind: "cmaq", label: "CMAQ", tableSuffixes: ["outputs/tables/cmaq.csv"] },
  { kind: "stip", label: "STIP", tableSuffixes: ["outputs/tables/stip.csv"] },
];

export type PlannerPackSubmitPayload = {
  workspace: string;
  runId: string;
  kind: PlannerPackKind;
  cycleYear: number | null;
  analysisYear: number | null;
};

export type PlannerPackValidation =
  | { ok: true; payload: PlannerPackSubmitPayload }
  | { ok: false; error: string };

const PREVIEWABLE_ARTIFACT_EXTENSIONS = new Set([
  ".csv",
  ".json",
  ".jsonl",
  ".md",
  ".txt",
  ".xml",
  ".sh",
  ".toml",
  ".yaml",
  ".yml",
]);

export function normalizePathList(input: string): string[] {
  return input
    .split(/\r?\n|,/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function normalizeScenarios(input: string): string[] {
  const values = input
    .split(/\s|,/u)
    .map((item) => item.trim())
    .filter(Boolean);
  return values.length > 0 ? values : ["baseline"];
}

export function buildFullWorkflowArgs(params: {
  workspace: string;
  inputs: string[];
  question: string;
  runId: string;
  scenarios: string[];
  skipBridges: boolean;
  routingSource?: string;
  routingGraphId?: string;
  routingImpedance?: string;
}): string[] {
  const args = [
    "workflow",
    "full",
    "--workspace",
    params.workspace,
    "--inputs",
    ...params.inputs,
    "--question",
    params.question,
    "--run-id",
    params.runId,
    "--scenarios",
    ...params.scenarios,
  ];
  if (params.routingSource && params.routingSource !== "question") {
    args.push("--routing-source", params.routingSource);
  }
  if (params.routingGraphId?.trim()) {
    args.push("--routing-graph-id", params.routingGraphId.trim());
  }
  if (params.routingImpedance?.trim()) {
    args.push("--routing-impedance", params.routingImpedance.trim());
  }
  if (params.skipBridges) {
    args.push("--skip-bridges");
  }
  return args;
}

export function buildBridgeExecuteArgs(params: {
  workspace: string;
  runId: string;
  bridge: string;
  scenarioId: string;
  dryRun: boolean;
}): string[] {
  const args = [
    "bridge",
    params.bridge,
    "execute",
    "--workspace",
    params.workspace,
    "--run-id",
    params.runId,
    "--scenario-id",
    params.scenarioId || "baseline",
  ];
  if (params.dryRun) {
    args.push("--dry-run");
  }
  return args;
}

export function summarizeQa(qaReport: Record<string, unknown> | null): QaSummary {
  if (!qaReport) {
    return { label: "No QA report", tone: "unknown", blockers: [] };
  }

  const rawBlockers = qaReport.blockers;
  const blockers = Array.isArray(rawBlockers) ? rawBlockers.map((item) => String(item)) : [];

  if (qaReport.export_ready === true) {
    return { label: "Export ready", tone: "ready", blockers };
  }
  if (qaReport.export_ready === false) {
    return { label: "Export blocked", tone: "blocked", blockers };
  }
  return { label: "QA status unknown", tone: "unknown", blockers };
}

export function countJsonLines(input: string | null): number {
  if (!input) {
    return 0;
  }
  return input
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean).length;
}

export function manifestOutputCategories(manifest: Record<string, unknown> | null): string[] {
  const outputs = manifest?.outputs;
  if (!outputs || typeof outputs !== "object" || Array.isArray(outputs)) {
    return [];
  }
  return Object.keys(outputs).toSorted();
}

function workspacePathJoin(workspace: string, ...segments: string[]): string {
  const trimmed = workspace.trim().replace(/[/\\]+$/u, "");
  const separator = trimmed.includes("\\") && !trimmed.includes("/") ? "\\" : "/";
  return [trimmed, ...segments].filter(Boolean).join(separator);
}

function stringValues(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => stringValues(item));
  }
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).flatMap((item) => stringValues(item));
  }
  return [];
}

function normalizedSuffix(value: string): string {
  return value.replace(/\\/gu, "/").replace(/^\.?\//u, "");
}

function pathHasSuffix(paths: string[], suffix: string): boolean {
  const normalizedNeedle = normalizedSuffix(suffix);
  return paths.some((path) => normalizedSuffix(path).endsWith(normalizedNeedle));
}

export function manifestOutputPaths(manifest: Record<string, unknown> | null): string[] {
  return stringValues(manifest?.outputs);
}

export function detectPlannerPackArtifacts(
  files: string[],
  manifest: Record<string, unknown> | null,
): string[] {
  const paths = [...files, ...manifestOutputPaths(manifest)];
  return PLANNER_PACK_SPECS.filter((spec) =>
    spec.tableSuffixes.some((suffix) => pathHasSuffix(paths, suffix)),
  ).map((spec) => spec.kind);
}

function generatedArtifactSummary(manifest: Record<string, unknown> | null): GeneratedArtifactSummary[] {
  const outputs = manifest?.outputs;
  if (!outputs || typeof outputs !== "object" || Array.isArray(outputs)) {
    return [];
  }
  return Object.entries(outputs)
    .map(([category, value]) => ({ category, count: stringValues(value).length }))
    .filter((entry) => entry.count > 0)
    .sort((a, b) => a.category.localeCompare(b.category));
}

function scenarioIds(manifest: Record<string, unknown> | null): string[] {
  const scenarios = manifest?.scenarios;
  if (!Array.isArray(scenarios)) {
    return [];
  }
  return scenarios
    .map((scenario) => {
      if (typeof scenario === "string") return scenario;
      if (scenario && typeof scenario === "object") {
        const raw = (scenario as Record<string, unknown>).scenario_id;
        return typeof raw === "string" ? raw : "";
      }
      return "";
    })
    .filter(Boolean);
}

function workflowReportPath(
  workflowReport: Record<string, unknown> | null,
  key: string,
): string | null {
  const artifacts = workflowReport?.artifacts;
  if (!artifacts || typeof artifacts !== "object" || Array.isArray(artifacts)) {
    return null;
  }
  return asString((artifacts as Record<string, unknown>)[key]);
}

function bridgeExportReady(workflowReport: Record<string, unknown> | null): boolean | null {
  const bridgeValidation = workflowReport?.bridge_validation;
  if (!bridgeValidation || typeof bridgeValidation !== "object" || Array.isArray(bridgeValidation)) {
    return null;
  }
  const value = (bridgeValidation as Record<string, unknown>).export_ready;
  return typeof value === "boolean" ? value : null;
}

function detailedEngineReadinessPayload(
  workflowReport: Record<string, unknown> | null,
  manifest: Record<string, unknown> | null,
): Record<string, unknown> | null {
  const workflowReadiness = workflowReport?.detailed_engine_readiness;
  if (workflowReadiness && typeof workflowReadiness === "object" && !Array.isArray(workflowReadiness)) {
    return workflowReadiness as Record<string, unknown>;
  }
  const manifestReadiness = manifest?.detailed_engine_readiness;
  if (manifestReadiness && typeof manifestReadiness === "object" && !Array.isArray(manifestReadiness)) {
    return manifestReadiness as Record<string, unknown>;
  }
  return null;
}

function detailedForecastStatuses(
  workflowReport: Record<string, unknown> | null,
  manifest: Record<string, unknown> | null,
): DetailedForecastStatusSummary[] {
  const readiness = detailedEngineReadinessPayload(workflowReport, manifest);
  const engines = readiness?.engines;
  if (!engines || typeof engines !== "object" || Array.isArray(engines)) {
    return [];
  }
  return Object.entries(engines)
    .map(([bridge, raw]) => {
      const row = raw && typeof raw === "object" && !Array.isArray(raw)
        ? (raw as Record<string, unknown>)
        : {};
      return {
        bridge,
        status: typeof row.status === "string" ? row.status : "handoff_only",
        statusLabel: typeof row.status_label === "string" ? row.status_label : bridge,
        blockers: asStringArray(row.missing_readiness_blockers),
        summary: asString(row.summary),
      };
    })
    .sort((a, b) => a.bridge.localeCompare(b.bridge));
}

function detailedForecastReady(
  workflowReport: Record<string, unknown> | null,
  manifest: Record<string, unknown> | null,
): boolean | null {
  const bridgeValidation = workflowReport?.bridge_validation;
  if (bridgeValidation && typeof bridgeValidation === "object" && !Array.isArray(bridgeValidation)) {
    const value = (bridgeValidation as Record<string, unknown>).detailed_forecast_ready;
    if (typeof value === "boolean") {
      return value;
    }
  }
  const statuses = detailedForecastStatuses(workflowReport, manifest);
  if (statuses.length === 0) {
    return null;
  }
  return statuses.every((item) => item.status === "validation_ready");
}

function bridgeGeneratedFileCount(workflowReport: Record<string, unknown> | null): number | null {
  const seen = new Set<string>();
  const bridgePrepare = workflowReport?.bridges;
  if (bridgePrepare && typeof bridgePrepare === "object" && !Array.isArray(bridgePrepare)) {
    const prepared = (bridgePrepare as Record<string, unknown>).prepared;
    if (Array.isArray(prepared)) {
      for (const item of prepared) {
        if (!item || typeof item !== "object" || Array.isArray(item)) continue;
        for (const path of asStringArray((item as Record<string, unknown>).generated_files)) {
          seen.add(path);
        }
      }
    }
  }

  const bridgeValidation = workflowReport?.bridge_validation;
  if (bridgeValidation && typeof bridgeValidation === "object" && !Array.isArray(bridgeValidation)) {
    const bridges = (bridgeValidation as Record<string, unknown>).bridges;
    if (Array.isArray(bridges)) {
      for (const item of bridges) {
        if (!item || typeof item !== "object" || Array.isArray(item)) continue;
        for (const path of asStringArray((item as Record<string, unknown>).generated_files)) {
          seen.add(path);
        }
      }
    }
  }

  return seen.size > 0 ? seen.size : null;
}

function bridgeExecutionReports(files: string[]): string[] {
  return files
    .filter((path) => normalizedSuffix(path).endsWith("bridge_execution_report.json"))
    .toSorted();
}

function routingSummary(workflowReport: Record<string, unknown> | null): RoutingSummary | null {
  const routing = workflowReport?.routing;
  if (!routing || typeof routing !== "object" || Array.isArray(routing)) {
    return null;
  }
  const row = routing as Record<string, unknown>;
  return {
    requestedSource:
      typeof row.requested_source === "string" ? row.requested_source : "auto",
    selectedSource:
      typeof row.selected_source === "string" ? row.selected_source : "unknown",
    graphId: asString(row.graph_id),
    impedance: typeof row.impedance === "string" ? row.impedance : "minutes",
    detail: asString(row.detail),
  };
}

function bridgeSkippedInputs(workflowReport: Record<string, unknown> | null): BridgeSkippedSummary[] {
  const bridgePrepare = workflowReport?.bridges;
  if (!bridgePrepare || typeof bridgePrepare !== "object" || Array.isArray(bridgePrepare)) {
    return [];
  }
  const skipped = (bridgePrepare as Record<string, unknown>).skipped;
  if (!Array.isArray(skipped)) {
    return [];
  }
  return skipped
    .map((item) => {
      const row = (item || {}) as Record<string, unknown>;
      return {
        bridge: typeof row.bridge === "string" ? row.bridge : "",
        requiredInputs: asStringArray(row.required_inputs),
        missingInputs: asStringArray(row.missing_inputs),
        reason: asString(row.reason),
      };
    })
    .filter((item) => item.bridge);
}

function collectWarnings(artifacts: WorkspaceArtifacts): string[] {
  const warnings = asStringArray(artifacts.manifest?.warnings);
  const qaBlockers = asStringArray(artifacts.qaReport?.blockers).map(
    (blocker) => `QA blocker: ${blocker}`,
  );
  const bridgeValidation = artifacts.workflowReport?.bridge_validation;
  const bridgeBlockers =
    bridgeValidation && typeof bridgeValidation === "object" && !Array.isArray(bridgeValidation)
      ? asStringArray((bridgeValidation as Record<string, unknown>).blockers).map(
          (blocker) => `Bridge blocker: ${blocker}`,
        )
      : [];
  const detailedForecastBlockers = detailedForecastStatuses(
    artifacts.workflowReport,
    artifacts.manifest,
  ).flatMap((item) =>
    item.blockers.map((blocker) => `Detailed forecast blocker (${item.bridge}): ${blocker}`),
  );
  if (artifacts.filesTruncated) {
    warnings.push("File list truncated; only the first 500 artifacts are shown.");
  }
  return [...warnings, ...qaBlockers, ...bridgeBlockers, ...detailedForecastBlockers];
}

function missingManifestSidecars(artifacts: WorkspaceArtifacts): string[] {
  const declared = artifacts.manifest?.artifacts;
  if (!declared || typeof declared !== "object" || Array.isArray(declared)) {
    return [];
  }
  const knownPaths = [...artifacts.files, ...manifestOutputPaths(artifacts.manifest)];
  const missing: string[] = [];
  for (const [key, value] of Object.entries(declared)) {
    for (const declaredPath of stringValues(value)) {
      if (!pathHasSuffix(knownPaths, declaredPath)) {
        missing.push(`${key}: ${declaredPath}`);
      }
    }
  }
  return missing.toSorted();
}

export function summarizeRunArtifacts(artifacts: WorkspaceArtifacts | null): RunSummary | null {
  if (!artifacts) {
    return null;
  }
  return {
    runId: artifacts.runId,
    workspacePath: artifacts.workspace,
    manifestPath: workflowReportPath(artifacts.workflowReport, "manifest") ?? workspacePathJoin(
      artifacts.workspace,
      "runs",
      artifacts.runId,
      "manifest.json",
    ),
    reportPath: workflowReportPath(artifacts.workflowReport, "report"),
    scenarioIds: scenarioIds(artifacts.manifest),
    qaExportReady:
      typeof artifacts.qaReport?.export_ready === "boolean" ? artifacts.qaReport.export_ready : null,
    bridgeExportReady: bridgeExportReady(artifacts.workflowReport),
    detailedForecastReady: detailedForecastReady(artifacts.workflowReport, artifacts.manifest),
    detailedForecastStatuses: detailedForecastStatuses(artifacts.workflowReport, artifacts.manifest),
    bridgeGeneratedFileCount: bridgeGeneratedFileCount(artifacts.workflowReport),
    bridgeExecutionReports: bridgeExecutionReports(artifacts.files),
    bridgeSkippedInputs: bridgeSkippedInputs(artifacts.workflowReport),
    routing: routingSummary(artifacts.workflowReport),
    plannerPackArtifacts: detectPlannerPackArtifacts(artifacts.files, artifacts.manifest),
    generatedArtifacts: generatedArtifactSummary(artifacts.manifest),
    missingSidecars: missingManifestSidecars(artifacts),
    warnings: collectWarnings(artifacts),
  };
}

function workflowStep(params: WorkflowGuideStep): WorkflowGuideStep {
  return params;
}

export function deriveWorkflowGuide(params: {
  workspace: string;
  runId: string;
  inputPaths: string;
  questionPath: string;
  busy: boolean;
  artifacts: WorkspaceArtifacts | null;
  plannerPackBusy: boolean;
  chatBusy: boolean;
  chatTurnCount: number;
  whatIfBusy: boolean;
  hasWhatIfResult: boolean;
  portfolioBusy: boolean;
  portfolioResult: PortfolioResult | null;
  selectedPortfolioRunIds: ReadonlyArray<string>;
  hasDiffReport: boolean;
}): WorkflowGuide {
  const workspace = params.workspace.trim();
  const runId = params.runId.trim();
  const inputCount = normalizePathList(params.inputPaths).length;
  const questionReady = Boolean(params.questionPath.trim());
  const runSummary = summarizeRunArtifacts(params.artifacts);
  const hasRun = Boolean(params.artifacts?.manifest);
  const qa = summarizeQa(params.artifacts?.qaReport ?? null);
  const plannerPackCount = runSummary?.plannerPackArtifacts.length ?? 0;
  const diffSelection = validateDiffSelection(params.selectedPortfolioRunIds);
  const portfolioRunCount = params.portfolioResult?.runCount ?? 0;

  const steps: WorkflowGuideStep[] = [
    workflowStep({
      id: "workspace",
      label: "Workspace",
      state: workspace ? "done" : "blocked",
      status: workspace ? "Workspace path is set." : "Pick a workspace folder.",
      actionLabel: workspace ? "Review setup" : "Set workspace",
      anchor: "#workspace",
      blocker: workspace ? null : "Workspace path is required.",
    }),
    workflowStep({
      id: "run",
      label: "Run",
      state: params.busy ? "running" : hasRun ? "done" : workspace ? "ready" : "blocked",
      status: params.busy
        ? "Workflow command is running."
        : hasRun
          ? `Run ${runId || params.artifacts?.runId || "current"} is loaded.`
          : inputCount > 0 && questionReady
            ? "Inputs and question file are ready for a full workflow."
            : "Run the demo first, or add inputs and a question file.",
      actionLabel: hasRun ? "Review outputs" : inputCount > 0 && questionReady ? "Run full workflow" : "Run demo",
      anchor: hasRun ? "#qa" : "#run",
      blocker: workspace ? null : "Workspace path is required before running.",
    }),
    workflowStep({
      id: "qa-artifacts",
      label: "QA + Artifacts",
      state: !hasRun
        ? "blocked"
        : qa.tone === "ready"
          ? "done"
          : qa.tone === "blocked"
            ? "blocked"
            : "ready",
      status: !hasRun
        ? "Run a workflow to create QA and artifacts."
        : qa.tone === "ready"
          ? `Export-ready with ${runSummary?.generatedArtifacts.length ?? 0} output categories.`
          : qa.tone === "blocked"
            ? `Blocked: ${qa.blockers.join(", ") || "QA did not pass."}`
            : "QA report has not been loaded yet.",
      actionLabel: qa.tone === "blocked" ? "Review blockers" : "Review artifacts",
      anchor: "#qa",
      blocker: !hasRun
        ? "Run a workflow first."
        : qa.tone === "blocked"
          ? qa.blockers.join(", ") || "QA did not pass."
          : null,
    }),
    workflowStep({
      id: "planner-pack",
      label: "Planner Pack",
      state: !hasRun
        ? "blocked"
        : params.plannerPackBusy
          ? "running"
          : plannerPackCount > 0
            ? "done"
            : "ready",
      status: !hasRun
        ? "Run a workflow before generating packets."
        : params.plannerPackBusy
          ? "Planner Pack artifact is being generated."
          : plannerPackCount > 0
            ? `${plannerPackCount} Planner Pack artifact(s) detected.`
            : "Generate a planning packet from this run.",
      actionLabel: plannerPackCount > 0 ? "Generate another" : "Generate packet",
      anchor: "#planner-pack",
      blocker: hasRun ? null : "Run a workflow first.",
    }),
    workflowStep({
      id: "chat",
      label: "Chat",
      state: !hasRun
        ? "blocked"
        : params.chatBusy
          ? "running"
          : params.chatTurnCount > 0
            ? "done"
            : "ready",
      status: !hasRun
        ? "Chat needs finished run fact blocks."
        : params.chatBusy
          ? "Grounded chat is answering."
          : params.chatTurnCount > 0
            ? `${params.chatTurnCount} grounded chat turn(s) in this session.`
            : "Ask a grounded question about the run.",
      actionLabel: params.chatTurnCount > 0 ? "Ask another" : "Ask question",
      anchor: "#chat",
      blocker: hasRun ? null : "Run a workflow first.",
    }),
    workflowStep({
      id: "what-if",
      label: "What-if",
      state: !hasRun
        ? "blocked"
        : params.whatIfBusy
          ? "running"
          : params.hasWhatIfResult
            ? "done"
            : "ready",
      status: !hasRun
        ? "What-if needs a finished baseline run."
        : params.whatIfBusy
          ? "What-if run is being created."
          : params.hasWhatIfResult
            ? "What-if run was created in this session."
            : "Derive an alternative run from this baseline.",
      actionLabel: params.hasWhatIfResult ? "Create another" : "Create what-if",
      anchor: "#what-if",
      blocker: hasRun ? null : "Run a workflow first.",
    }),
    workflowStep({
      id: "portfolio-diff",
      label: "Portfolio + Diff",
      state: !workspace
        ? "blocked"
        : params.portfolioBusy
          ? "running"
          : params.hasDiffReport
            ? "done"
            : diffSelection.ok
              ? "ready"
              : params.portfolioResult
                ? portfolioRunCount >= 2
                  ? "optional"
                  : "done"
                : "ready",
      status: !workspace
        ? "Pick a workspace before loading portfolio."
        : params.portfolioBusy
          ? "Portfolio command is running."
          : params.hasDiffReport
            ? "Diff report was written in this session."
            : diffSelection.ok
              ? `Ready to diff ${diffSelection.runA} and ${diffSelection.runB}.`
              : params.portfolioResult
                ? portfolioRunCount >= 2
                  ? "Pick exactly two runs to diff."
                  : "Portfolio is loaded; create another run to diff."
                : "Refresh the workspace portfolio.",
      actionLabel: params.hasDiffReport
        ? "Review portfolio"
        : diffSelection.ok
          ? "Diff selected"
          : params.portfolioResult
            ? "Review portfolio"
            : "Refresh portfolio",
      anchor: "#portfolio",
      blocker: workspace ? null : "Workspace path is required.",
    }),
  ];

  const current =
    steps.find((step) => step.state === "running") ??
    steps.find((step) => step.state === "blocked" || step.state === "ready") ??
    steps.find((step) => step.state === "optional") ??
    null;

  return {
    steps,
    currentStepId: current?.id ?? null,
    nextActionLabel: current?.actionLabel ?? null,
    nextActionAnchor: current?.anchor ?? null,
  };
}

export function validatePlannerPackForm(params: {
  workspace: string;
  runId: string;
  kind: string;
  cycleYear: string;
  analysisYear: string;
}): PlannerPackValidation {
  const workspace = params.workspace.trim();
  const runId = params.runId.trim();
  const kind = params.kind as PlannerPackKind;
  if (!workspace) return { ok: false, error: "Workspace is required." };
  if (!runId) return { ok: false, error: "Run ID is required." };
  if (!PLANNER_PACK_SPECS.some((spec) => spec.kind === kind)) {
    return { ok: false, error: "Pick a Planner Pack artifact." };
  }

  let cycleYear: number | null = null;
  if (kind === "hsip") {
    cycleYear = Number(params.cycleYear.trim());
    if (!Number.isInteger(cycleYear) || cycleYear < 2000 || cycleYear > 2100) {
      return { ok: false, error: "HSIP cycle year must be a four-digit year." };
    }
  }

  let analysisYear: number | null = null;
  if (kind === "cmaq") {
    analysisYear = Number(params.analysisYear.trim());
    if (!Number.isInteger(analysisYear) || analysisYear < 2000 || analysisYear > 2100) {
      return { ok: false, error: "CMAQ analysis year must be a four-digit year." };
    }
  }

  return { ok: true, payload: { workspace, runId, kind, cycleYear, analysisYear } };
}

export function buildPlannerPackArgs(payload: PlannerPackSubmitPayload): string[] {
  const args = [
    "planner-pack",
    payload.kind,
    "--workspace",
    payload.workspace,
    "--run-id",
    payload.runId,
    "--json",
  ];
  if (payload.kind === "hsip" && payload.cycleYear !== null) {
    args.push("--cycle-year", String(payload.cycleYear));
  }
  if (payload.kind === "cmaq" && payload.analysisYear !== null) {
    args.push("--analysis-year", String(payload.analysisYear));
  }
  return args;
}

export function artifactBasename(path: string): string {
  const parts = path.split(/[/\\]/u).filter(Boolean);
  return parts.at(-1) ?? path;
}

export function isPreviewableArtifact(path: string): boolean {
  const lower = artifactBasename(path).toLowerCase();
  const dot = lower.lastIndexOf(".");
  if (dot < 0) {
    return false;
  }
  return PREVIEWABLE_ARTIFACT_EXTENSIONS.has(lower.slice(dot));
}

const FRIENDLY_ERROR_PATTERNS: ReadonlyArray<{ pattern: RegExp; message: string }> = [
  {
    pattern: /workspace is required/i,
    message: "Pick a workspace folder first. This is where ClawModeler stores your project files.",
  },
  {
    pattern: /no such file or directory|cannot find the (file|path)/i,
    message: "One of the paths doesn't exist. Double-check your workspace and input paths.",
  },
  {
    pattern: /permission denied/i,
    message:
      "ClawModeler can't read or write that location. Check folder permissions or pick another path.",
  },
  {
    pattern: /no module named ['"]?clawmodeler_engine['"]?/i,
    message:
      "The ClawModeler engine isn't installed. Run pip install -e . from the repo root, then retry.",
  },
  {
    pattern: /python3?: ?command not found|python3? is not recognized/i,
    message: "Python 3 isn't on PATH. Install Python 3.10+ and reopen ClawModeler.",
  },
  {
    pattern: /duckdb/i,
    message: "DuckDB isn't installed. Click Doctor to see which tools are missing.",
  },
  {
    pattern: /question\.json/i,
    message:
      "ClawModeler needs a question.json file describing what to analyze. Check the path you entered.",
  },
  {
    pattern: /method not allowed/i,
    message: "Internal routing error. Reload the window and try again.",
  },
];

export function friendlyError(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return "Something went wrong. Open Doctor for details.";
  }
  for (const { pattern, message } of FRIENDLY_ERROR_PATTERNS) {
    if (pattern.test(trimmed)) {
      return message;
    }
  }
  const firstLine = trimmed.split(/\r?\n/u).at(0) ?? trimmed;
  return firstLine.length > 220 ? `${firstLine.slice(0, 217)}...` : firstLine;
}

export type ChatTurn = {
  turnId: number;
  createdAt: string;
  userMessage: string;
  provider: string;
  model: string;
  text: string;
  rawText: string;
  isFullyGrounded: boolean;
  ungroundedSentenceCount: number;
  citedFactIds: string[];
  unknownFactIds: string[];
};

export function parseChatTurn(payload: unknown): ChatTurn | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const p = payload as Record<string, unknown>;
  const turnId = typeof p.turn_id === "number" ? p.turn_id : Number(p.turn_id);
  if (!Number.isFinite(turnId)) {
    return null;
  }
  const cited = Array.isArray(p.cited_fact_ids)
    ? p.cited_fact_ids.map((value) => String(value)).filter(Boolean)
    : [];
  const unknown = Array.isArray(p.unknown_fact_ids)
    ? p.unknown_fact_ids.map((value) => String(value)).filter(Boolean)
    : [];
  return {
    turnId,
    createdAt: typeof p.created_at === "string" ? p.created_at : "",
    userMessage: typeof p.user_message === "string" ? p.user_message : "",
    provider: typeof p.provider === "string" ? p.provider : "",
    model: typeof p.model === "string" ? p.model : "",
    text: typeof p.text === "string" ? p.text : "",
    rawText: typeof p.raw_text === "string" ? p.raw_text : "",
    isFullyGrounded: p.is_fully_grounded === true,
    ungroundedSentenceCount:
      typeof p.ungrounded_sentence_count === "number"
        ? p.ungrounded_sentence_count
        : Number(p.ungrounded_sentence_count) || 0,
    citedFactIds: cited,
    unknownFactIds: unknown,
  };
}

const FACT_CITATION_RE = /\[fact:([A-Za-z0-9_.-]+)\]/gu;

export type ChatSegment =
  | { kind: "text"; value: string }
  | { kind: "chip"; factId: string };

export function segmentChatText(text: string): ChatSegment[] {
  if (!text) {
    return [];
  }
  const segments: ChatSegment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(FACT_CITATION_RE)) {
    const matchIndex = match.index ?? 0;
    if (matchIndex > cursor) {
      segments.push({ kind: "text", value: text.slice(cursor, matchIndex) });
    }
    segments.push({ kind: "chip", factId: match[1] });
    cursor = matchIndex + match[0].length;
  }
  if (cursor < text.length) {
    segments.push({ kind: "text", value: text.slice(cursor) });
  }
  return segments;
}

export function chatTurnBadge(turn: ChatTurn): string {
  if (turn.unknownFactIds.length > 0) {
    return "unknown-ids";
  }
  if (!turn.isFullyGrounded || turn.ungroundedSentenceCount > 0) {
    return "partial";
  }
  return "grounded";
}

export type WhatIfWeights = {
  safety: number;
  equity: number;
  climate: number;
  feasibility: number;
};

export const DEFAULT_WHAT_IF_WEIGHTS: WhatIfWeights = {
  safety: 0.3,
  equity: 0.25,
  climate: 0.25,
  feasibility: 0.2,
};

export const WHAT_IF_WEIGHT_EPSILON = 1e-6;

export function whatIfWeightSum(weights: WhatIfWeights): number {
  return weights.safety + weights.equity + weights.climate + weights.feasibility;
}

export function isValidWhatIfWeights(weights: WhatIfWeights): boolean {
  const values = [weights.safety, weights.equity, weights.climate, weights.feasibility];
  if (values.some((v) => !Number.isFinite(v) || v < 0 || v > 1)) {
    return false;
  }
  return Math.abs(whatIfWeightSum(weights) - 1) < WHAT_IF_WEIGHT_EPSILON;
}

export function rebalanceWhatIfWeights(
  weights: WhatIfWeights,
  changedKey: keyof WhatIfWeights,
  newValue: number,
): WhatIfWeights {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(newValue) ? newValue : 0));
  const next: WhatIfWeights = { ...weights, [changedKey]: clamped };
  const otherKeys = (["safety", "equity", "climate", "feasibility"] as const).filter(
    (key) => key !== changedKey,
  );
  const remaining = 1 - clamped;
  const otherSum = otherKeys.reduce((acc, key) => acc + weights[key], 0);
  if (otherSum <= WHAT_IF_WEIGHT_EPSILON) {
    const share = remaining / otherKeys.length;
    for (const key of otherKeys) {
      next[key] = share;
    }
  } else {
    for (const key of otherKeys) {
      next[key] = (weights[key] / otherSum) * remaining;
    }
  }
  return next;
}

export type WhatIfSubmitPayload = {
  workspace: string;
  baseRunId: string;
  newRunId: string;
  weights: WhatIfWeights | null;
  referenceVmtPerCapita: number | null;
  thresholdPct: number | null;
  includeProjects: string[];
  excludeProjects: string[];
  sensitivityFloor: "LOW" | "MEDIUM" | "HIGH" | null;
};

export type WhatIfValidation =
  | { ok: true; payload: WhatIfSubmitPayload }
  | { ok: false; error: string };

export function parseProjectIdList(input: string): string[] {
  return input
    .split(/\r?\n|,/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function validateWhatIfForm(params: {
  workspace: string;
  baseRunId: string;
  newRunId: string;
  weightsEnabled: boolean;
  weights: WhatIfWeights;
  referenceVmtPerCapita: string;
  thresholdPct: string;
  includeProjects: string;
  excludeProjects: string;
  sensitivityFloor: string;
}): WhatIfValidation {
  const workspace = params.workspace.trim();
  const baseRunId = params.baseRunId.trim();
  const newRunId = params.newRunId.trim();
  if (!workspace) return { ok: false, error: "Workspace is required." };
  if (!baseRunId) return { ok: false, error: "Base run ID is required." };
  if (!newRunId) return { ok: false, error: "New run ID is required." };
  if (baseRunId === newRunId)
    return { ok: false, error: "New run ID must differ from base run ID." };

  const weights = params.weightsEnabled ? params.weights : null;
  if (weights && !isValidWhatIfWeights(weights)) {
    return {
      ok: false,
      error: `Weights must each be between 0 and 1 and sum to 1 (current sum ${whatIfWeightSum(params.weights).toFixed(3)}).`,
    };
  }

  const include = parseProjectIdList(params.includeProjects);
  const exclude = parseProjectIdList(params.excludeProjects);
  const overlap = include.filter((id) => exclude.includes(id));
  if (overlap.length > 0) {
    return {
      ok: false,
      error: `Project id(s) cannot appear in both include and exclude: ${overlap.join(", ")}.`,
    };
  }

  const refVmtRaw = params.referenceVmtPerCapita.trim();
  let referenceVmtPerCapita: number | null = null;
  if (refVmtRaw) {
    const parsed = Number(refVmtRaw);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return { ok: false, error: "Reference VMT/capita must be a positive number." };
    }
    referenceVmtPerCapita = parsed;
  }

  const thresholdRaw = params.thresholdPct.trim();
  let thresholdPct: number | null = null;
  if (thresholdRaw) {
    const parsed = Number(thresholdRaw);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed >= 1) {
      return {
        ok: false,
        error: "CEQA threshold must be a fraction strictly between 0 and 1 (e.g., 0.15).",
      };
    }
    thresholdPct = parsed;
  }

  const floorRaw = params.sensitivityFloor.trim().toUpperCase();
  let sensitivityFloor: WhatIfSubmitPayload["sensitivityFloor"] = null;
  if (floorRaw) {
    if (floorRaw !== "LOW" && floorRaw !== "MEDIUM" && floorRaw !== "HIGH") {
      return {
        ok: false,
        error: "Sensitivity floor must be LOW, MEDIUM, or HIGH.",
      };
    }
    sensitivityFloor = floorRaw;
  }

  if (
    !weights &&
    referenceVmtPerCapita === null &&
    thresholdPct === null &&
    include.length === 0 &&
    exclude.length === 0 &&
    sensitivityFloor === null
  ) {
    return { ok: false, error: "Supply at least one override." };
  }

  return {
    ok: true,
    payload: {
      workspace,
      baseRunId,
      newRunId,
      weights,
      referenceVmtPerCapita,
      thresholdPct,
      includeProjects: include,
      excludeProjects: exclude,
      sensitivityFloor,
    },
  };
}

export type PortfolioRun = {
  runId: string;
  engineVersion: string | null;
  createdAt: string | null;
  baseRunId: string | null;
  scenarioCount: number;
  projectCount: number;
  meanTotalScore: number | null;
  topProjectId: string | null;
  topProjectName: string | null;
  topProjectScore: number | null;
  vmtFlaggedCount: number;
  dacShare: number | null;
  factBlockCount: number;
  exportReady: boolean;
  qaBlockers: string[];
  plannerPackArtifacts: string[];
  hasWhatIfOverrides: boolean;
};

export type PortfolioSummary = {
  runCount: number;
  exportReadyCount: number;
  meanPortfolioScore: number | null;
  totalVmtFlaggedCount: number;
  meanDacShare: number | null;
  engineVersions: string[];
  lineageEdges: Array<{ from: string; to: string }>;
};

export type PortfolioResult = {
  workspacePath: string;
  runCount: number;
  runs: PortfolioRun[];
  summary: PortfolioSummary | null;
  generatedAt: string;
  csvPath: string | null;
  jsonPath: string | null;
  reportPath: string | null;
  factBlocksPath: string | null;
  factBlockCount: number;
};

function asString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asInt(value: unknown, fallback = 0): number {
  const n = asNumber(value);
  return n === null ? fallback : Math.trunc(n);
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((v) => String(v)).filter(Boolean) : [];
}

export function parsePortfolioPayload(payload: unknown): PortfolioResult | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as Record<string, unknown>;
  const runCount = asInt(p.run_count);
  const rawRuns = Array.isArray(p.runs) ? p.runs : [];
  const runs: PortfolioRun[] = rawRuns.map((item) => {
    const r = (item || {}) as Record<string, unknown>;
    return {
      runId: typeof r.run_id === "string" ? r.run_id : "",
      engineVersion: asString(r.engine_version),
      createdAt: asString(r.created_at),
      baseRunId: asString(r.base_run_id),
      scenarioCount: asInt(r.scenario_count),
      projectCount: asInt(r.project_count),
      meanTotalScore: asNumber(r.mean_total_score),
      topProjectId: asString(r.top_project_id),
      topProjectName: asString(r.top_project_name),
      topProjectScore: asNumber(r.top_project_score),
      vmtFlaggedCount: asInt(r.vmt_flagged_count),
      dacShare: asNumber(r.dac_share),
      factBlockCount: asInt(r.fact_block_count),
      exportReady: r.export_ready === true,
      qaBlockers: asStringArray(r.qa_blockers),
      plannerPackArtifacts: asStringArray(r.planner_pack_artifacts),
      hasWhatIfOverrides: r.has_what_if_overrides === true,
    };
  });
  let summary: PortfolioSummary | null = null;
  if (p.summary && typeof p.summary === "object") {
    const s = p.summary as Record<string, unknown>;
    const edges = Array.isArray(s.lineage_edges) ? s.lineage_edges : [];
    summary = {
      runCount: asInt(s.run_count),
      exportReadyCount: asInt(s.export_ready_count),
      meanPortfolioScore: asNumber(s.mean_portfolio_score),
      totalVmtFlaggedCount: asInt(s.total_vmt_flagged_count),
      meanDacShare: asNumber(s.mean_dac_share),
      engineVersions: asStringArray(s.engine_versions),
      lineageEdges: edges.map((edge) => {
        const e = (edge || {}) as Record<string, unknown>;
        return {
          from: typeof e.from === "string" ? e.from : "",
          to: typeof e.to === "string" ? e.to : "",
        };
      }),
    };
  }
  return {
    workspacePath: typeof p.workspace_path === "string" ? p.workspace_path : "",
    runCount,
    runs,
    summary,
    generatedAt: typeof p.generated_at === "string" ? p.generated_at : "",
    csvPath: asString(p.csv_path),
    jsonPath: asString(p.json_path),
    reportPath: asString(p.report_path),
    factBlocksPath: asString(p.fact_blocks_path),
    factBlockCount: asInt(p.fact_block_count),
  };
}

export type PortfolioSortKey =
  | "runId"
  | "createdAt"
  | "engineVersion"
  | "baseRunId"
  | "projectCount"
  | "meanTotalScore"
  | "vmtFlaggedCount"
  | "dacShare"
  | "exportReady";

export type PortfolioSortDirection = "asc" | "desc";

function portfolioSortValue(run: PortfolioRun, key: PortfolioSortKey): unknown {
  switch (key) {
    case "runId":
      return run.runId;
    case "createdAt":
      return run.createdAt ?? "";
    case "engineVersion":
      return run.engineVersion ?? "";
    case "baseRunId":
      return run.baseRunId ?? "";
    case "projectCount":
      return run.projectCount;
    case "meanTotalScore":
      return run.meanTotalScore;
    case "vmtFlaggedCount":
      return run.vmtFlaggedCount;
    case "dacShare":
      return run.dacShare;
    case "exportReady":
      return run.exportReady ? 1 : 0;
    default:
      return null;
  }
}

export function sortPortfolioRuns(
  runs: PortfolioRun[],
  key: PortfolioSortKey,
  direction: PortfolioSortDirection,
): PortfolioRun[] {
  const copy = runs.slice();
  const dir = direction === "asc" ? 1 : -1;
  copy.sort((a, b) => {
    const av = portfolioSortValue(a, key);
    const bv = portfolioSortValue(b, key);
    // Nulls always fall to the end regardless of direction.
    const aNull = av === null || av === undefined || av === "";
    const bNull = bv === null || bv === undefined || bv === "";
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    if (typeof av === "number" && typeof bv === "number") {
      return (av - bv) * dir;
    }
    return String(av).localeCompare(String(bv)) * dir;
  });
  return copy;
}

export function toggleRunSelection(
  selected: ReadonlyArray<string>,
  runId: string,
  limit = 2,
): string[] {
  const set = new Set(selected);
  if (set.has(runId)) {
    set.delete(runId);
  } else {
    set.add(runId);
  }
  const next = Array.from(set);
  if (next.length <= limit) return next;
  // Drop the oldest (front of the array) to keep the limit.
  return next.slice(next.length - limit);
}

export type DiffSelectionValidation =
  | { ok: true; runA: string; runB: string }
  | { ok: false; error: string };

export function validateDiffSelection(
  selected: ReadonlyArray<string>,
): DiffSelectionValidation {
  if (selected.length !== 2) {
    return { ok: false, error: "Pick exactly two runs to diff." };
  }
  const [runA, runB] = selected;
  if (!runA || !runB) {
    return { ok: false, error: "Pick exactly two runs to diff." };
  }
  if (runA === runB) {
    return { ok: false, error: "Pick two different runs." };
  }
  return { ok: true, runA, runB };
}

export function buildDiffArgs(params: {
  workspace: string;
  runA: string;
  runB: string;
}): string[] {
  return [
    "diff",
    "--workspace",
    params.workspace,
    "--run-a",
    params.runA,
    "--run-b",
    params.runB,
    "--json",
  ];
}

export function formatDacShare(share: number | null): string {
  if (share === null) return "—";
  return `${(share * 100).toFixed(1)}%`;
}

export function formatMeanScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(3);
}

export function deriveQuestionSavePath(workspace: string, currentQuestion: string): string {
  const trimmedQuestion = currentQuestion.trim();
  if (trimmedQuestion) {
    return trimmedQuestion;
  }
  const trimmedWorkspace = workspace.trim();
  if (!trimmedWorkspace) {
    return "question.json";
  }
  const separator = trimmedWorkspace.includes("\\") && !trimmedWorkspace.includes("/") ? "\\" : "/";
  const normalized = trimmedWorkspace.replace(/[/\\]+$/u, "");
  return `${normalized}${separator}question.json`;
}
