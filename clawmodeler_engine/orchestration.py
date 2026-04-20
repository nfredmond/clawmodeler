from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    CURRENT_MANIFEST_VERSION,
    normalize_question_contract,
    stamp_contract,
    validate_artifact_file,
    validate_contract,
)
from .model import run_full_stack
from .qa import build_qa_report, load_qa_report
from .readiness import build_detailed_engine_readiness
from .report import REPORT_TYPES, render_report
from .workspace import (
    ENGINE_VERSION,
    InsufficientDataError,
    QaGateBlockedError,
    collect_artifact_hashes,
    discover_workspace_inputs,
    ensure_workspace,
    load_receipt,
    read_json,
    run_paths,
    stage_inputs,
    sync_project_database,
    utc_now,
    write_json,
)


def write_intake(workspace: Path, input_paths: list[Path]) -> Path:
    workspace_info = ensure_workspace(workspace)
    artifacts = stage_inputs(workspace, input_paths)
    receipt = stamp_contract(
        {
            "created_at": utc_now(),
            "workspace": workspace_info,
            "inputs": [artifact.to_json() for artifact in artifacts],
            "validation": {
                "zone_id_present": any(artifact.zone_ids for artifact in artifacts),
                "join_coverage_threshold": "95%",
            },
        },
        "intake_receipt",
    )
    validate_contract(receipt, "intake_receipt")
    output_path = workspace / "intake_receipt.json"
    write_json(output_path, receipt)
    sync_project_database(workspace, receipt=receipt)
    return output_path


