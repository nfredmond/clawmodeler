import { describe, expect, it } from "vitest";
import {
  buildFullWorkflowArgs,
  chatTurnBadge,
  countJsonLines,
  deriveQuestionSavePath,
  friendlyError,
  manifestOutputCategories,
  normalizePathList,
  normalizeScenarios,
  parseChatTurn,
  segmentChatText,
  summarizeQa,
} from "./workbench.js";

describe("clawmodeler workbench helpers", () => {
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
});
