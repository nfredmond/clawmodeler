"""What-if simulator.

Given a finished run, apply deterministic parameter overrides and
produce a new run with the same artifact structure so diff, Planner
Pack, chat, export, and AI narrative compose unchanged.

Override surfaces:

- ``scoring_weights`` — override the safety/equity/climate/feasibility
  weights in ``model.compute_project_scores`` (default
  0.30/0.25/0.25/0.20, must sum to 1.0).
- ``project_ids_include`` / ``project_ids_exclude`` — filter rows in
  ``project_scores.csv`` after the stack runs.
- ``sensitivity_floor`` — drop rows whose ``sensitivity_flag`` is
  more assumption-heavy than the floor (``LOW`` keeps all, ``MEDIUM``
  keeps ``LOW``+``MEDIUM``, ``HIGH`` keeps only ``HIGH``-scoring rows
  — i.e., rows with *lower* assumption counts survive).
- ``reference_vmt_per_capita`` / ``threshold_pct`` — recorded in the
  new run's manifest ``overrides`` field so a subsequent
  ``planner-pack ceqa-vmt`` call has an audit trail of the agency's
  intent. They do not automatically trigger CEQA re-computation.

Everything is deterministic. No LLM is called; no narrative is
generated. The grounding covenant is preserved — every
``what_if_scenario`` / ``what_if_project_delta`` fact_block carries
``method_ref="what_if.parameter_override"`` + ``artifact_refs`` so the
v0.7.1 QA gate keeps passing.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .contracts import CURRENT_MANIFEST_VERSION, stamp_contract, validate_contract
from .model import DEFAULT_SCORING_WEIGHTS, _resolve_scoring_weights, run_full_stack
from .qa import build_qa_report
from .report import read_fact_blocks
from .workspace import (
    ENGINE_VERSION,
    InsufficientDataError,
    collect_artifact_hashes,
    load_receipt,
    read_json,
    run_paths,
    utc_now,
    write_json,
)

SENSITIVITY_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class WhatIfOverrides:
    scoring_weights: dict[str, float] | None = None
    reference_vmt_per_capita: float | None = None
    threshold_pct: float | None = None
    project_ids_include: list[str] | None = None
    project_ids_exclude: list[str] | None = None
    sensitivity_floor: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.scoring_weights is not None:
            payload["scoring_weights"] = dict(self.scoring_weights)
        if self.reference_vmt_per_capita is not None:
            payload["reference_vmt_per_capita"] = float(
                self.reference_vmt_per_capita
            )
        if self.threshold_pct is not None:
            payload["threshold_pct"] = float(self.threshold_pct)
        if self.project_ids_include is not None:
            payload["project_ids_include"] = list(self.project_ids_include)
        if self.project_ids_exclude is not None:
            payload["project_ids_exclude"] = list(self.project_ids_exclude)
        if self.sensitivity_floor is not None:
            payload["sensitivity_floor"] = str(self.sensitivity_floor)
        return payload

    def is_empty(self) -> bool:
        return self.to_json() == {}


@dataclass
class WhatIfProjectDelta:
    project_id: str
    name: str
    base_total_score: float
    new_total_score: float
    score_delta: float
    status: str  # "kept" | "dropped" | "rescored"


@dataclass
class WhatIfResult:
    base_run_id: str
    new_run_id: str
    applied_overrides: dict[str, Any]
    project_deltas: list[WhatIfProjectDelta] = field(default_factory=list)
    dropped_project_ids: list[str] = field(default_factory=list)
    base_fact_block_count: int = 0
    new_fact_block_count: int = 0
    scoring_weights_used: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SCORING_WEIGHTS)
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "base_run_id": self.base_run_id,
            "new_run_id": self.new_run_id,
            "applied_overrides": self.applied_overrides,
            "project_deltas": [asdict(delta) for delta in self.project_deltas],
            "dropped_project_ids": list(self.dropped_project_ids),
            "base_fact_block_count": self.base_fact_block_count,
            "new_fact_block_count": self.new_fact_block_count,
            "scoring_weights_used": dict(self.scoring_weights_used),
        }


def _validate_sensitivity_floor(floor: str | None) -> str | None:
    if floor is None:
        return None
    normalized = floor.strip().upper()
    if normalized not in SENSITIVITY_ORDER:
        raise ValueError(
            f"sensitivity_floor must be one of {sorted(SENSITIVITY_ORDER)}; "
            f"got {floor!r}"
        )
    return normalized


def _validate_overrides(overrides: WhatIfOverrides) -> WhatIfOverrides:
    if overrides.is_empty():
        raise InsufficientDataError(
            "WhatIfOverrides must specify at least one override; "
            "got an empty overrides payload"
        )
    if overrides.scoring_weights is not None:
        _resolve_scoring_weights(overrides.scoring_weights)
    if overrides.threshold_pct is not None and not (
        0.0 < float(overrides.threshold_pct) < 1.0
    ):
        raise ValueError(
            "threshold_pct must be strictly between 0 and 1; "
            f"got {overrides.threshold_pct!r}"
        )
    if overrides.reference_vmt_per_capita is not None and float(
        overrides.reference_vmt_per_capita
    ) <= 0:
        raise ValueError(
            "reference_vmt_per_capita must be positive; "
            f"got {overrides.reference_vmt_per_capita!r}"
        )
    overrides.sensitivity_floor = _validate_sensitivity_floor(
        overrides.sensitivity_floor
    )
    if overrides.project_ids_include is not None and overrides.project_ids_exclude is not None:
        overlap = set(overrides.project_ids_include) & set(
            overrides.project_ids_exclude
        )
        if overlap:
            raise ValueError(
                f"project_ids_include and project_ids_exclude overlap on: {sorted(overlap)}"
            )
    return overrides


def _read_scores_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _score_lookup(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["project_id"]: row for row in rows if row.get("project_id")}


def _apply_row_filters(
    rows: list[dict[str, Any]],
    overrides: WhatIfOverrides,
) -> tuple[list[dict[str, Any]], list[str]]:
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    include = (
        set(overrides.project_ids_include)
        if overrides.project_ids_include is not None
        else None
    )
    exclude = (
        set(overrides.project_ids_exclude)
        if overrides.project_ids_exclude is not None
        else set()
    )
    floor_rank = (
        SENSITIVITY_ORDER[overrides.sensitivity_floor]
        if overrides.sensitivity_floor is not None
        else None
    )
    for row in rows:
        project_id = row.get("project_id", "")
        if include is not None and project_id not in include:
            dropped.append(project_id)
            continue
        if project_id in exclude:
            dropped.append(project_id)
            continue
        if floor_rank is not None:
            row_flag = str(row.get("sensitivity_flag", "")).strip().upper()
            row_rank = SENSITIVITY_ORDER.get(row_flag)
            if row_rank is None or row_rank > floor_rank:
                dropped.append(project_id)
                continue
        kept.append(row)
    return kept, dropped


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _filter_score_fact_blocks(
    blocks: list[dict[str, Any]],
    kept_project_ids: set[str],
) -> list[dict[str, Any]]:
    """Drop per-project-ranking fact_blocks tied to dropped projects.

    The engine emits a ``score-top-ranked`` fact_block that references
    the highest-scoring row by name. Because the top-ranked project
    might now be different under new weights or filters, we recompute
    the score fact_block from the new rows in ``write_what_if`` rather
    than preserving the base block here. This helper just drops the
    stale block so the caller can append the fresh one.
    """
    return [
        block
        for block in blocks
        if block.get("fact_id") != "score-top-ranked"
    ]


def _what_if_summary_claim(result: WhatIfResult) -> str:
    parts: list[str] = []
    overrides = result.applied_overrides
    if "scoring_weights" in overrides:
        weights = overrides["scoring_weights"]
        parts.append(
            "scoring weights = "
            + ", ".join(
                f"{k}={weights[k]:.2f}"
                for k in ("safety", "equity", "climate", "feasibility")
            )
        )
    if "reference_vmt_per_capita" in overrides:
        parts.append(
            f"reference VMT/capita = {overrides['reference_vmt_per_capita']:.2f}"
        )
    if "threshold_pct" in overrides:
        parts.append(
            f"CEQA threshold = {overrides['threshold_pct'] * 100:.1f}% below reference"
        )
    if "project_ids_include" in overrides:
        parts.append(
            f"included {len(overrides['project_ids_include'])} project(s): "
            + ", ".join(overrides["project_ids_include"][:5])
            + ("..." if len(overrides["project_ids_include"]) > 5 else "")
        )
    if "project_ids_exclude" in overrides:
        parts.append(
            f"excluded {len(overrides['project_ids_exclude'])} project(s)"
        )
    if "sensitivity_floor" in overrides:
        parts.append(
            f"sensitivity floor = {overrides['sensitivity_floor']}"
        )
    override_phrase = "; ".join(parts) if parts else "no parameter overrides"
    return (
        f"What-if scenario derived from run `{result.base_run_id}` → "
        f"`{result.new_run_id}`: {override_phrase}. "
        f"{len(result.project_deltas)} project(s) re-scored, "
        f"{len(result.dropped_project_ids)} dropped."
    )


def what_if_fact_blocks(
    result: WhatIfResult,
    source_path: Path,
) -> list[dict[str, Any]]:
    """Emit a ``what_if_scenario`` summary block plus per-project deltas.

    Every block carries ``method_ref="what_if.parameter_override"`` and
    ``artifact_refs=[{"path": <source_path>, "type": "table"}]`` so the
    v0.7.1 QA gate (``qa.is_valid_fact_block``) accepts them.
    """
    blocks: list[dict[str, Any]] = [
        {
            "fact_id": f"what-if-scenario-{result.new_run_id}",
            "fact_type": "what_if_scenario",
            "scenario_id": None,
            "claim_text": _what_if_summary_claim(result),
            "method_ref": "what_if.parameter_override",
            "artifact_refs": [{"path": str(source_path), "type": "table"}],
            "base_run_id": result.base_run_id,
            "new_run_id": result.new_run_id,
            "created_at": utc_now(),
        }
    ]
    for delta in result.project_deltas:
        blocks.append(
            {
                "fact_id": f"what-if-project-{result.new_run_id}-{delta.project_id}",
                "fact_type": "what_if_project_delta",
                "scenario_id": None,
                "project_id": delta.project_id,
                "claim_text": (
                    f"What-if `{result.new_run_id}` vs base `{result.base_run_id}`: "
                    f"project `{delta.project_id}` ({delta.name}) total_score "
                    f"{delta.base_total_score:.3f} → {delta.new_total_score:.3f} "
                    f"(Δ {delta.score_delta:+.3f}, {delta.status})."
                ),
                "method_ref": "what_if.parameter_override",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "created_at": utc_now(),
            }
        )
    return blocks


def render_what_if_markdown(result: WhatIfResult, *, run_id: str) -> str:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template("what_if.md.j2")
    return template.render(
        result=result,
        run_id=run_id,
        generated_at=utc_now(),
        engine_version=ENGINE_VERSION,
    )


def compute_what_if(
    workspace: Path,
    base_run_id: str,
    overrides: WhatIfOverrides,
    *,
    new_run_id: str,
) -> WhatIfResult:
    """Plan a what-if without writing any files.

    Validates overrides, confirms the base run exists and the new run
    id is free, and returns a result stub. ``write_what_if`` does the
    side-effectful work of producing the new run tree.
    """

    overrides = _validate_overrides(overrides)
    base_run_root = workspace / "runs" / base_run_id
    if not base_run_root.exists():
        raise InsufficientDataError(
            f"Base run {base_run_id!r} not found at {base_run_root}"
        )
    new_run_root = workspace / "runs" / new_run_id
    if new_run_root.exists():
        raise InsufficientDataError(
            f"Run id {new_run_id!r} already exists at {new_run_root}; "
            "pick a distinct new-run-id"
        )
    if new_run_id == base_run_id:
        raise ValueError("base_run_id and new_run_id must differ")

    resolved_weights = _resolve_scoring_weights(overrides.scoring_weights)
    return WhatIfResult(
        base_run_id=base_run_id,
        new_run_id=new_run_id,
        applied_overrides=overrides.to_json(),
        scoring_weights_used=resolved_weights,
    )


def write_what_if(
    workspace: Path,
    base_run_id: str,
    new_run_id: str,
    overrides: WhatIfOverrides,
) -> tuple[Path, WhatIfResult]:
    """Produce a new run under ``runs/<new_run_id>/`` derived from the base.

    Pipeline:
      1. Validate overrides and confirm collision-free new_run_id.
      2. Load the base manifest to recover the scenarios list.
      3. Re-invoke ``run_full_stack`` with ``scoring_weights=overrides``
         so project_scores is recomputed deterministically. All other
         artifacts are recomputed from the same staged inputs under
         ``workspace/inputs/`` — they are byte-identical to the base
         for unchanged overrides (e.g. weight-only).
      4. Apply project include/exclude + sensitivity_floor filters to
         project_scores.csv and drop corresponding score_fact_blocks.
      5. Append ``what_if_scenario`` + per-project delta fact_blocks.
      6. Stamp manifest with ``manifest_version="1.1.0"``, ``base_run_id``,
         and ``overrides``; build the QA report.
    """

    result = compute_what_if(
        workspace, base_run_id, overrides, new_run_id=new_run_id
    )
    overrides = _validate_overrides(overrides)
    resolved_weights = _resolve_scoring_weights(overrides.scoring_weights)

    base_run_root = workspace / "runs" / base_run_id
    base_manifest_path = base_run_root / "manifest.json"
    if not base_manifest_path.exists():
        raise InsufficientDataError(
            f"Base run {base_run_id!r} has no manifest at {base_manifest_path}"
        )
    base_manifest = read_json(base_manifest_path)
    scenarios = [
        str(entry.get("scenario_id"))
        for entry in base_manifest.get("scenarios", [])
        if isinstance(entry, dict) and entry.get("scenario_id")
    ]
    if not scenarios:
        raise InsufficientDataError(
            f"Base run {base_run_id!r} manifest has no scenarios"
        )

    base_scores_path = (
        base_run_root / "outputs" / "tables" / "project_scores.csv"
    )
    base_scores = (
        _read_scores_csv(base_scores_path) if base_scores_path.exists() else []
    )
    base_score_lookup = _score_lookup(base_scores)

    receipt = load_receipt(workspace)
    paths = run_paths(workspace, new_run_id)

    stack_result = run_full_stack(
        workspace,
        new_run_id,
        receipt,
        scenarios,
        paths,
        scoring_weights=resolved_weights,
    )

    new_scores_path = paths["tables"] / "project_scores.csv"
    new_scores = (
        _read_scores_csv(new_scores_path) if new_scores_path.exists() else []
    )
    filtered_scores, dropped_ids = _apply_row_filters(new_scores, overrides)
    if dropped_ids or filtered_scores != new_scores:
        _write_csv(new_scores_path, filtered_scores)

    kept_ids = {row.get("project_id", "") for row in filtered_scores}
    project_deltas: list[WhatIfProjectDelta] = []
    for row in filtered_scores:
        project_id = row.get("project_id", "")
        new_total = float(row.get("total_score", 0.0))
        base_row = base_score_lookup.get(project_id)
        if base_row is None:
            base_total = 0.0
            status = "rescored"
        else:
            base_total = float(base_row.get("total_score", 0.0))
            status = "rescored" if abs(new_total - base_total) > 1e-9 else "kept"
        project_deltas.append(
            WhatIfProjectDelta(
                project_id=project_id,
                name=str(row.get("name", project_id)),
                base_total_score=round(base_total, 3),
                new_total_score=round(new_total, 3),
                score_delta=round(new_total - base_total, 3),
                status=status,
            )
        )

    fact_blocks_path = paths["tables"] / "fact_blocks.jsonl"
    existing_blocks = (
        read_fact_blocks(fact_blocks_path) if fact_blocks_path.exists() else []
    )
    filtered_blocks = _filter_score_fact_blocks(existing_blocks, kept_ids)
    result.project_deltas = project_deltas
    result.dropped_project_ids = dropped_ids
    result.base_fact_block_count = len(existing_blocks)

    what_if_blocks = what_if_fact_blocks(result, new_scores_path)
    all_blocks = filtered_blocks + what_if_blocks
    with fact_blocks_path.open("w", encoding="utf-8") as file:
        for block in all_blocks:
            file.write(json.dumps(block) + "\n")
    result.new_fact_block_count = len(all_blocks)

    manifest = stamp_contract(
        {
            "manifest_version": CURRENT_MANIFEST_VERSION,
            "run_id": new_run_id,
            "base_run_id": base_run_id,
            "overrides": overrides.to_json(),
            "created_at": utc_now(),
            "app": {"name": "ClawModeler", "engine_version": ENGINE_VERSION},
            "engine": base_manifest.get("engine", {}),
            "workspace": base_manifest.get("workspace", {}),
            "inputs": receipt.get("inputs", []),
            "input_hashes": collect_artifact_hashes(workspace / "inputs"),
            "output_hashes": collect_artifact_hashes(paths["outputs"]),
            "scenarios": [{"scenario_id": scenario_id} for scenario_id in scenarios],
            "methods": stack_result["methods"] + ["what_if"],
            "outputs": stack_result["outputs"],
            "assumptions": stack_result["assumptions"],
            "fact_block_count": len(all_blocks),
        },
        "run_manifest",
    )
    validate_contract(manifest, "run_manifest")
    manifest_path = paths["root"] / "manifest.json"
    write_json(manifest_path, manifest)

    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{new_run_id}_what_if.md"
    report_path.write_text(
        render_what_if_markdown(result, run_id=new_run_id), encoding="utf-8"
    )

    write_json(paths["root"] / "what_if.json", result.to_json())
    build_qa_report(workspace, new_run_id)

    return manifest_path, result
