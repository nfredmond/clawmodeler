"""Run-to-run diff across shipped ClawModeler artifacts.

Transportation plans iterate. An RTP cycle may produce half a dozen
screening runs as assumptions, network edits, or project lists change;
before a board adoption the lead agency must explain *what moved* since
the previous draft. This module compares two finished runs in the same
workspace and emits a structured diff — added / removed / changed rows
for every shipped artifact both runs contain — plus a Markdown report
and grounded fact_blocks so downstream narrative and chat turns can
cite the differences under the same citation contract as the rest of
ClawModeler.

The diff reads CSVs written by the engine and the Planner Pack series:
``project_scores.csv``, ``vmt_screening.csv``, ``ceqa_vmt.csv``,
``lapm_exhibit.csv``, ``rtp_chapter_projects.csv``,
``rtp_chapter_scenarios.csv``, ``equity_lens.csv``, ``atp_packet.csv``.
Missing artifacts are reported as *not present in this run* rather than
silently dropped.

This module does not call an LLM. Every claim is derived deterministically
from the two input runs.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .report import read_fact_blocks
from .workspace import (
    ENGINE_VERSION,
    InsufficientDataError,
    sync_project_database,
    utc_now,
    write_json,
)

# Per-artifact diff spec: which column is the row key, which columns are
# tracked for change detection, and which are numeric (so the diff can
# report a delta). Presence of an artifact is optional; every Planner
# Pack module may or may not have been run.
_TRACKED_ARTIFACTS: tuple[dict[str, Any], ...] = (
    {
        "name": "project_scores",
        "filename": "project_scores.csv",
        "key": "project_id",
        "label": "Project screening scores",
        "tracked": (
            "name",
            "safety_score",
            "equity_score",
            "climate_score",
            "feasibility_score",
            "total_score",
            "sensitivity_flag",
        ),
        "numeric": (
            "safety_score",
            "equity_score",
            "climate_score",
            "feasibility_score",
            "total_score",
        ),
    },
    {
        "name": "vmt_screening",
        "filename": "vmt_screening.csv",
        "key": "scenario_id",
        "label": "VMT screening (per scenario)",
        "tracked": (
            "population",
            "daily_vmt",
            "daily_vmt_delta",
            "daily_kg_co2e",
            "tier",
            "method",
        ),
        "numeric": (
            "population",
            "daily_vmt",
            "daily_vmt_delta",
            "daily_kg_co2e",
        ),
    },
    {
        "name": "ceqa_vmt",
        "filename": "ceqa_vmt.csv",
        "key": "scenario_id",
        "label": "CEQA §15064.3 VMT determinations",
        "tracked": (
            "vmt_per_capita",
            "threshold_vmt_per_capita",
            "delta_pct",
            "significant",
            "determination",
            "mitigation_required",
        ),
        "numeric": (
            "vmt_per_capita",
            "threshold_vmt_per_capita",
            "delta_pct",
        ),
    },
    {
        "name": "lapm_exhibit",
        "filename": "lapm_exhibit.csv",
        "key": "project_id",
        "label": "Caltrans LAPM programming exhibit",
        "tracked": (
            "lead_agency",
            "district",
            "estimated_cost_usd",
            "project_type",
            "location_note",
        ),
        "numeric": ("estimated_cost_usd",),
    },
    {
        "name": "rtp_chapter_projects",
        "filename": "rtp_chapter_projects.csv",
        "key": "project_id",
        "label": "RTP chapter — project entries",
        "tracked": (
            "total_score",
            "sensitivity_flag",
            "lapm_project_type",
            "lapm_estimated_cost_usd",
        ),
        "numeric": ("total_score", "lapm_estimated_cost_usd"),
    },
    {
        "name": "rtp_chapter_scenarios",
        "filename": "rtp_chapter_scenarios.csv",
        "key": "scenario_id",
        "label": "RTP chapter — scenario entries",
        "tracked": (
            "population",
            "daily_vmt",
            "vmt_per_capita",
            "accessibility_delta_jobs",
            "ceqa_determination",
        ),
        "numeric": (
            "population",
            "daily_vmt",
            "vmt_per_capita",
            "accessibility_delta_jobs",
        ),
    },
    {
        "name": "equity_lens",
        "filename": "equity_lens.csv",
        "key": "project_id",
        "label": "SB 535 / AB 1550 / tribal equity lens",
        "tracked": (
            "dac_sb535",
            "low_income_ab1550",
            "low_income_near_dac",
            "tribal_area",
            "benefit_category",
            "overlay_supplied",
        ),
        "numeric": (),
    },
    {
        "name": "atp_packet",
        "filename": "atp_packet.csv",
        "key": "project_id",
        "label": "California ATP application packet",
        "tracked": (
            "agency",
            "cycle",
            "total_score",
            "benefit_category",
            "atp_dac_benefit_eligible",
            "estimated_cost_usd",
            "sensitivity_flag",
        ),
        "numeric": ("total_score", "estimated_cost_usd"),
    },
    {
        "name": "hsip",
        "filename": "hsip.csv",
        "key": "project_id",
        "label": "FHWA HSIP cycle screen",
        "tracked": (
            "crash_history_5yr",
            "fatal_serious_5yr",
            "systemic_risk_score",
            "benefit_cost_ratio",
            "proven_countermeasure",
            "overlay_supplied",
            "bc_ratio_passes",
            "screen_status",
        ),
        "numeric": (
            "crash_history_5yr",
            "fatal_serious_5yr",
            "systemic_risk_score",
            "benefit_cost_ratio",
        ),
    },
    {
        "name": "cmaq",
        "filename": "cmaq.csv",
        "key": ("project_id", "pollutant"),
        "label": "FHWA CMAQ cycle packet",
        "tracked": (
            "kg_per_day_reduced",
            "cost_effectiveness_usd_per_kg",
            "eligibility_category",
            "nonattainment_area",
            "overlay_supplied",
        ),
        "numeric": (
            "kg_per_day_reduced",
            "cost_effectiveness_usd_per_kg",
        ),
    },
    {
        "name": "stip",
        "filename": "stip.csv",
        "key": ("project_id", "phase", "fiscal_year"),
        "label": "California STIP cycle packet",
        "tracked": (
            "cost_thousands",
            "funding_source",
            "ppno",
            "region",
            "overlay_supplied",
        ),
        "numeric": (
            "cost_thousands",
        ),
    },
)


@dataclass
class FieldChange:
    field: str
    from_value: str
    to_value: str
    numeric_delta: float | None


@dataclass
class RowChange:
    key: str
    name: str
    status: str  # "added" | "removed" | "changed"
    changes: list[FieldChange] = field(default_factory=list)


@dataclass
class ArtifactDiff:
    artifact: str
    label: str
    filename: str
    key_column: str
    present_in_a: bool
    present_in_b: bool
    row_count_a: int
    row_count_b: int
    added_count: int
    removed_count: int
    changed_count: int
    unchanged_count: int
    row_changes: list[RowChange] = field(default_factory=list)


@dataclass
class RunDiffResult:
    run_a_id: str
    run_b_id: str
    run_a_engine_version: str | None
    run_b_engine_version: str | None
    run_a_created_at: str | None
    run_b_created_at: str | None
    artifacts: list[ArtifactDiff] = field(default_factory=list)
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_a_id": self.run_a_id,
            "run_b_id": self.run_b_id,
            "run_a_engine_version": self.run_a_engine_version,
            "run_b_engine_version": self.run_b_engine_version,
            "run_a_created_at": self.run_a_created_at,
            "run_b_created_at": self.run_b_created_at,
            "generated_at": self.generated_at,
            "artifacts": [asdict(a) for a in self.artifacts],
        }


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _row_name(row: dict[str, Any], fallback: str) -> str:
    for col in ("name", "project_name"):
        val = _normalize(row.get(col))
        if val:
            return val
    return fallback


def _diff_single_artifact(
    spec: dict[str, Any],
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    present_a: bool,
    present_b: bool,
) -> ArtifactDiff:
    key = spec["key"]
    tracked = tuple(spec["tracked"])
    numeric = set(spec["numeric"])

    if isinstance(key, tuple):
        key_columns: tuple[str, ...] = key
        key_label = "+".join(key_columns)
    else:
        key_columns = (key,)
        key_label = key

    def _row_key(row: dict[str, Any]) -> str:
        parts = [_normalize(row.get(col)) for col in key_columns]
        if not all(parts):
            return ""
        return "|".join(parts)

    by_key_a: dict[str, dict[str, Any]] = {}
    for row in rows_a:
        k = _row_key(row)
        if k:
            by_key_a[k] = row
    by_key_b: dict[str, dict[str, Any]] = {}
    for row in rows_b:
        k = _row_key(row)
        if k:
            by_key_b[k] = row

    keys_a = set(by_key_a)
    keys_b = set(by_key_b)

    row_changes: list[RowChange] = []
    added_count = 0
    removed_count = 0
    changed_count = 0
    unchanged_count = 0

    for k in sorted(keys_b - keys_a):
        row = by_key_b[k]
        row_changes.append(
            RowChange(
                key=k,
                name=_row_name(row, k),
                status="added",
                changes=[
                    FieldChange(
                        field=col,
                        from_value="",
                        to_value=_normalize(row.get(col)),
                        numeric_delta=None,
                    )
                    for col in tracked
                    if _normalize(row.get(col))
                ],
            )
        )
        added_count += 1

    for k in sorted(keys_a - keys_b):
        row = by_key_a[k]
        row_changes.append(
            RowChange(
                key=k,
                name=_row_name(row, k),
                status="removed",
                changes=[
                    FieldChange(
                        field=col,
                        from_value=_normalize(row.get(col)),
                        to_value="",
                        numeric_delta=None,
                    )
                    for col in tracked
                    if _normalize(row.get(col))
                ],
            )
        )
        removed_count += 1

    for k in sorted(keys_a & keys_b):
        row_a = by_key_a[k]
        row_b = by_key_b[k]
        field_changes: list[FieldChange] = []
        for col in tracked:
            v_a = _normalize(row_a.get(col))
            v_b = _normalize(row_b.get(col))
            if v_a == v_b:
                continue
            delta: float | None = None
            if col in numeric:
                f_a = _parse_optional_float(row_a.get(col))
                f_b = _parse_optional_float(row_b.get(col))
                if f_a is not None and f_b is not None:
                    delta = round(f_b - f_a, 3)
            field_changes.append(
                FieldChange(
                    field=col,
                    from_value=v_a,
                    to_value=v_b,
                    numeric_delta=delta,
                )
            )
        if field_changes:
            row_changes.append(
                RowChange(
                    key=k,
                    name=_row_name(row_b, k),
                    status="changed",
                    changes=field_changes,
                )
            )
            changed_count += 1
        else:
            unchanged_count += 1

    return ArtifactDiff(
        artifact=spec["name"],
        label=spec["label"],
        filename=spec["filename"],
        key_column=key_label,
        present_in_a=present_a,
        present_in_b=present_b,
        row_count_a=len(rows_a),
        row_count_b=len(rows_b),
        added_count=added_count,
        removed_count=removed_count,
        changed_count=changed_count,
        unchanged_count=unchanged_count,
        row_changes=row_changes,
    )


def compute_run_diff(
    *,
    run_a_id: str,
    run_b_id: str,
    artifact_rows_a: dict[str, list[dict[str, Any]]],
    artifact_rows_b: dict[str, list[dict[str, Any]]],
    artifact_present_a: dict[str, bool],
    artifact_present_b: dict[str, bool],
    run_a_engine_version: str | None = None,
    run_b_engine_version: str | None = None,
    run_a_created_at: str | None = None,
    run_b_created_at: str | None = None,
) -> RunDiffResult:
    """Compute a deterministic diff between two finished runs."""
    if run_a_id == run_b_id:
        raise InsufficientDataError(
            "run-a and run-b must be different run IDs to produce a diff."
        )

    artifacts: list[ArtifactDiff] = []
    for spec in _TRACKED_ARTIFACTS:
        name = spec["name"]
        artifacts.append(
            _diff_single_artifact(
                spec,
                artifact_rows_a.get(name, []),
                artifact_rows_b.get(name, []),
                artifact_present_a.get(name, False),
                artifact_present_b.get(name, False),
            )
        )

    return RunDiffResult(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        run_a_engine_version=run_a_engine_version,
        run_b_engine_version=run_b_engine_version,
        run_a_created_at=run_a_created_at,
        run_b_created_at=run_b_created_at,
        artifacts=artifacts,
        generated_at=utc_now(),
    )


def _format_field_summary(change: FieldChange) -> str:
    from_s = change.from_value or "∅"
    to_s = change.to_value or "∅"
    base = f"{change.field}: {from_s} → {to_s}"
    if change.numeric_delta is not None:
        sign = "+" if change.numeric_delta >= 0 else ""
        base += f" (Δ {sign}{change.numeric_delta})"
    return base


def _format_row_summary(row: RowChange) -> str:
    if row.status == "added":
        return f"added row `{row.key}` ({row.name})"
    if row.status == "removed":
        return f"removed row `{row.key}` ({row.name})"
    parts = "; ".join(_format_field_summary(c) for c in row.changes)
    return f"changed `{row.key}` ({row.name}) — {parts}"


def run_diff_fact_blocks(
    result: RunDiffResult, source_path: Path
) -> list[dict[str, Any]]:
    """Emit per-row `run_diff_row` and per-artifact `run_diff_summary` blocks."""
    blocks: list[dict[str, Any]] = []
    for artifact in result.artifacts:
        for row in artifact.row_changes:
            claim = (
                f"Run {result.run_a_id} → {result.run_b_id} "
                f"({artifact.label}): {_format_row_summary(row)}."
            )
            blocks.append(
                {
                    "fact_id": (
                        f"run-diff-{artifact.artifact}-{row.status}-{row.key}"
                    ),
                    "fact_type": "run_diff_row",
                    "artifact": artifact.artifact,
                    "status": row.status,
                    "claim_text": claim,
                    "method_ref": "diff.run_to_run",
                    "artifact_refs": [{"path": str(source_path), "type": "table"}],
                    "source_table": str(source_path),
                    "source_row": row.key,
                }
            )
        if artifact.present_in_a or artifact.present_in_b:
            presence_phrase = {
                (True, True): "present in both runs",
                (True, False): f"present only in run {result.run_a_id}",
                (False, True): f"present only in run {result.run_b_id}",
                (False, False): "present in neither run",
            }[(artifact.present_in_a, artifact.present_in_b)]
        else:
            presence_phrase = "present in neither run"
        summary_claim = (
            f"Run {result.run_a_id} → {result.run_b_id} "
            f"({artifact.label}): {presence_phrase}; "
            f"{artifact.added_count} added, {artifact.removed_count} removed, "
            f"{artifact.changed_count} changed, "
            f"{artifact.unchanged_count} unchanged."
        )
        blocks.append(
            {
                "fact_id": f"run-diff-summary-{artifact.artifact}",
                "fact_type": "run_diff_summary",
                "artifact": artifact.artifact,
                "claim_text": summary_claim,
                "method_ref": "diff.run_to_run",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": artifact.artifact,
            }
        )
    return blocks


def render_run_diff_markdown(result: RunDiffResult) -> str:
    """Render the diff as a Markdown report."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    template = env.get_template("run_diff.md.j2")
    return template.render(
        engine_version=ENGINE_VERSION,
        result=result.to_json(),
        artifacts=[asdict(a) for a in result.artifacts],
    )


