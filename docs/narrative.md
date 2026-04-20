# ClawModeler — Agent Onboarding Narrative

*Written to bring a fresh AI agent up to speed with no prior context. Reading order
assumes you have already cloned the repo but have never seen the product, the team,
or the surrounding OpenClaw / Nat Ford Planning ecosystem.*

---

## 1. The 60-second pitch

ClawModeler is a **local-first, desktop-installable transportation sketch-planning
workbench for small and rural California agencies, tribes, RTPAs, and the consultants
who serve them.** It stages a planner's own data (zones, socio-economic tables,
candidate projects), runs a deterministic engine that produces scenario outputs
(accessibility deltas, VMT screening, scored projects), and emits a Planner Pack of
regulation-aligned artifacts (CEQA §15064.3 significance memos, Caltrans LAPM
programming exhibits, Regional Transportation Plan chapters, SB 535 / AB 1550 equity
lenses, California ATP grant packets). Everything is grounded in citable fact-blocks,
runs on the user's laptop without any cloud upload, and ships as a ~40 MB Tauri
installer for Windows, macOS, and Linux.

It is **not** a chat-first tool. It is a planner's workbench where the chat and AI
narrative features are strictly layered on top of a deterministic engine under a hard
"every sentence cites a real fact-block or the sentence is dropped" contract.

---

## 2. What problem ClawModeler actually solves

California transportation planning has a compounding data problem. To get a project
funded and environmentally cleared, a small agency has to produce, in sequence:

1. A **VMT screening** (CEQA §15064.3 + OPR Dec 2018 Technical Advisory — default
   threshold 15% below regional baseline VMT/capita).
2. A **Caltrans LAPM programming exhibit** (Chapter 3 fact sheet per project).
3. An **RTP chapter** that ties project lists to performance metrics (Gov Code §65080).
4. An **equity lens overlay** (SB 535 DAC share, AB 1550 low-income share, tribal
   sovereignty per Pub Res Code §§21074 / 21080.3.1–21080.3.2).
5. A **grant application packet** (California ATP, HSIP, CMAQ, STIP), each with its
   own scoring rubric (e.g., ATP's 30 / 25 / 25 / 20 safety / equity / climate /
   feasibility weights in S&HC §§2380–2383).

Every one of those deliverables needs the **same underlying data** (project list,
scenario assumptions, accessibility deltas, VMT estimates, equity overlay) but they
are almost never produced from the same spine. Small agencies do them in disconnected
spreadsheets and Word docs, lose track of which numbers came from where, and get
burned in review when the CEQA VMT number doesn't tie to the RTP's VMT number, or
the ATP packet claims a DAC benefit percentage the equity lens never produced.

ClawModeler's bet: **put the spine in one place, make every artifact derive from the
same manifest + fact-blocks, and enforce a QA gate that blocks export when the
artifacts don't cite real evidence.** That is the product.

---

## 3. The shape of the product

Three user-facing surfaces share one engine:

### 3.1 Python engine (`clawmodeler_engine/`)

Python 3.10+ package, installable via `pip install -e .`. The CLI entry point is
`clawmodeler-engine`, declared in `pyproject.toml` as a console script.

Core modules worth reading in this order:
1. `workspace.py` — workspace layout, `ENGINE_VERSION`, the directory skeleton.
2. `contracts.py` — manifest schema versioning (currently **1.2.0**, with **1.0.0**
   listed in `LEGACY_MANIFEST_VERSIONS`), `stamp_contract`, `validate_contract`.
3. `model.py` — scenario scoring, `DEFAULT_SCORING_WEIGHTS` (California
   ATP-aligned: safety 0.30, equity 0.25, climate 0.25, feasibility 0.20),
   `compute_project_scores(weights=…)`, `run_full_stack(scoring_weights=…)`.
4. `qa.py` — the QA-gate validator. Every fact-block must have `method_ref` (str) +
   `artifact_refs` (non-empty list of `{path, type}` dicts). `build_qa_report` returns
   `export_ready: true` or `blockers: [...]`.
5. `orchestration.py` — the `workflow {full,demo-full,diagnose,report-only}` entry
   points, `write_export`.
6. `report.py` — Jinja2 template rendering; **StrictUndefined is on**, which is why
   every fact-block key has to exist (missing keys raise, not warn).
