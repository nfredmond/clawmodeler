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
  if (params.skipBridges) {
    args.push("--skip-bridges");
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