def _flatten_diff_rows(
    result: RunDiffResult,
) -> list[dict[str, Any]]:
    """Flatten diff row changes into CSV rows (one per FieldChange).

    Added/removed rows with no tracked columns still emit a single row
    with an empty ``field`` column so the CSV captures the event.
    """
    flat: list[dict[str, Any]] = []
    for artifact in result.artifacts:
        for row in artifact.row_changes:
            if not row.changes:
                flat.append(
                    {
                        "artifact": artifact.artifact,
                        "key": row.key,
                        "name": row.name,
                        "status": row.status,
                        "field": "",
                        "from_value": "",
                        "to_value": "",
                        "numeric_delta": "",
                    }
                )
                continue
            for change in row.changes:
                flat.append(
                    {
                        "artifact": artifact.artifact,
                        "key": row.key,
                        "name": row.name,
                        "status": row.status,
                        "field": change.field,
                        "from_value": change.from_value,
                        "to_value": change.to_value,
                        "numeric_delta": (
                            "" if change.numeric_delta is None
                            else change.numeric_delta
                        ),
                    }
                )
    return flat


def _append_fact_blocks(path: Path, new_blocks: list[dict[str, Any]]) -> int:
    if not new_blocks:
        return 0
    existing_ids: set[str] = set()
    if path.exists():
        existing_ids = {str(b.get("fact_id")) for b in read_fact_blocks(path)}
    appended = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for block in new_blocks:
            if block["fact_id"] in existing_ids:
                continue
            f.write(json.dumps(block) + "\n")
            appended += 1
    return appended