7. `planner_pack/{ceqa,lapm,rtp,equity,atp,hsip,cmaq,stip}.py` — the Planner Pack modules.
   Each follows the same **quartet pattern**:
   ```
   compute_*(...)         # pure, no I/O
   *_fact_blocks(...)     # dict list, method_ref + artifact_refs required
   render_*_markdown(...) # Jinja2
   write_*(workspace, …)  # reads run, writes outputs/tables/ + reports/, appends fact_blocks.jsonl
   ```
8. `diff.py` — run-to-run diff across every engine + Planner Pack artifact
   (`compute_run_diff`, `run_diff_fact_blocks`, `render_run_diff_markdown`,
   `write_run_diff`). Writes to `diffs/<run_a>_vs_<run_b>/`.
9. `what_if.py` — the v0.8.0 what-if simulator. Takes a finished run as baseline,
   applies `WhatIfOverrides` (scoring weights, VMT threshold, project include /
   exclude, sensitivity floor), re-invokes `run_full_stack` with the new weights,
   re-filters `project_scores.csv`, stamps the new run's manifest with `base_run_id`
   + `overrides`, and records every change as a `what_if_scenario` or
   `what_if_project_delta` fact-block.
10. `chat.py` — grounded Q&A over a run's fact-blocks. Every sentence in the reply
    must cite `[fact:<id>]` against a real fact-block; ungrounded sentences are
    dropped. When everything drops, the reply collapses to
    `"I do not have evidence for that in this run's fact_blocks."`
11. `llm/` — provider adapters (ollama default, Anthropic / OpenAI BYOK behind a
    `cloud_confirmed` gate) + the deterministic citation validator.

### 3.2 Tauri v2 desktop workbench (`desktop/`)

`desktop/src-tauri/src/lib.rs` exposes six Tauri commands that all route through
one shared `run_engine_args` sidecar invocation:

| Command | Purpose |
|---|---|
| `clawmodeler_doctor` | Check local modeling stack (Python, DuckDB, OSMnx, etc.) |
| `clawmodeler_tools` | List available tools / bridges |
| `clawmodeler_run` | Generic engine invocation with a `Vec<String>` args list |
| `clawmodeler_workspace` | Read a run's manifest + qa_report + files for the UI |
| `clawmodeler_chat` | Chat with a finished run |
| `clawmodeler_what_if` | Run a what-if override (v0.8.1) |

The frontend is vanilla TypeScript (no framework) — `desktop/src/main.ts` +
`desktop/src/workbench.ts` + `desktop/src/workbench.test.ts`. State lives in one
`AppState` object; rendering is a single `render()` that rewrites `#app.innerHTML`
and then binds events in `bindControls()`. Pure helpers live in `workbench.ts` so
Vitest can cover them without a DOM (currently 21 cases across chat parsing,
what-if weight rebalancing, form validation, friendly error mapping).

### 3.3 Sidecar-packaging pipeline

The engine ships as a PyInstaller-built single-file `clawmodeler-engine` binary
that Tauri bundles as a "resource" next to the desktop app. `scripts/build-sidecar-binary.sh`
drives the build per-OS; the Tauri config lists the binary under `bundle.resources`.
When the desktop app starts, `sidecar_path()` in `lib.rs` walks a priority list
(`$CLAWMODELER_ENGINE_BIN` → `resource_dir()` → `binaries/`) and falls back to
`python3 -m clawmodeler_engine` if no sidecar is found (this is how `pnpm tauri:dev`
works without rebuilding PyInstaller every time).

GitHub Actions builds on ubuntu-latest + macos-14 + windows-latest, producing
**six bundles** per release: `.AppImage`, `.deb`, `.rpm` (Linux), `.dmg` (macOS
arm64), `.msi`, `setup.exe` (Windows).

---

## 4. The data model you must internalize

Four concepts explain 90% of the code:

