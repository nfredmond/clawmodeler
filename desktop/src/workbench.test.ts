import { describe, expect, it } from "vitest";
import {
  artifactBasename,
  buildDiffArgs,
  buildFullWorkflowArgs,
  buildPlannerPackArgs,
  chatTurnBadge,
  countJsonLines,
  DEFAULT_WHAT_IF_WEIGHTS,
  detectPlannerPackArtifacts,
  deriveWorkflowGuide,
  deriveQuestionSavePath,
  formatDacShare,
  formatMeanScore,
  friendlyError,
  isPreviewableArtifact,
  isValidWhatIfWeights,
  manifestOutputCategories,
  manifestOutputPaths,
  normalizePathList,
  normalizeScenarios,
  parseChatTurn,
  parsePortfolioPayload,
  parseProjectIdList,
  rebalanceWhatIfWeights,
  segmentChatText,
  sortPortfolioRuns,
  summarizeRunArtifacts,
  summarizeQa,
  toggleRunSelection,
  validateDiffSelection,
  validatePlannerPackForm,
  validateWhatIfForm,
  whatIfWeightSum,
} from "./workbench.js";

describe("clawmodeler workbench helpers", () => {
  const makeGuide = (overrides: Partial<Parameters<typeof deriveWorkflowGuide>[0]> = {}) =>
    deriveWorkflowGuide({
      workspace: "/tmp/ws",
      runId: "demo",
      inputPaths: "",
      questionPath: "",
      busy: false,
      artifacts: null,
      plannerPackBusy: false,
      chatBusy: false,
      chatTurnCount: 0,
      whatIfBusy: false,
      hasWhatIfResult: false,
      portfolioBusy: false,
      portfolioResult: null,
      selectedPortfolioRunIds: [],
      hasDiffReport: false,
      ...overrides,
    });

  it("normalizes paths from newlines and commas", () => {
    expect(normalizePathList("zones.geojson, socio.csv\nprojects.csv\n")).toEqual([
      "zones.geojson",
      "socio.csv",
      "projects.csv",
    ]);
  });

  it("defaults scenarios to baseline", () => {
    expect(normalizeScenarios("")).toEqual(["baseline"]);
    expect(normalizeScenarios("baseline, build")).toEqual(["baseline", "build"]);
  });

  it("builds the full workflow sidecar args", () => {
    expect(
      buildFullWorkflowArgs({
        workspace: "/tmp/demo",
        inputs: ["zones.geojson", "socio.csv"],
        question: "question.json",
        runId: "demo",
        scenarios: ["baseline"],
        skipBridges: true,
      }),
    ).toEqual([
      "workflow",
      "full",
      "--workspace",
      "/tmp/demo",
      "--inputs",
      "zones.geojson",
      "socio.csv",
      "--question",
      "question.json",
      "--run-id",
      "demo",
      "--scenarios",
      "baseline",
      "--skip-bridges",
    ]);
  });

  it("summarizes QA reports", () => {
    expect(summarizeQa({ export_ready: true, blockers: [] }).tone).toBe("ready");
    expect(summarizeQa({ export_ready: false, blockers: ["manifest_missing"] })).toEqual({
      label: "Export blocked",
      tone: "blocked",
      blockers: ["manifest_missing"],
    });
  });

  it("counts JSONL rows and manifest output categories", () => {
    expect(countJsonLines('{"a":1}\n\n{"b":2}\n')).toBe(2);
    expect(manifestOutputCategories({ outputs: { tables: [], maps: [], bridges: [] } })).toEqual([
      "bridges",
      "maps",
      "tables",
    ]);
  });

  it("normalizes run summary details from workspace artifacts", () => {
    const summary = summarizeRunArtifacts({
      workspace: "/tmp/ws",
      runId: "demo",
      manifest: {
        scenarios: [{ scenario_id: "baseline" }, { scenario_id: "build" }],
        outputs: {
          tables: ["/tmp/ws/runs/demo/outputs/tables/ceqa_vmt.csv"],
          maps: ["/tmp/ws/runs/demo/outputs/maps/access_baseline.html"],
        },
        artifacts: {
          cmaq_overlay_csv: "inputs/missing_cmaq.csv",
        },
        detailed_engine_readiness: {
          engines: {
            sumo: {
              status: "handoff_only",
              status_label: "Handoff only",
              summary: "Bridge package only.",
              missing_readiness_blockers: ["model_year_missing"],
            },
          },
        },
      },
      qaReport: { export_ready: true, blockers: [] },
      workflowReport: {
        artifacts: {
          manifest: "/tmp/ws/runs/demo/manifest.json",
          report: "/tmp/ws/reports/demo_report.md",
        },
        bridges: {
          prepared: [
            {
              bridge: "sumo",
              generated_files: [
                "/tmp/ws/runs/demo/outputs/bridges/sumo/sumo_run_manifest.json",
                "/tmp/ws/runs/demo/outputs/bridges/sumo/network.edg.xml",
              ],
            },
          ],
          skipped: [
            {
              bridge: "tbest",
              required_inputs: ["gtfs_zip"],
              missing_inputs: ["gtfs_zip"],
              reason: "Missing required inputs: gtfs_zip",
            },
          ],
        },
        bridge_validation: {
          export_ready: false,
          detailed_forecast_ready: false,
          blockers: ["sumo_not_ready"],
        },
      },
      reportMarkdown: null,
      files: ["/tmp/ws/runs/demo/outputs/tables/ceqa_vmt.csv"],
      filesTruncated: false,
    });

    expect(summary?.manifestPath).toBe("/tmp/ws/runs/demo/manifest.json");
    expect(summary?.reportPath).toBe("/tmp/ws/reports/demo_report.md");
    expect(summary?.scenarioIds).toEqual(["baseline", "build"]);
    expect(summary?.qaExportReady).toBe(true);
    expect(summary?.bridgeExportReady).toBe(false);
    expect(summary?.detailedForecastReady).toBe(false);
    expect(summary?.detailedForecastStatuses).toEqual([
      {
        bridge: "sumo",
        status: "handoff_only",
        statusLabel: "Handoff only",
        blockers: ["model_year_missing"],
        summary: "Bridge package only.",
      },
    ]);
    expect(summary?.bridgeGeneratedFileCount).toBe(2);
    expect(summary?.bridgeSkippedInputs).toEqual([
      {
        bridge: "tbest",
        requiredInputs: ["gtfs_zip"],
        missingInputs: ["gtfs_zip"],
        reason: "Missing required inputs: gtfs_zip",
      },
    ]);
    expect(summary?.plannerPackArtifacts).toEqual(["ceqa-vmt"]);
    expect(summary?.generatedArtifacts).toEqual([
      { category: "maps", count: 1 },
      { category: "tables", count: 1 },
    ]);
    expect(summary?.missingSidecars).toEqual(["cmaq_overlay_csv: inputs/missing_cmaq.csv"]);
    expect(summary?.warnings).toContain("Bridge blocker: sumo_not_ready");
    expect(summary?.warnings).toContain(
      "Detailed forecast blocker (sumo): model_year_missing",
    );
  });

  it("flattens manifest outputs and detects planner-pack tables", () => {
    const manifest = {
      outputs: {
        tables: [
          { path: "/tmp/ws/runs/demo/outputs/tables/hsip.csv" },
          "/tmp/ws/runs/demo/outputs/tables/project_scores.csv",
        ],
      },
    };
    expect(manifestOutputPaths(manifest)).toContain(
      "/tmp/ws/runs/demo/outputs/tables/hsip.csv",
    );
    expect(detectPlannerPackArtifacts([], manifest)).toEqual(["hsip"]);
  });

  it("derives a guided workflow for a fresh workspace", () => {
    const guide = makeGuide();
    expect(guide.currentStepId).toBe("run");
    expect(guide.nextActionLabel).toBe("Run demo");
    expect(guide.steps.find((step) => step.id === "workspace")?.state).toBe("done");
    expect(guide.steps.find((step) => step.id === "run")?.state).toBe("ready");
    expect(guide.steps.find((step) => step.id === "qa-artifacts")?.state).toBe("blocked");
  });

  it("prefers full workflow when inputs and question are present", () => {
    const guide = makeGuide({
      inputPaths: "zones.geojson\nsocio.csv",
      questionPath: "/tmp/ws/question.json",
    });
    const runStep = guide.steps.find((step) => step.id === "run");
    expect(runStep?.status).toMatch(/full workflow/u);
    expect(runStep?.actionLabel).toBe("Run full workflow");
  });

  it("marks QA, Planner Pack, chat, and what-if readiness after a run", () => {
    const artifacts = {
      workspace: "/tmp/ws",
      runId: "demo",
      manifest: {
        outputs: {
          tables: ["/tmp/ws/runs/demo/outputs/tables/project_scores.csv"],
        },
      },
      qaReport: { export_ready: true, blockers: [] },
      workflowReport: null,
      reportMarkdown: "Report",
      files: ["/tmp/ws/runs/demo/outputs/tables/project_scores.csv"],
      filesTruncated: false,
    };
    const guide = makeGuide({ artifacts });
    expect(guide.currentStepId).toBe("planner-pack");
    expect(guide.steps.find((step) => step.id === "run")?.state).toBe("done");
    expect(guide.steps.find((step) => step.id === "qa-artifacts")?.state).toBe("done");
    expect(guide.steps.find((step) => step.id === "planner-pack")?.state).toBe("ready");
    expect(guide.steps.find((step) => step.id === "chat")?.state).toBe("ready");
    expect(guide.steps.find((step) => step.id === "what-if")?.state).toBe("ready");
  });

  it("surfaces blocked QA and completed Planner Pack coverage in the guide", () => {
    const artifacts = {
      workspace: "/tmp/ws",
      runId: "demo",
      manifest: {
        outputs: {
          tables: ["/tmp/ws/runs/demo/outputs/tables/ceqa_vmt.csv"],
        },
      },
      qaReport: { export_ready: false, blockers: ["fact_blocks_invalid"] },
      workflowReport: null,
      reportMarkdown: null,
      files: ["/tmp/ws/runs/demo/outputs/tables/ceqa_vmt.csv"],
      filesTruncated: false,
    };
    const guide = makeGuide({ artifacts });
    const qaStep = guide.steps.find((step) => step.id === "qa-artifacts");
    const plannerStep = guide.steps.find((step) => step.id === "planner-pack");
    expect(guide.currentStepId).toBe("qa-artifacts");
    expect(qaStep?.state).toBe("blocked");
    expect(qaStep?.blocker).toContain("fact_blocks_invalid");
    expect(plannerStep?.state).toBe("done");
    expect(plannerStep?.status).toMatch(/1 Planner Pack/u);
  });

  it("guides portfolio refresh, run selection, and completed diff states", () => {
    const portfolioResult = {
      workspacePath: "/tmp/ws",
      runCount: 2,
      runs: [],
      summary: null,
      generatedAt: "",
      csvPath: null,
      jsonPath: null,
      reportPath: null,
      factBlocksPath: null,
      factBlockCount: 0,
    };
    const ready = makeGuide({
      portfolioResult,
      selectedPortfolioRunIds: ["demo", "alt"],
    });
    expect(ready.steps.find((step) => step.id === "portfolio-diff")?.state).toBe("ready");
    expect(ready.steps.find((step) => step.id === "portfolio-diff")?.status).toMatch(
      /Ready to diff demo and alt/u,
    );

    const optional = makeGuide({ portfolioResult, selectedPortfolioRunIds: ["demo"] });
    expect(optional.steps.find((step) => step.id === "portfolio-diff")?.state).toBe("optional");

    const done = makeGuide({ portfolioResult, hasDiffReport: true });
    expect(done.steps.find((step) => step.id === "portfolio-diff")?.state).toBe("done");
  });

  it("translates engine errors into planner-friendly language", () => {
    expect(friendlyError("Error: workspace is required")).toMatch(/Pick a workspace folder/u);
    expect(friendlyError("FileNotFoundError: No such file or directory: 'zones.geojson'")).toMatch(
      /doesn't exist/u,
    );
    expect(friendlyError("PermissionError: [Errno 13] Permission denied")).toMatch(
      /can't read or write/u,
    );
    expect(friendlyError("ModuleNotFoundError: No module named 'clawmodeler_engine'")).toMatch(
      /engine isn't installed/u,
    );
    expect(friendlyError("")).toMatch(/Something went wrong/u);
    expect(friendlyError("custom short message")).toBe("custom short message");
    const longLine = "a".repeat(500);
    expect(friendlyError(longLine).length).toBeLessThanOrEqual(220);
  });

  it("parses engine ChatTurn payloads into a typed value", () => {
    const turn = parseChatTurn({
      turn_id: 2,
      created_at: "2026-04-16T00:00:00Z",
      user_message: "how does baseline compare?",
      provider: "ollama",
      model: "phi3:mini",
      raw_text: "Raw. [fact:vmt_1]",
      text: "Grounded. [fact:vmt_1]",
      is_fully_grounded: true,
      ungrounded_sentence_count: 0,
      cited_fact_ids: ["vmt_1"],
      unknown_fact_ids: [],
    });
    expect(turn).not.toBeNull();
    expect(turn?.turnId).toBe(2);
    expect(turn?.citedFactIds).toEqual(["vmt_1"]);
    expect(turn?.isFullyGrounded).toBe(true);
    expect(parseChatTurn(null)).toBeNull();
    expect(parseChatTurn({ turn_id: "not a number" })).toBeNull();
  });

  it("splits chat replies into text and citation chips", () => {
    expect(segmentChatText("Baseline VMT steady. [fact:vmt_1] Access improves. [fact:acc_2]")).toEqual(
      [
        { kind: "text", value: "Baseline VMT steady. " },
        { kind: "chip", factId: "vmt_1" },
        { kind: "text", value: " Access improves. " },
        { kind: "chip", factId: "acc_2" },
      ],
    );
    expect(segmentChatText("")).toEqual([]);
    expect(segmentChatText("No citations here.")).toEqual([{ kind: "text", value: "No citations here." }]);
  });

  it("badges a chat turn by grounding status", () => {
    const base = {
      turnId: 1,
      createdAt: "",
      userMessage: "",
      provider: "",
      model: "",
      text: "",
      rawText: "",
      ungroundedSentenceCount: 0,
      citedFactIds: [],
      unknownFactIds: [],
    };
    expect(chatTurnBadge({ ...base, isFullyGrounded: true })).toBe("grounded");
    expect(chatTurnBadge({ ...base, isFullyGrounded: false, ungroundedSentenceCount: 1 })).toBe(
      "partial",
    );
    expect(chatTurnBadge({ ...base, isFullyGrounded: true, unknownFactIds: ["ghost"] })).toBe(
      "unknown-ids",
    );
  });

  it("derives a sensible default path for the starter question.json save dialog", () => {
    expect(deriveQuestionSavePath("/home/nat/project", "")).toBe("/home/nat/project/question.json");
    expect(deriveQuestionSavePath("/home/nat/project/", "")).toBe(
      "/home/nat/project/question.json",
    );
    expect(deriveQuestionSavePath("C:\\Users\\nat\\project", "")).toBe(
      "C:\\Users\\nat\\project\\question.json",
    );
    expect(deriveQuestionSavePath("/home/nat/project", "/tmp/custom.json")).toBe(
      "/tmp/custom.json",
    );
    expect(deriveQuestionSavePath("", "")).toBe("question.json");
  });

  it("defaults what-if weights to 0.30/0.25/0.25/0.20 summing to 1", () => {
    expect(DEFAULT_WHAT_IF_WEIGHTS).toEqual({
      safety: 0.3,
      equity: 0.25,
      climate: 0.25,
      feasibility: 0.2,
    });
    expect(whatIfWeightSum(DEFAULT_WHAT_IF_WEIGHTS)).toBeCloseTo(1, 9);
    expect(isValidWhatIfWeights(DEFAULT_WHAT_IF_WEIGHTS)).toBe(true);
  });

  it("rebalances remaining weights proportionally to preserve sum=1", () => {
    const next = rebalanceWhatIfWeights(DEFAULT_WHAT_IF_WEIGHTS, "safety", 0.5);
    expect(next.safety).toBeCloseTo(0.5, 9);
    expect(whatIfWeightSum(next)).toBeCloseTo(1, 9);
    expect(isValidWhatIfWeights(next)).toBe(true);
    expect(next.equity).toBeCloseTo(
      (DEFAULT_WHAT_IF_WEIGHTS.equity / 0.7) * 0.5,
      9,
    );
  });

  it("clamps slider values into [0,1] on rebalance", () => {
    const over = rebalanceWhatIfWeights(DEFAULT_WHAT_IF_WEIGHTS, "safety", 5);
    expect(over.safety).toBe(1);
    expect(whatIfWeightSum(over)).toBeCloseTo(1, 9);
    const under = rebalanceWhatIfWeights(DEFAULT_WHAT_IF_WEIGHTS, "safety", -2);
    expect(under.safety).toBe(0);
    expect(whatIfWeightSum(under)).toBeCloseTo(1, 9);
  });

  it("invalid what-if weights fail isValidWhatIfWeights", () => {
    expect(
      isValidWhatIfWeights({ safety: 0.25, equity: 0.25, climate: 0.25, feasibility: 0.2 }),
    ).toBe(false);
    expect(
      isValidWhatIfWeights({ safety: 1.1, equity: 0, climate: 0, feasibility: 0 }),
    ).toBe(false);
    expect(
      isValidWhatIfWeights({ safety: -0.1, equity: 0.4, climate: 0.4, feasibility: 0.3 }),
    ).toBe(false);
  });

  it("validateWhatIfForm rejects sub-unity weight sums when enabled", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "alt",
      weightsEnabled: true,
      weights: { safety: 0.25, equity: 0.25, climate: 0.25, feasibility: 0.2 },
      referenceVmtPerCapita: "",
      thresholdPct: "",
      includeProjects: "",
      excludeProjects: "",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/sum to 1/);
    }
  });

  it("validateWhatIfForm rejects same base/new run id", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "demo",
      weightsEnabled: false,
      weights: DEFAULT_WHAT_IF_WEIGHTS,
      referenceVmtPerCapita: "",
      thresholdPct: "",
      includeProjects: "",
      excludeProjects: "",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/must differ/);
    }
  });

  it("validateWhatIfForm rejects include/exclude overlap", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "alt",
      weightsEnabled: false,
      weights: DEFAULT_WHAT_IF_WEIGHTS,
      referenceVmtPerCapita: "",
      thresholdPct: "",
      includeProjects: "p1, p2",
      excludeProjects: "p2",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/p2/);
    }
  });

  it("validateWhatIfForm rejects empty override set", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "alt",
      weightsEnabled: false,
      weights: DEFAULT_WHAT_IF_WEIGHTS,
      referenceVmtPerCapita: "",
      thresholdPct: "",
      includeProjects: "",
      excludeProjects: "",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/at least one override/);
    }
  });

  it("validateWhatIfForm accepts a valid weight-only override", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "alt",
      weightsEnabled: true,
      weights: { safety: 0.4, equity: 0.3, climate: 0.2, feasibility: 0.1 },
      referenceVmtPerCapita: "",
      thresholdPct: "",
      includeProjects: "",
      excludeProjects: "",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.payload.weights).toEqual({
        safety: 0.4,
        equity: 0.3,
        climate: 0.2,
        feasibility: 0.1,
      });
      expect(res.payload.includeProjects).toEqual([]);
    }
  });

  it("validateWhatIfForm rejects out-of-range CEQA threshold", () => {
    const res = validateWhatIfForm({
      workspace: "/tmp/ws",
      baseRunId: "demo",
      newRunId: "alt",
      weightsEnabled: false,
      weights: DEFAULT_WHAT_IF_WEIGHTS,
      referenceVmtPerCapita: "",
      thresholdPct: "1.5",
      includeProjects: "",
      excludeProjects: "",
      sensitivityFloor: "",
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/fraction/);
    }
  });

  it("parseProjectIdList accepts newlines and commas", () => {
    expect(parseProjectIdList("p1, p2\np3")).toEqual(["p1", "p2", "p3"]);
    expect(parseProjectIdList("")).toEqual([]);
  });

  it("parsePortfolioPayload converts snake_case JSON to typed runs + summary", () => {
    const payload = parsePortfolioPayload({
      workspace_path: "/tmp/ws",
      run_count: 2,
      generated_at: "2026-04-18T00:00:00Z",
      csv_path: "/tmp/ws/portfolio/summary.csv",
      json_path: "/tmp/ws/portfolio/summary.json",
      report_path: "/tmp/ws/reports/portfolio.md",
      fact_blocks_path: "/tmp/ws/portfolio/fact_blocks.jsonl",
      fact_block_count: 3,
      summary: {
        run_count: 2,
        export_ready_count: 1,
        mean_portfolio_score: 0.42,
        total_vmt_flagged_count: 3,
        mean_dac_share: 0.25,
        engine_versions: ["0.8.2"],
        lineage_edges: [{ from: "alpha", to: "alpha-safety" }],
      },
      runs: [
        {
          run_id: "alpha",
          engine_version: "0.8.2",
          created_at: "2026-04-18T00:00:00Z",
          base_run_id: null,
          scenario_count: 2,
          project_count: 12,
          mean_total_score: 0.45,
          top_project_id: "p1",
          top_project_name: "Top",
          top_project_score: 0.9,
          vmt_flagged_count: 2,
          dac_share: 0.25,
          fact_block_count: 10,
          export_ready: true,
          qa_blockers: [],
          planner_pack_artifacts: ["ceqa_vmt", "equity_lens"],
          has_what_if_overrides: false,
        },
      ],
    });
    expect(payload).not.toBeNull();
    expect(payload?.runCount).toBe(2);
    expect(payload?.runs[0]?.runId).toBe("alpha");
    expect(payload?.runs[0]?.meanTotalScore).toBe(0.45);
    expect(payload?.runs[0]?.plannerPackArtifacts).toEqual(["ceqa_vmt", "equity_lens"]);
    expect(payload?.summary?.lineageEdges[0]).toEqual({ from: "alpha", to: "alpha-safety" });
    expect(payload?.csvPath).toBe("/tmp/ws/portfolio/summary.csv");
    expect(parsePortfolioPayload(null)).toBeNull();
  });

  it("sortPortfolioRuns sorts mixed numeric + string columns with nulls last", () => {
    const makeRun = (runId: string, mean: number | null, createdAt: string | null) => ({
      runId,
      engineVersion: "0.8.2",
      createdAt,
      baseRunId: null,
      scenarioCount: 1,
      projectCount: 1,
      meanTotalScore: mean,
      topProjectId: null,
      topProjectName: null,
      topProjectScore: null,
      vmtFlaggedCount: 0,
      dacShare: null,
      factBlockCount: 0,
      exportReady: false,
      qaBlockers: [],
      plannerPackArtifacts: [],
      hasWhatIfOverrides: false,
    });
    const runs = [
      makeRun("bravo", null, "2026-04-18T00:00:00Z"),
      makeRun("alpha", 0.5, "2026-04-17T00:00:00Z"),
      makeRun("charlie", 0.9, "2026-04-19T00:00:00Z"),
    ];
    const byScoreDesc = sortPortfolioRuns(runs, "meanTotalScore", "desc");
    expect(byScoreDesc.map((r) => r.runId)).toEqual(["charlie", "alpha", "bravo"]);
    const byCreatedAsc = sortPortfolioRuns(runs, "createdAt", "asc");
    expect(byCreatedAsc.map((r) => r.runId)).toEqual(["alpha", "bravo", "charlie"]);
    const byRunIdAsc = sortPortfolioRuns(runs, "runId", "asc");
    expect(byRunIdAsc.map((r) => r.runId)).toEqual(["alpha", "bravo", "charlie"]);
  });

  it("toggleRunSelection caps the selection at a 2-run ceiling", () => {
    expect(toggleRunSelection([], "alpha")).toEqual(["alpha"]);
    expect(toggleRunSelection(["alpha"], "alpha")).toEqual([]);
    expect(toggleRunSelection(["alpha"], "bravo")).toEqual(["alpha", "bravo"]);
    const capped = toggleRunSelection(["alpha", "bravo"], "charlie");
    expect(capped.length).toBe(2);
    expect(capped).toContain("charlie");
  });

  it("validateDiffSelection requires exactly two distinct runs", () => {
    expect(validateDiffSelection([])).toEqual({
      ok: false,
      error: "Pick exactly two runs to diff.",
    });
    expect(validateDiffSelection(["alpha"])).toEqual({
      ok: false,
      error: "Pick exactly two runs to diff.",
    });
    expect(validateDiffSelection(["alpha", "alpha"])).toEqual({
      ok: false,
      error: "Pick two different runs.",
    });
    expect(validateDiffSelection(["alpha", "bravo"])).toEqual({
      ok: true,
      runA: "alpha",
      runB: "bravo",
    });
  });

  it("buildDiffArgs produces the diff CLI args the Tauri bridge expects", () => {
    expect(buildDiffArgs({ workspace: "/tmp/ws", runA: "alpha", runB: "bravo" })).toEqual([
      "diff",
      "--workspace",
      "/tmp/ws",
      "--run-a",
      "alpha",
      "--run-b",
      "bravo",
      "--json",
    ]);
  });

  it("validates and builds Planner Pack args", () => {
    expect(
      buildPlannerPackArgs({
        workspace: "/tmp/ws",
        runId: "demo",
        kind: "ceqa-vmt",
        cycleYear: null,
        analysisYear: null,
      }),
    ).toEqual([
      "planner-pack",
      "ceqa-vmt",
      "--workspace",
      "/tmp/ws",
      "--run-id",
      "demo",
      "--json",
    ]);
    expect(
      buildPlannerPackArgs({
        workspace: "/tmp/ws",
        runId: "demo",
        kind: "hsip",
        cycleYear: 2027,
        analysisYear: null,
      }),
    ).toContain("--cycle-year");
    expect(
      buildPlannerPackArgs({
        workspace: "/tmp/ws",
        runId: "demo",
        kind: "cmaq",
        cycleYear: null,
        analysisYear: 2028,
      }),
    ).toContain("--analysis-year");

    expect(
      validatePlannerPackForm({
        workspace: "/tmp/ws",
        runId: "demo",
        kind: "cmaq",
        cycleYear: "",
        analysisYear: "",
      }).ok,
    ).toBe(false);
    const valid = validatePlannerPackForm({
      workspace: "/tmp/ws",
      runId: "demo",
      kind: "hsip",
      cycleYear: "2027",
      analysisYear: "",
    });
    expect(valid.ok).toBe(true);
  });

  it("formatMeanScore/formatDacShare render null as em-dash", () => {
    expect(formatMeanScore(null)).toBe("—");
    expect(formatMeanScore(0.4567)).toBe("0.457");
    expect(formatDacShare(null)).toBe("—");
    expect(formatDacShare(0.236)).toBe("23.6%");
  });

  it("detects previewable text artifacts by extension", () => {
    expect(artifactBasename("/tmp/ws/reports/demo_report.md")).toBe("demo_report.md");
    expect(artifactBasename("C:\\tmp\\demo\\manifest.json")).toBe("manifest.json");
    expect(isPreviewableArtifact("/tmp/ws/runs/demo/manifest.json")).toBe(true);
    expect(isPreviewableArtifact("/tmp/ws/runs/demo/outputs/tables/project_scores.csv")).toBe(
      true,
    );
    expect(isPreviewableArtifact("/tmp/ws/runs/demo/outputs/figures/vmt.png")).toBe(false);
  });
});