def _load_run_manifest(run_root: Path) -> dict[str, Any]:
    manifest_path = run_root / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_run_artifacts(
    run_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    tables_dir = run_root / "outputs" / "tables"
    rows: dict[str, list[dict[str, Any]]] = {}
    present: dict[str, bool] = {}
    for spec in _TRACKED_ARTIFACTS:
        path = tables_dir / spec["filename"]
        exists = path.exists()
        present[spec["name"]] = exists
        rows[spec["name"]] = _read_csv(path) if exists else []
    return rows, present


def write_run_diff(
    workspace: Path,
    run_a_id: str,
    run_b_id: str,
) -> dict[str, Any]:
    """Compute a diff between two runs, write artifacts, return paths."""
    if run_a_id == run_b_id:
        raise InsufficientDataError(
            "run-a and run-b must be different run IDs to produce a diff."
        )
    run_a_root = workspace / "runs" / run_a_id
    run_b_root = workspace / "runs" / run_b_id
    if not run_a_root.exists():
        raise InsufficientDataError(
            f"Run {run_a_id!r} does not exist under {workspace}."
        )
    if not run_b_root.exists():
        raise InsufficientDataError(
            f"Run {run_b_id!r} does not exist under {workspace}."
        )

    rows_a, present_a = _collect_run_artifacts(run_a_root)
    rows_b, present_b = _collect_run_artifacts(run_b_root)

    # Require that at least one tracked artifact is present in each run so
    # the diff is meaningful.
    if not any(present_a.values()):
        raise InsufficientDataError(
            f"Run {run_a_id!r} has no tracked artifacts in outputs/tables/."
        )
    if not any(present_b.values()):
        raise InsufficientDataError(
            f"Run {run_b_id!r} has no tracked artifacts in outputs/tables/."
        )

    manifest_a = _load_run_manifest(run_a_root)
    manifest_b = _load_run_manifest(run_b_root)

    def _engine_version(manifest: dict[str, Any]) -> str | None:
        app = manifest.get("app") if isinstance(manifest, dict) else None
        if isinstance(app, dict):
            return app.get("engine_version")
        return None

    result = compute_run_diff(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        artifact_rows_a=rows_a,
        artifact_rows_b=rows_b,
        artifact_present_a=present_a,
        artifact_present_b=present_b,
        run_a_engine_version=_engine_version(manifest_a),
        run_b_engine_version=_engine_version(manifest_b),
        run_a_created_at=manifest_a.get("created_at") if manifest_a else None,
        run_b_created_at=manifest_b.get("created_at") if manifest_b else None,
    )

    diff_dir = workspace / "diffs" / f"{run_a_id}_vs_{run_b_id}"
    diff_dir.mkdir(parents=True, exist_ok=True)
    csv_path = diff_dir / "diff.csv"
    json_path = diff_dir / "diff.json"
    fact_blocks_path = diff_dir / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_a_id}_vs_{run_b_id}_diff.md"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "artifact",
                "key",
                "name",
                "status",
                "field",
                "from_value",
                "to_value",
                "numeric_delta",
            ],
        )
        writer.writeheader()
        for row in _flatten_diff_rows(result):
            writer.writerow(row)

    write_json(json_path, result.to_json())

    new_blocks = run_diff_fact_blocks(result, csv_path)
    appended = _append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_run_diff_markdown(result)
    report_path.write_text(markdown, encoding="utf-8")

    totals = {
        "added": sum(a.added_count for a in result.artifacts),
        "removed": sum(a.removed_count for a in result.artifacts),
        "changed": sum(a.changed_count for a in result.artifacts),
        "unchanged": sum(a.unchanged_count for a in result.artifacts),
    }
    sync_project_database(workspace)
    return {
        "report_path": str(report_path),
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "diff_dir": str(diff_dir),
        "fact_block_count": appended,
        "run_a_id": run_a_id,
        "run_b_id": run_b_id,
        "totals": totals,
    }