### 4.1 Workspace
A user-chosen folder. Layout:
```
workspace/
├── inputs/              # staged user data (CSVs, GeoJSON)
│   ├── raw/             # original uploads
│   └── processed/       # normalized, validated
├── runs/<run_id>/
│   ├── manifest.json    # schema 1.2.0 — the spine of the run
│   ├── qa_report.json   # export_ready: bool + blockers
│   ├── chat_history.jsonl
│   └── outputs/
│       ├── tables/
│       │   ├── project_scores.csv
│       │   ├── vmt_screening.csv
│       │   ├── ceqa_vmt.csv         # when planner-pack ceqa-vmt has run
│       │   ├── lapm_exhibit.csv     # when planner-pack lapm-exhibit has run
│       │   ├── rtp_chapter_*.csv
│       │   ├── equity_lens.csv
│       │   ├── atp_packet.csv
│       │   ├── hsip.csv
│       │   ├── cmaq.csv
│       │   ├── stip.csv
│       │   └── fact_blocks.jsonl    # the evidence spine
│       ├── figures/     # matplotlib PNGs
│       ├── maps/        # folium HTML/PNG
│       └── bridges/     # SUMO/MATSim/UrbanSim/TBEST/DTALite packages
├── reports/
│   ├── <run_id>_report.md
│   ├── <run_id>_ceqa_vmt.md, _lapm_exhibit.md, _rtp_chapter.md, _equity_lens.md, _atp_packet.md
│   ├── <run_id>_hsip.md, _cmaq.md, _stip.md
│   └── <run_a>_vs_<run_b>_diff.md
└── diffs/<run_a>_vs_<run_b>/
    ├── diff.csv, diff.json, fact_blocks.jsonl
```

### 4.2 Run
Identified by a string `run_id`. A run has exactly one manifest. The manifest records
which inputs were staged, which scenarios were executed, which tools were invoked,
the engine version, and (if the run was produced by what-if) `base_run_id` + the
applied `overrides`. Runs are **content-addressed by user intent, not by hash** —
the user picks the id.

### 4.3 Fact-block
One line of JSON in `fact_blocks.jsonl`. Minimum shape:
```json
{
  "fact_id": "score-top-ranked",
  "fact_type": "project_score",
  "claim_text": "Project X ranks 1st in the portfolio with total_score 0.672.",
  "method_ref": "model.compute_project_scores",
  "artifact_refs": [{"path": "outputs/tables/project_scores.csv", "type": "table"}],
  "scenario_id": "baseline",
  "created_at": "2026-04-18T20:12:03Z"
}
```
`qa.is_valid_fact_block` is the single validator. `method_ref` is a dotted
module-specific identifier (e.g., `planner_pack.ceqa_vmt`, `diff.run_to_run`,
`what_if.parameter_override`). `artifact_refs` is a non-empty list of path + type
dicts. Both are **hard requirements** — v0.7.1 shipped specifically because the
Planner Pack modules had been omitting them for six versions, silently blocking
`export` with `blockers: ["fact_blocks_invalid"]`.

### 4.4 QA gate
`build_qa_report(workspace, run_id)` reads the manifest, the fact-blocks, and the
artifact tree, and emits `runs/<id>/qa_report.json`. `export_ready: true` only if
every fact-block validates, every claimed artifact exists, and the manifest
invariants hold. Every CLI subcommand that produces deliverables rebuilds the QA
report before returning.

---

## 5. The grounding covenant (read this twice)

ClawModeler's entire credibility rests on one rule:

> **Every sentence in any AI-generated output — chat reply, narrative summary,
> report prose — must cite a `[fact:<fact_id>]` that resolves to a real fact-block
> in this run, or the sentence is dropped.**

The covenant is enforced by a deterministic regex + set-membership validator in
`clawmodeler_engine/llm/` (the citation validator), not by the LLM itself. The LLM
cannot be coaxed into ungrounded output because the ungrounded sentences never
reach the user. When the validator drops every sentence of a reply, the reply
collapses to the literal string:
`"I do not have evidence for that in this run's fact_blocks."`

This is the **non-negotiable foundation**. Every new AI feature (narrative, chat,
future grant-wizard drafting) layers on top of this gate. Features that violate it
do not ship.

Deterministic features — scoring, VMT screening, Planner Pack emitters, diff,
what-if — call no LLM at all. That is why the grounding covenant is preserved even
when the user runs a what-if scenario that rewrites half the portfolio: no LLM is
in the loop; the new fact-blocks are derived from recomputed CSVs by pure Python.

---

## 6. The Planner Pack quartet pattern (copy this for new features)

