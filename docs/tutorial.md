# ClawModeler in 20 minutes

A walkthrough for a planner who has never opened ClawModeler before. You'll install the desktop app, run a complete sample analysis, inspect the QA-gated outputs, export a report to Word, and open it. No command-line work is required to complete this tutorial.

> **This is a screening workflow.** Every output you produce here is labeled screening-level. ClawModeler is not a replacement for calibrated regional models, detailed traffic operations analysis, or project-specific engineering forecasts. See [What ClawModeler is not](#what-clawmodeler-is-not) at the end.

## What you'll need

- A computer running Linux, macOS (Apple Silicon), or Windows 10/11. Intel Macs can currently build from source only — no pre-built installer.
- About 20 minutes.
- Microsoft Word or any `.docx` reader (LibreOffice Writer and Google Docs both work) for the final step.
- No data — the tutorial uses the built-in Run Demo path.

## Step 1 — Download the installer (2 minutes)

Open the [ClawModeler releases page](https://github.com/nfredmond/clawmodeler/releases/latest) and download the file that matches your OS:

| Platform | File |
|---|---|
| Linux (any distro) | `ClawModeler_<version>_amd64.AppImage` |
| Debian / Ubuntu | `ClawModeler_<version>_amd64.deb` |
| Fedora / RHEL | `ClawModeler-<version>-1.x86_64.rpm` |
| macOS (M1/M2/M3/M4) | `ClawModeler_<version>_aarch64.dmg` |
| Windows 10/11 | `ClawModeler_<version>_x64-setup.exe` (or the MSI) |

_Screenshot: releases page with installers listed. (To be captured during v1.0.0 manual verification — see `docs/release.md`.)_

## Step 2 — First launch (1 minute)

ClawModeler ships **unsigned** — Apple and Microsoft code-signing certificates cost several hundred dollars a year each and keeping the tool free for small agencies is the point. The first launch needs a one-time bypass:

- **Linux AppImage:** make the file executable (right-click → Properties → Permissions → Allow executing as program, or `chmod +x ClawModeler*.AppImage` in a terminal), then double-click.
- **macOS:** right-click `ClawModeler.app` → **Open** → **Open**. Gatekeeper remembers the decision; you won't be asked again.
- **Windows:** when SmartScreen appears, click **More info** → **Run anyway**.

_Screenshot: each OS's first-launch bypass dialog. (To be captured during v1.0.0 manual verification.)_

## Step 3 — Run the demo (3 minutes)

When ClawModeler opens, you'll see a panel labeled **Workflow** with a row of buttons.

Click **Run Demo**.

ClawModeler will:

1. Create a sample project folder on disk.
2. Stage three example zones, a small socio table, a project list, a tiny network, and a GTFS feed.
3. Run a full workflow: intake validation, scenario transforms, accessibility analysis, VMT and CO₂ screening, GTFS route metrics, project scoring, and bridge-package preparation for SUMO, MATSim, UrbanSim, DTALite, and TBEST.
4. Generate a QA report, fact-blocks, and a technical report.

You'll watch the status banner cycle through each step. The whole run finishes in under a minute on a modern laptop.

_Screenshot: Workflow panel with Run Demo button highlighted, status banner showing progress. (To be captured during v1.0.0 manual verification.)_

## Step 4 — Inspect the outputs (5 minutes)

Scroll down to the **Results** panel. You'll see:

- **QA export readiness** — green if QA passes, amber if not. The demo always passes.
- **Run summary** — one-line facts: scenarios that ran, fact-block count, bridge readiness.
- **Artifacts** — every file the run produced, grouped by category (tables, figures, maps, bridges, reports).

Click any artifact to preview it in-app. Text and JSON files render inline. Figures open in your system image viewer.

**What to look for:**

1. **`qa_report.json`** — the gate. It records why export was allowed (or blocked). Every ClawModeler export passes through this check.
2. **`fact_blocks.jsonl`** — one grounded claim per line. Each numeric statement in the written report traces to one of these. If you delete all fact-blocks, the next export gets blocked.
3. **`manifest.json`** — a full reproducibility record: input hashes, methods chosen, scenarios, assumptions. Paired with the input files, it reconstructs the run exactly.
4. **Figures** — VMT by scenario, accessibility deltas, project score distribution. All generated from the run data, not from templates.

_Screenshot: Results panel showing QA ready badge, artifact list, and a preview of qa_report.json. (To be captured during v1.0.0 manual verification.)_

A full set of real demo artifacts — identical to what you're looking at — is also committed in [`docs/samples/rural-demo/`](samples/rural-demo/). Compare to confirm your run produced the expected outputs.

## Step 5 — Export to Word (2 minutes)

In the **Workflow** panel, find the **Regenerate Report** button. Next to it is a **Format** dropdown. Change it to **DOCX**, then click **Regenerate Report**.

ClawModeler writes the Word document to `<your-project-folder>/reports/<run-id>_report.docx`.

_Screenshot: Format selector dropdown expanded showing MD, PDF, DOCX; Regenerate Report button. (To be captured during v1.0.0 manual verification.)_

Open the generated file in Word (or LibreOffice Writer or Google Docs). You should see:

- A title, generated timestamp, engine version, and QA status on the first page.
- A Methods section listing every engine step that contributed.
- A Scenarios table with population and jobs multipliers per scenario.
- An Evidence table with every fact-block — each claim is traceable.
- Figures and maps.
- An Assumptions and limitations section.
- A QA report block.
- A Bridge Packages table.

This is what a planner would hand to an agency, attach to a grant application, or drop into an RTP chapter.

## Step 6 — Generate a CEQA VMT Planner Pack memo (3 minutes)

The technical report is one output. Planner Pack artifacts are the other. They're formatted for specific regulatory contexts: CEQA §15064.3 VMT significance, Caltrans LAPM exhibits, RTP chapters, equity lens, ATP packets, HSIP, CMAQ, STIP.

Scroll to the **Planner Pack** panel.

1. Pick a kind. For this tutorial, pick **CEQA VMT**.
2. Leave the defaults (residential project type, regional reference baseline).
3. Click **Generate Planner Pack**.

ClawModeler produces a CEQA VMT memo under `reports/<run-id>_ceqa_vmt.md`, adds supporting tables under `runs/<run-id>/outputs/tables/`, and appends a new fact-block.

Open the memo. It documents the threshold, applies 15% below the reference per OPR's Technical Advisory, records each scenario's determination, and cites the fact-block that backs each claim.

_Screenshot: Planner Pack panel with CEQA VMT selected, output summary showing memo path. (To be captured during v1.0.0 manual verification.)_

## Step 7 — You're done (0 minutes)

That's the full workflow. Everything from this point on is iteration: change the question, re-run, compare runs with the diff tool, try a what-if override, or export to a bridge package for a detailed engine.

---

## Bring your own data

When you're ready to run ClawModeler against a real project, you need at minimum:

- **`zones.geojson`** — your study-area zones as GeoJSON polygons. Each feature must have `properties.zone_id`.
- **`socio.csv`** — population and jobs per zone. Columns: `zone_id`, `population`, `jobs`.
- **`projects.csv`** — your candidate project list. Columns: `project_id`, `name`, `safety`, `equity`, `climate`, `feasibility` (each 0–100).

That's enough to run end-to-end and produce a screening-level report.

Optional inputs unlock better results:

- **`network_edges.csv`** — zone-to-zone travel times (`from_zone_id`, `to_zone_id`, `minutes`). Replaces Euclidean proxies with real routed accessibility.
- **GTFS ZIP** — any valid GTFS feed. Enables transit route metrics.
- **GraphML network** — an OSMnx-style network stored under `cache/graphs/`. Enables routed accessibility from OSM.

A ready-to-edit starter template is provided under [`docs/samples/starter-template/`](samples/starter-template/) — copy it, replace the placeholder rows with your data, and point the desktop app at your folder.

## What ClawModeler is not

Before you share any output with stakeholders, know the guardrails ClawModeler enforces and the questions it does **not** answer:

- **Not a calibrated regional model.** The accessibility, VMT, and scoring outputs are screening-level proxies by default. ClawModeler explicitly records which methods are proxies and which are engine-backed, and the report labels every screening-level claim as such.
- **Not a traffic operations engine.** Corridor LOS, intersection delay, queuing, signal timing, and ramp metering belong in SUMO, Vissim, Synchro, HCS, or a calibrated microsimulation. ClawModeler prepares a handoff package to SUMO for these, but the package is structurally ready, not forecast-ready.
- **Not a transit ridership model.** Stop-access proxies and GTFS route metrics describe service quality; they don't forecast boardings. For ridership, use a calibrated APC/FTA-methodology model. ClawModeler prepares a TBEST handoff package.
- **Not a land-use allocation model.** Zone population and jobs are inputs. To forecast land-use change, use UrbanSim, PECAS, or a regional land-use model. ClawModeler prepares a UrbanSim handoff package.
- **Not a substitute for qualified review.** AI-assisted narrative and chat features must cite fact-blocks from the run. Client-critical conclusions still require a qualified planner or engineer to review the methodology, the assumptions, and the limitations.

Every ClawModeler export preserves these limits by design: QA blocks the export if fact-blocks are missing or if claims aren't grounded, and the manifest records every assumption. Keep that visibility when you share results.

## Where to next

- **[Sample Planner Pack](samples/rural-demo/)** — the full output set referenced by this tutorial, committed to the repo so you can review it without installing.
- **[Roadmap](roadmap.md)** — what's shipped, what's deferred, and the decision gates for advanced features.
- **[CLI reference](cli.md)** — every `clawmodeler-engine` subcommand, for scripted and automated workflows.
- **[Release notes](../CHANGELOG.md)** — what changed in each version.
- **[GitHub issues](https://github.com/nfredmond/clawmodeler/issues)** — report a bug, ask a question, or suggest a feature.