def write_plan(
    workspace: Path,
    question_path: Path,
    *,
    routing_overrides: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    ensure_workspace(workspace)
    receipt = load_receipt(workspace)
    question = normalize_question_contract(read_json(question_path))
    question = apply_routing_overrides(question, routing_overrides)
    input_flags = discover_workspace_inputs(workspace)
    engine_selection = select_engine(question, input_flags)
    analysis_plan = stamp_contract(
        {
            "created_at": utc_now(),
            "question": question,
            "inputs": {
                "receipt": "intake_receipt.json",
                "count": len(receipt.get("inputs", [])),
                **input_flags,
            },
            "methods": [
                "intake",
                "model_brain",
                "scenario_lab",
                "accessibility_engine",
                "vmt_climate",
                "transit_analyzer",
                "project_scoring",
                "narrative_engine",
                "bridge_exports",
            ],
            "assumptions": [
                "MVP outputs are screening-level unless a detailed engine integration is enabled.",
                "External downloads are disabled unless explicitly configured.",
            ],
        },
        "analysis_plan",
    )
    engine_selection = stamp_contract(engine_selection, "engine_selection")
    validate_contract(analysis_plan, "analysis_plan")
    validate_contract(engine_selection, "engine_selection")
    analysis_path = workspace / "analysis_plan.json"
    engine_path = workspace / "engine_selection.json"
    write_json(analysis_path, analysis_plan)
    write_json(engine_path, engine_selection)
    return analysis_path, engine_path


def select_engine(question: dict[str, Any], flags: dict[str, bool]) -> dict[str, Any]:
    question_type = str(question.get("question_type", "accessibility"))
    num_zones = int(question.get("num_zones", 0) or 0)
    gtfs_size_mb = float(question.get("gtfs_size_mb", 0) or 0)
    gtfs_present = bool(flags.get("gtfs_present"))

    if question_type in {"accessibility", "transit_coverage"} and not gtfs_present:
        return {
            "routing_engine": "osmnx_networkx",
            "note": "Car/walk/bike screening only; transit disabled because GTFS is absent.",
        }
    if (
        question_type in {"accessibility", "transit_accessibility"}
        and gtfs_present
        and (num_zones > 500 or gtfs_size_mb > 50)
    ):
        return {
            "routing_engine": "r5_optional",
            "note": "Use optional R5 for large many-to-many or transit accessibility.",
        }
    return {"routing_engine": "osmnx_networkx", "note": "Default MVP screening engine."}


def normalize_scenario_ids(scenarios: list[str]) -> list[str]:
    scenario_ids = [str(scenario).strip() for scenario in scenarios if str(scenario).strip()]
    return scenario_ids or ["baseline"]


def apply_routing_overrides(
    question: dict[str, Any],
    routing_overrides: dict[str, str] | None,
) -> dict[str, Any]:
    if not routing_overrides:
        return question

    routing = question.get("routing")
    if not isinstance(routing, dict):
        routing = {}
    else:
        routing = dict(routing)

    for key in ("source", "graph_id", "impedance"):
        value = str(routing_overrides.get(key, "")).strip()
        if value:
            routing[key] = value

    updated = dict(question)
    if routing:
        updated["routing"] = routing
    return updated


def write_run(workspace: Path, run_id: str, scenarios: list[str]) -> tuple[Path, Path]:
    workspace_info = ensure_workspace(workspace)
    receipt = load_receipt(workspace)
    paths = run_paths(workspace, run_id)
    engine_path = workspace / "engine_selection.json"
    engine = read_json(engine_path) if engine_path.exists() else select_engine({}, {})
    question = _read_question(workspace)
    scenario_ids = normalize_scenario_ids(scenarios)

    stack_result = run_full_stack(workspace, run_id, receipt, scenario_ids, paths)
    detailed_engine_readiness = build_detailed_engine_readiness(
        workspace,
        question=question,
        receipt=receipt,
    )
    manifest = stamp_contract(
        {
            "manifest_version": CURRENT_MANIFEST_VERSION,
            "run_id": run_id,
            "created_at": utc_now(),
            "app": {"name": "ClawModeler", "engine_version": ENGINE_VERSION},
            "engine": engine,
            "workspace": workspace_info,
            "inputs": receipt.get("inputs", []),
            "input_hashes": collect_artifact_hashes(workspace / "inputs"),
            "output_hashes": collect_artifact_hashes(paths["outputs"]),
            "scenarios": [{"scenario_id": scenario_id} for scenario_id in scenario_ids],
            "methods": stack_result["methods"],
            "outputs": stack_result["outputs"],
            "assumptions": _augment_assumptions(
                stack_result["assumptions"],
                detailed_engine_readiness,
            ),
            "fact_block_count": stack_result["fact_block_count"],
            "detailed_engine_readiness": detailed_engine_readiness,
        },
        "run_manifest",
    )
    validate_contract(manifest, "run_manifest")
    manifest_path = paths["root"] / "manifest.json"
    write_json(manifest_path, manifest)
    build_qa_report(workspace, run_id)
    sync_project_database(workspace, receipt=receipt, run_id=run_id)
    return manifest_path, paths["root"] / "qa_report.json"


def write_export(
    workspace: Path,
    run_id: str,
    export_format: str,
    *,
    report_type: str = "technical",
    ai_narrative: bool = False,
) -> Path | list[Path]:
    ensure_workspace(workspace)
    reports_dir = workspace / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    build_qa_report(workspace, run_id)
    qa_report = load_qa_report(workspace, run_id)
    if not qa_report.get("export_ready"):
        _write_qa_block_report(reports_dir, run_id, qa_report)
        raise QaGateBlockedError(
            f"Export blocked by QA gate: {reports_dir / f'{run_id}_export_blocked.md'}"
        )

    if export_format not in {"md", "pdf"}:
        raise InsufficientDataError(
            f"Export format {export_format!r} is not implemented in the sidecar scaffold."
        )

    manifest = validate_artifact_file(
        workspace / "runs" / run_id / "manifest.json",
        "run_manifest",
    )

    narrative_context: dict[str, Any] | None = None
    if ai_narrative:
        narrative_result = _generate_ai_narrative(workspace, run_id, manifest)
        build_qa_report(workspace, run_id, narrative=narrative_result)
        qa_report = load_qa_report(workspace, run_id)
        if not qa_report.get("export_ready"):
            _write_qa_block_report(
                reports_dir, run_id, qa_report, narrative=narrative_result
            )
            raise QaGateBlockedError(
                f"Export blocked by QA gate: "
                f"{reports_dir / f'{run_id}_export_blocked.md'}"
            )
        narrative_context = narrative_result.to_template_context()

    if report_type == "all":
        paths: list[Path] = []
        for single_type in REPORT_TYPES:
            path = _write_single_report(
                manifest,
                reports_dir,
                run_id,
                single_type,
                export_format,
                ai_narrative=narrative_context,
            )
            paths.append(path)
        return paths

    if report_type not in REPORT_TYPES:
        raise InsufficientDataError(
            f"Unknown --report-type {report_type!r}; expected one of {REPORT_TYPES} or 'all'."
        )
    return _write_single_report(
        manifest,
        reports_dir,
        run_id,
        report_type,
        export_format,
        ai_narrative=narrative_context,
    )


def _generate_ai_narrative(
    workspace: Path,
    run_id: str,
    manifest: dict[str, Any],
) -> Any:
    """Build provider and generate a narrative against the run's fact_blocks.

    Raises for provider- or config-level problems (unconfirmed cloud
    use, missing fact_blocks). Does NOT raise for grounding failures —
    those are recorded in the returned ``NarrativeResult`` and the
    caller feeds them into :func:`qa.build_qa_report` so the standard
    QA gate blocks the export.
    """

    from .llm import (
        CLOUD_PROVIDERS,
        GroundingMode,
        build_provider,
        generate_narrative,
        load_config,
    )
    from .report import read_fact_blocks

    config = load_config(workspace)
    if config.provider in CLOUD_PROVIDERS and not config.cloud_confirmed:
        raise InsufficientDataError(
            f"Cloud provider {config.provider!r} requires explicit confirmation. "
            "Run `clawmodeler-engine llm configure cloud_confirmed=true` "
            "before using --ai-narrative."
        )

    fact_blocks_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
    )
    fact_blocks = read_fact_blocks(fact_blocks_path) if fact_blocks_path.exists() else []
    if not fact_blocks:
        raise InsufficientDataError(
            "--ai-narrative requires at least one fact_block; none were found."
        )

    provider = build_provider(config)
    try:
        mode = GroundingMode(config.grounding_mode)
    except ValueError:
        mode = GroundingMode.STRICT
    return generate_narrative(manifest, fact_blocks, provider, mode=mode)