When adding a new regulation-aligned deliverable, copy the shape of
`planner_pack/ceqa.py`:

1. `@dataclass` for the inputs and outputs (e.g., `CeqaVmtFinding`).
2. `compute_*(...)` — pure function, reads staged CSVs, returns dataclass instances.
3. `*_fact_blocks(findings, source_path) -> list[dict]` — each block carries the
   QA-gate-compliant keys. Set `scenario_id: None` when a block isn't scenario-scoped
   (otherwise `technical.md.j2` will raise under StrictUndefined — v0.8.0 shipped
   the fix).
4. `render_*_markdown(findings, **context) -> str` — Jinja2 template in
   `clawmodeler_engine/templates/`. Cite regulatory sources in the body (§15064.3,
   LAPM, OPR Advisory, S&HC §§2380–2383, Gov Code §65080, etc.).
5. `write_*(workspace, run_id, **overrides) -> Path` — writes CSV + JSON +
   Markdown, appends fact-blocks to the existing `fact_blocks.jsonl` (do not
   overwrite — append with dedup by `fact_id`), rebuilds the QA report.
6. CLI subparser in `cli.py` + `command_*` dispatcher. Add regression tests in
   `tests/test_<feature>.py` that exercise `build_qa_report` after the `write_*`
   call — this is how we catch the v0.7.1-class "I forgot `method_ref`" bug.

Every Planner Pack module, plus `diff.py` and `what_if.py`, follows this shape.
If a new feature doesn't fit the quartet, ask whether it's really a Planner Pack
deliverable or something else.

---

## 7. How this got built — the compounding release arc

The interesting part is the **shape** of the arc, not the individual commits. Every
release composed with every prior release.

- **v0.2.0** — 3-platform desktop release pipeline. The scaffolding bet: ship the
  installer before the product, so every later release just adds depth without
  touching distribution.
- **v0.3.0** — Jinja2 templates + charts + maps. Reports became the product surface.
- **v0.4.0** — grounded AI narrative with the citation validator. This is where
  the grounding covenant became load-bearing.
- **v0.4.1** — PDF export via `markdown-it-py` + WeasyPrint. The Markdown chain
  got a second render target for free.
- **v0.5.0 / v0.5.1** — Chat With the Run (engine + desktop panel). Same grounding
  covenant as narrative, new UI for it.
- **v0.6.0 / .1 / .2 / .3 / .4** — the five Planner Packs in 48 hours:
  CEQA → LAPM → RTP → Equity → ATP. Each one ~200 lines of engine code + a
  template + a ~12-test regression suite, all following the quartet pattern.
- **v0.7.0** — run-to-run diff. Needed because the Planner Packs produced enough
  comparable artifacts that comparing two runs by hand was untenable.
- **v0.7.1** — QA-gate schema fix. Every Planner Pack emitter and the diff emitter
  had been writing fact-blocks without `method_ref` + `artifact_refs`, so
  `build_qa_report` returned `export_ready: false` after any Planner Pack command.
  Additive fix: add the missing keys, keep legacy `source_table` / `source_row` for
  compatibility, add a regression test that exercises `build_qa_report` after
  every `write_*`. This is the highest-value 30-line patch in the whole arc.
- **v0.8.0** — what-if simulator (engine + CLI). Manifest schema bumped 1.0.0 →
  1.1.0 additive: optional `base_run_id` + `overrides` fields, legacy versions
  1.2.0 additive: optional `detailed_engine_readiness` on run manifests and `forecast_readiness` on bridge manifests so bridge handoff readiness stays separate from calibrated forecast readiness.
  remain readable. `model.py` scoring refactored to accept weight overrides
  (defaults unchanged — byte-identical for every existing caller). 22-test
  regression suite. The diff engine, which had been underpowered because users
  could only diff hand-curated runs, suddenly became powerful because what-if
  produces mechanically-derived alternatives.
- **v0.8.1** — what-if desktop panel. Sliders that rebalance the other three
  weights proportionally to keep the sum at exactly 1.0, form-level client-side
  validation, auto-navigate to the new run on success. 11 new Vitest cases.

The compounding pattern is clear: **infrastructure first, then depth, then
composition, then fixes, then iteration**. The what-if simulator would have been
1000 lines if it had shipped in v0.3 — it shipped at ~350 because the scoring path
in `model.py`, the manifest schema, the fact-block contract, the Planner Pack
pattern, and the diff engine were already in place.

