# CEQA §15064.3 VMT Significance Determination — run `rural-demo`

- Engine version: `0.9.6`
- Generated: `2026-04-22T05:30:08Z`
- Project type: **residential**
- Reference baseline: **regional** — 25.0 VMT per capita
- Screening threshold: **15% below regional** → 21.25 VMT per capita

## Scope

This memo documents the CEQA transportation-impact significance screening for each
scenario produced by ClawModeler run `rural-demo`. Per California Public Resources
Code §21099 and CEQA Guidelines §15064.3 (revised after SB 743), vehicle miles
traveled (VMT) is the preferred metric for transportation-impact significance for
land-use and transportation projects.

## Methodology

The Governor's Office of Planning and Research (OPR) *Technical Advisory on
Evaluating Transportation Impacts in CEQA* (December 2018) recommends **15 percent
below the regional or citywide VMT-per-capita baseline** as the default residential
screening threshold. Scenarios at or above that cut line are flagged as *potentially
significant*; scenarios below it are *less than significant*. The cut line applied
to this run is **21.25 VMT per capita**
(15 percent below the
regional reference of 25.0
VMT per capita). Determinations are arithmetic and reproducible; no model is
consulted.

## Per-scenario determinations

| Scenario | Population | Daily VMT | VMT/capita | Threshold | Δ vs. threshold | Determination |
|---|---:|---:|---:|---:|---:|---|
| `baseline` | 2800.0 | 53200.0 | 19.0 | 21.25 | -10.6% | **less than significant** |
| `infill-growth` | 3274.0 | 62206.0 | 19.0 | 21.25 | -10.6% | **less than significant** |



## Findings


No scenarios in this run exceed the CEQA §15064.3 screening threshold. All
scenarios are **less than significant** for transportation-impact purposes.



The following scenarios are **less than significant** and do not require VMT
mitigation under CEQA §15064.3:

- `baseline`: 19.0 VMT per capita — -10.6% versus the 21.25 VMT per capita threshold.
- `infill-growth`: 19.0 VMT per capita — -10.6% versus the 21.25 VMT per capita threshold.



## Citations

- California Public Resources Code §21099.
- CEQA Guidelines §15064.3 (14 CCR §15064.3).
- Governor's Office of Planning and Research, *Technical Advisory on Evaluating Transportation Impacts in CEQA*, December 2018.

## Notes

- Determinations in this memo are *screening-level*. A lead agency may adopt a
  different threshold or a custom methodology with substantial evidence. Override
  the reference VMT per capita or the percent-below value on the command line to
  reproduce the agency's preferred cut line.
- Every determination in this memo is mirrored as a `ceqa_vmt_determination`
  fact_block appended to this run's `fact_blocks.jsonl`, so subsequent narrative
  and chat turns remain subject to the ClawModeler citation contract.

---

*ClawModeler Planner Pack — CEQA §15064.3 VMT significance screening.*
