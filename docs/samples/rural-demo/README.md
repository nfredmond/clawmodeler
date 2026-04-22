# Rural-Demo Sample Planner Pack

This folder holds a **full, real output set** from ClawModeler's built-in rural demo workflow. Nothing in here is mocked up — these are the actual artifacts the engine produced. Look at them to get a sense of what ClawModeler will produce for your own project before you install it.

> **Screening-level, not a calibrated forecast.** Every file here was produced by the built-in demo workflow using small synthetic zones, socio, project, network, and GTFS inputs. The outputs are designed to show the pipeline and Planner Pack format — not to substitute for detailed engineering analysis, calibrated regional modeling, or project-specific forecasting.

## What's in here

| File | What it is |
|---|---|
| [`sample_report.md`](sample_report.md) | Full technical report in Markdown — previewable directly on GitHub. |
| [`sample_report.docx`](sample_report.docx) | Same report in Microsoft Word format. Open this to see what planners get out of ClawModeler's `--format docx` export. |
| [`sample_report.pdf`](sample_report.pdf) | Same report in PDF. |
| [`ceqa_vmt_memo.md`](ceqa_vmt_memo.md) | CEQA §15064.3 VMT significance-determination memo produced by the `planner-pack ceqa-vmt` command. |
| [`qa_report.json`](qa_report.json) | Machine-readable QA-gate record. Shows the export decision, fact-block count, and any blockers. |
| [`fact_blocks.jsonl`](fact_blocks.jsonl) | Every grounded claim in the report, one JSON line each. Every narrative sentence in the technical report can be traced back to one of these. |
| [`figures/`](figures) | Two charts referenced by the report (VMT by scenario and accessibility delta). |

## How this was generated

Anyone with ClawModeler installed can reproduce this sample exactly:

```bash
# Install (choose the profile you need; "standard" covers this sample)
pip install -e .
bash scripts/install-profile.sh standard

# Run the rural demo end-to-end
clawmodeler-engine workflow demo-full \
  --workspace ./rural-demo-workspace \
  --run-id rural-demo

# Add the CEQA VMT Planner Pack memo
clawmodeler-engine planner-pack ceqa-vmt \
  --workspace ./rural-demo-workspace \
  --run-id rural-demo \
  --project-type residential \
  --reference-vmt-per-capita 25.0

# Export to Word (requires the docx extra: pip install -e ".[docx]")
clawmodeler-engine export \
  --workspace ./rural-demo-workspace \
  --run-id rural-demo \
  --format docx
```

The artifacts in this folder were produced exactly this way. Absolute workspace paths were sanitized to workspace-relative paths before commit, so the report reads cleanly outside the temp directory it was generated in.

## What to look at first

If you only want to spend two minutes here:

1. Open [`sample_report.docx`](sample_report.docx) in Word. This is what a planner gets from ClawModeler for their own project.
2. Skim [`ceqa_vmt_memo.md`](ceqa_vmt_memo.md). This is one of nine Planner Pack artifacts (CEQA VMT, LAPM, RTP chapter, equity lens, ATP, HSIP, CMAQ, STIP). Each one is grounded in fact-blocks and QA-gated.
3. Open [`qa_report.json`](qa_report.json). Every export in ClawModeler is blocked until this file records `"export_ready": true`. The gate checks manifest presence, fact-block count, and grounding — no un-cited narrative sentences make it out.

## Where to go from here

- Read [`docs/tutorial.md`](../../tutorial.md) for a 20-minute walkthrough using the desktop app instead of the CLI.
- Read [`docs/roadmap.md`](../../roadmap.md) for the release plan and what's deferred.
- See [ClawModeler releases](https://github.com/nfredmond/clawmodeler/releases/latest) for free installers.