---

## 8. Does OpenClaw fork "great" into a transportation modeling platform?

**Partially. The honest answer has two halves.**

### 8.1 What worked

OpenClaw's **multi-agent methodology** — ClawPrincipal (product), ClawAnalyst
(data), ClawGIS (spatial), ClawEngineer (build), ClawQA (gates), ClawWriter
(narrative) — is an excellent **design-time** framework for evolving a planning
tool. The roles map almost 1:1 to how a real transportation consultancy staffs a
project: principal-in-charge, senior analyst, GIS lead, software engineer,
technical reviewer, writer. The agent team's docs bundle still lives at
`code/ClawModeler/` (different casing from the runnable `code/clawmodeler/`) and
is how this product gets scoped, reviewed, and extended. That is a genuine win.

The grounding covenant also transplanted well. OpenClaw is built on strict
citation contracts for general assistant use; ClawModeler specializes those
contracts to regulatory citations (CEQA §15064.3, LAPM chapters, Gov Code §65080,
S&HC §§2380–2383, OPR Dec 2018 Technical Advisory). The underlying machinery —
deterministic regex + set-membership validator, `[fact:<id>]` chips in chat
transcripts, `export_ready` QA gate — is the same.

### 8.2 Where the fork had to break from the parent pattern

OpenClaw as a multi-channel personal assistant is **runtime-agentic**: LLMs
orchestrate actions, respond to events, hold conversations, choose tools. A
transportation modeling platform for small agencies **must be the opposite of
that** at runtime:

- **Determinism is the product.** The value of a CEQA VMT memo is that the same
  inputs produce the same number across reviewers, months, and staff changes. An
  LLM-orchestrated pipeline cannot promise this. ClawModeler's engine calls no LLM
  for any numerical output. The LLM only layers narrative and chat on top of
  already-computed fact-blocks, under the grounding gate.
- **Local-first is the product.** Many small agencies, tribes, and rural RTPAs
  cannot upload project lists to third-party cloud services for confidentiality,
  political, or policy reasons. An agent framework that assumes cloud inference is
  unshippable into this market. ClawModeler defaults to ollama; cloud providers
  are opt-in behind a `cloud_confirmed` gate.
- **Installers are the product.** Agency users do not run `pip install`. They
  download a `.msi` and double-click it. The Tauri + PyInstaller sidecar
  architecture is there because that is the only deployment small agencies
  tolerate.
- **Regulatory framing is the product.** The Planner Pack quartet pattern —
  `compute / fact_blocks / render / write`, cited against specific California
  statutes — does not generalize to non-planning domains. Trying to make it do so
  would be a featuritis mistake.

So the honest framing is: **OpenClaw's methodology and grounding infrastructure
transplanted great. OpenClaw's runtime pattern (LLM-orchestrated agent loops) did
not, and was deliberately inverted.** If you told someone "ClawModeler is OpenClaw
for transportation planning," the first half of that sentence would mislead them
about how the runtime actually works.

The fork was the right move. Keeping ClawModeler inside the OpenClaw repo would
have created constant pressure to use the same runtime patterns, when the product
needed the opposite. Shipping as a standalone repo (nfredmond/clawmodeler,
Apache-2.0, public) let the runtime be deterministic without apologizing for not
being "agentic."

---

## 9. What's still to build

Plan-approved arc after v0.9.2:

- **0.9.2 release stabilization.** Package templates into wheels, keep full
  engine/UI/Tauri checks green, and align docs with the standalone app.
- **Planner workflow milestone.** Make the desktop flow coherent end to end:
  workspace setup, run, QA, artifact review, Planner Pack generation, grounded
  chat, what-if, diff, and portfolio.
- **v1.0 horizon — Modeling depth.** AequilibraE calibrated-model handoff,
  ActivitySim integration, GIS export (ArcGIS Online, QGIS project file), offline
  model cache bundling. Moves ClawModeler from sketch-planning into real
  forecasting.

The recommendation in the plan is to ship v0.8.x interactivity first (it unlocks
diff and makes the tool sticky), then take user feedback before committing to
grant-wizard vs modeling-depth.

---

## 10. How a fresh agent should onboard