def _write_qa_block_report(
    reports_dir: Path,
    run_id: str,
    qa_report: dict[str, Any],
    *,
    narrative: Any = None,
) -> Path:
    blocked_path = reports_dir / f"{run_id}_export_blocked.md"
    lines = [
        "# Export Blocked",
        "",
        "ClawQA blocked this export because required evidence is missing.",
        "",
        f"Blockers: {', '.join(qa_report.get('blockers', []))}",
        "",
    ]
    if narrative is not None and not narrative.is_fully_grounded:
        lines += [
            "## AI narrative grounding failure",
            "",
            f"- Provider: `{narrative.provider}`",
            f"- Model: `{narrative.model}`",
            f"- Ungrounded sentences: {narrative.ungrounded_sentence_count}",
            f"- Unknown fact_ids: {narrative.unknown_fact_ids}",
            "",
            "### Raw model output",
            "",
            "```",
            narrative.raw_text,
            "```",
            "",
        ]
    blocked_path.write_text("\n".join(lines), encoding="utf-8")
    return blocked_path


def _read_question(workspace: Path) -> dict[str, Any]:
    analysis_plan_path = workspace / "analysis_plan.json"
    if not analysis_plan_path.exists():
        return {}
    return read_json(analysis_plan_path).get("question", {}) or {}


def _augment_assumptions(
    assumptions: list[str],
    detailed_engine_readiness: dict[str, Any],
) -> list[str]:
    augmented = list(assumptions)
    if detailed_engine_readiness.get("validation_ready_count"):
        augmented.append(
            "Detailed-engine readiness evidence is recorded for at least one bridge, but "
            "authoritative forecast language still depends on executing the external model and "
            "reviewing results under project QA."
        )
    else:
        augmented.append(
            "Bridge packages may be ready for handoff and structural validation while detailed "
            "forecast readiness remains blocked until project-specific calibration inputs, "
            "validation targets, and method notes are recorded."
        )
    return augmented


def _write_single_report(
    manifest: dict[str, Any],
    reports_dir: Path,
    run_id: str,
    report_type: str,
    export_format: str,
    *,
    ai_narrative: dict[str, Any] | None = None,
) -> Path:
    suffix = "" if report_type == "technical" else f"_{report_type}"
    report_path = reports_dir / f"{run_id}_report{suffix}.{export_format}"
    if export_format == "pdf":
        from .pdf import render_pdf

        report_path.write_bytes(
            render_pdf(
                manifest,
                report_type,
                reports_dir,
                ai_narrative=ai_narrative,
            )
        )
    else:
        report_path.write_text(
            render_report(manifest, report_type, ai_narrative=ai_narrative),
            encoding="utf-8",
        )
    return report_path