**Read first (in this order):**
1. `README.md` — product framing.
2. `docs/roadmap.md` — where this is going.
3. `docs/stack.md` — the dependency graph.
4. `clawmodeler_engine/workspace.py` — directory layout + engine version.
5. `clawmodeler_engine/qa.py` — the contract every new feature must honor.
6. `clawmodeler_engine/planner_pack/ceqa.py` — the canonical quartet-pattern example.
7. `tests/test_what_if.py` — how to write a regression suite that exercises the QA
   gate after every new `write_*`.
8. `CHANGELOG.md` — the release arc in one file.

**Try these commands:**
```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -p '*test*.py'      # expect 216/216 pass
ruff check .                                               # expect clean
clawmodeler-engine workflow demo-full --workspace /tmp/ws --run-id demo
clawmodeler-engine planner-pack ceqa-vmt --workspace /tmp/ws --run-id demo
clawmodeler-engine what-if --workspace /tmp/ws --base-run-id demo --new-run-id alt \
  --weight-safety 0.40 --weight-equity 0.30 --weight-climate 0.20 --weight-feasibility 0.10
clawmodeler-engine diff --workspace /tmp/ws --run-a demo --run-b alt
clawmodeler-engine export --workspace /tmp/ws --run-id alt --format pdf
pnpm ui:test                                               # expect 21/21 pass
pnpm ui:build                                              # expect clean
```

**Conventions that are load-bearing (not stylistic):**
- Manifest schema is **additive**. Never remove or rename fields. If you must
  evolve, bump `CURRENT_MANIFEST_VERSION`, add the old version to
  `LEGACY_MANIFEST_VERSIONS`, and leave `validate_contract` accepting both.
- Every fact-block **must** have `method_ref` (str) + `artifact_refs`
  (non-empty list of `{path, type}` dicts) + `scenario_id` (may be None).
  Omitting any of these silently blocks `export`.
- Defaults in `model.py` are California ATP-aligned (0.30 / 0.25 / 0.25 / 0.20).
  Do not change the defaults; only allow them to be overridden via kwargs.
- The grounding covenant is non-negotiable. New AI features that could emit
  ungrounded prose must layer on top of the existing citation validator, not
  around it.
- Regression tests must exercise `build_qa_report` after the feature's `write_*`
  call. This is how we guard against the v0.7.1-class silent-export-blocker bug.
- Signed-inline git identity for this repo:
  `20851160+nfredmond@users.noreply.github.com` / Nathaniel Ford Redmond.
  Every commit uses `git -c user.email=... -c user.name=...` inline.
- Releases follow a fixed sequence: bump 6 version files → add CHANGELOG entry
  above the prior entry → commit signed-inline → push main → tag → push tag →
  watch CI → watch Release → verify 6 bundles attached. Do not skip any step.

**Red flags to ask about before touching:**
- Anything in `llm/` — the citation validator is the most dangerous file in the
  repo. Breaking it breaks the grounding covenant.
- The scoring line in `model.py` — altering the default weights would silently
  change every historical run's scores.
- The Tauri command list in `desktop/src-tauri/src/lib.rs` (around line 240–250).
  Removing a command breaks existing installed desktop apps that still expect it.
- Any template under `clawmodeler_engine/templates/` that uses
  `{{ block.scenario_id or "—" }}` — **StrictUndefined is on**, so fact-blocks
  missing `scenario_id` will raise at export time (v0.8.0 fix).

---

## 11. Closing

ClawModeler is a small-agency-first, local-first, regulation-aligned, deterministic
transportation sketch-planning workbench. It is the opposite of a chat product:
the AI features are strictly downstream of a deterministic engine under a hard
citation gate. The OpenClaw connection is real but selective — the methodology
and grounding machinery transplanted great; the runtime pattern had to be
inverted. The release arc has been deliberately compounding: scaffolding →
depth → composition → fixes → iteration. The next stop is the portfolio
dashboard; after that, either grant-wizard expansion or modeling-depth.

If you are an AI agent reading this for the first time, start with
`clawmodeler_engine/workspace.py` and `clawmodeler_engine/qa.py`, then trace a
single Planner Pack module end-to-end, then read `what_if.py` to see how a new
feature is layered on top of the existing contract. After that, the rest of the
codebase will feel obvious.
