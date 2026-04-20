from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import load_receipt, read_json

DETAILED_ENGINE_IDS: tuple[str, ...] = ("sumo", "matsim", "urbansim", "dtalite", "tbest")

STATUS_LABELS = {
    "handoff_only": "Handoff only",
    "calibration_required": "Calibration required",
    "validation_ready": "Validation ready",
}

DEFAULT_REQUIREMENTS: dict[str, dict[str, list[dict[str, str]]]] = {
    "sumo": {
        "required_calibration_inputs": [
            {"id": "observed_counts", "label": "Observed counts"},
            {"id": "network_controls", "label": "Network controls or signal timing"},
            {"id": "demand_controls", "label": "Demand controls or OD assumptions"},
        ],
        "required_validation_targets": [
            {"id": "travel_times", "label": "Observed travel times"},
            {"id": "delay_or_queue", "label": "Delay or queue targets"},
        ],
    },
    "matsim": {
        "required_calibration_inputs": [
            {"id": "od_seed_or_survey", "label": "OD seed or survey data"},
            {"id": "counts_or_screenlines", "label": "Observed counts or screenlines"},
            {"id": "population_controls", "label": "Population or mode-share controls"},
        ],
        "required_validation_targets": [
            {"id": "mode_share", "label": "Observed mode share targets"},
            {"id": "screenline_or_link_counts", "label": "Screenline or link-count targets"},
        ],
    },
    "urbansim": {
        "required_calibration_inputs": [
            {"id": "land_use_inventory", "label": "Land-use inventory"},
            {"id": "household_controls", "label": "Household controls"},
            {"id": "job_controls", "label": "Job controls"},
        ],
        "required_validation_targets": [
            {"id": "household_totals", "label": "Observed household totals"},
            {"id": "job_totals", "label": "Observed job totals"},
        ],
    },
    "dtalite": {
        "required_calibration_inputs": [
            {"id": "traffic_counts", "label": "Traffic counts"},
            {"id": "od_seed_matrix", "label": "OD seed matrix"},
            {"id": "capacity_controls", "label": "Capacity or control data"},
        ],
        "required_validation_targets": [
            {"id": "link_volumes", "label": "Observed link volumes"},
            {"id": "travel_times", "label": "Observed travel times"},
        ],
    },
    "tbest": {
        "required_calibration_inputs": [
            {"id": "observed_ridership", "label": "Observed ridership"},
            {"id": "service_context", "label": "Service context"},
            {"id": "fare_or_network_notes", "label": "Fare or network notes"},
        ],
        "required_validation_targets": [
            {"id": "route_boardings", "label": "Route boarding targets"},
            {"id": "stop_boardings", "label": "Stop boarding targets"},
        ],
    },
}


def build_detailed_engine_readiness(
    workspace: Path,
    *,
    question: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_question = question or _load_question(workspace)
    resolved_receipt = receipt or _load_receipt_optional(workspace)

    engines = {
        engine_id: build_bridge_forecast_readiness(
            engine_id,
            workspace,
            question=resolved_question,
            receipt=resolved_receipt,
        )
        for engine_id in DETAILED_ENGINE_IDS
    }
    validation_ready_count = sum(
        1 for readiness in engines.values() if readiness["status"] == "validation_ready"
    )
    calibration_required_count = sum(
        1 for readiness in engines.values() if readiness["status"] == "calibration_required"
    )
    handoff_only_count = sum(
        1 for readiness in engines.values() if readiness["status"] == "handoff_only"
    )
    overall_status = (
        "validation_ready"
        if validation_ready_count == len(engines)
        else "calibration_required"
        if validation_ready_count > 0 or calibration_required_count > 0
        else "handoff_only"
    )
    return {
        "overall_status": overall_status,
        "overall_status_label": STATUS_LABELS[overall_status],
        "validation_ready_count": validation_ready_count,
        "calibration_required_count": calibration_required_count,
        "handoff_only_count": handoff_only_count,
        "engines": engines,
    }


def build_bridge_forecast_readiness(
    bridge_id: str,
    workspace: Path,
    *,
    question: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if bridge_id not in DEFAULT_REQUIREMENTS:
        raise KeyError(f"Unknown detailed bridge id: {bridge_id}")

    resolved_question = question or _load_question(workspace)
    resolved_receipt = receipt or _load_receipt_optional(workspace)
    engine_config = _engine_config(resolved_question, bridge_id)
    discovered = discover_local_calibration_evidence(resolved_receipt, bridge_id)

    required_calibration_inputs = _normalize_items(
        engine_config.get("required_calibration_inputs"),
        fallback=DEFAULT_REQUIREMENTS[bridge_id]["required_calibration_inputs"],
        kind="calibration_input",
    )
    required_validation_targets = _normalize_items(
        engine_config.get("required_validation_targets"),
        fallback=DEFAULT_REQUIREMENTS[bridge_id]["required_validation_targets"],
        kind="validation_target",
    )
    provided_calibration_inputs = _dedupe_items(
        _normalize_items(
            engine_config.get("provided_calibration_inputs")
            or engine_config.get("calibration_inputs"),
            kind="calibration_input",
        )
        + discovered["provided_calibration_inputs"]
    )
    provided_validation_targets = _dedupe_items(
        _normalize_items(
            engine_config.get("provided_validation_targets")
            or engine_config.get("validation_targets"),
            kind="validation_target",
        )
        + discovered["provided_validation_targets"]
    )
    method_notes = _dedupe_strings(
        _normalize_strings(engine_config.get("method_notes"))
        + _normalize_strings(engine_config.get("calibration_notes"))
        + discovered["method_notes"]
    )
    model_year = _string_or_none(
        engine_config.get("model_year")
        or resolved_question.get("model_year")
        or resolved_question.get("analysis_year")
    )
    calibration_geography = _string_or_none(
        engine_config.get("calibration_geography")
        or resolved_question.get("calibration_geography")
        or resolved_question.get("study_area")
    )

    missing_calibration_inputs = _missing_items(
        required_calibration_inputs,
        provided_calibration_inputs,
    )
    missing_validation_targets = _missing_items(
        required_validation_targets,
        provided_validation_targets,
    )

    blockers: list[str] = []
    if not model_year:
        blockers.append("model_year_missing")
    if not calibration_geography:
        blockers.append("calibration_geography_missing")
    if not method_notes:
        blockers.append("method_notes_missing")
    if not provided_calibration_inputs:
        blockers.append("calibration_inputs_missing")
    if not provided_validation_targets:
        blockers.append("validation_targets_missing")
    if missing_calibration_inputs:
        blockers.append(
            "missing_calibration_inputs:"
            + ",".join(item["id"] for item in missing_calibration_inputs)
        )
    if missing_validation_targets:
        blockers.append(
            "missing_validation_targets:"
            + ",".join(item["id"] for item in missing_validation_targets)
        )

    has_project_specific_evidence = bool(
        model_year
        or calibration_geography
        or method_notes
        or provided_calibration_inputs
        or provided_validation_targets
    )
    status = (
        "handoff_only"
        if not has_project_specific_evidence
        else "validation_ready"
        if not blockers
        else "calibration_required"
    )
    return {
        "bridge": bridge_id,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "authoritative_forecast_ready": status == "validation_ready",
        "model_year": model_year,
        "calibration_geography": calibration_geography,
        "method_notes": method_notes,
        "required_calibration_inputs": required_calibration_inputs,
        "provided_calibration_inputs": provided_calibration_inputs,
        "missing_calibration_inputs": missing_calibration_inputs,
        "required_validation_targets": required_validation_targets,
        "provided_validation_targets": provided_validation_targets,
        "missing_validation_targets": missing_validation_targets,
        "missing_readiness_blockers": blockers,
        "summary": _readiness_summary(bridge_id, status, blockers),
        "limitations": _readiness_limitations(status, bridge_id, blockers),
    }


def discover_local_calibration_evidence(
    receipt: dict[str, Any] | None,
    bridge_id: str,
) -> dict[str, list[Any]]:
    if not receipt:
        return {
            "provided_calibration_inputs": [],
            "provided_validation_targets": [],
            "method_notes": [],
        }

    provided_calibration_inputs: list[dict[str, Any]] = []
    provided_validation_targets: list[dict[str, Any]] = []
    method_notes: list[str] = []

    for item in receipt.get("inputs", []):
        if not isinstance(item, dict):
            continue
        candidate_path = _artifact_path_label(item)
        lower_name = candidate_path.name.lower()
        if _is_method_note(lower_name):
            method_notes.append(f"Local note staged: {candidate_path.name}")
        if _is_validation_target(lower_name):
            provided_validation_targets.append(
                {
                    "id": _evidence_id(candidate_path.stem),
                    "label": candidate_path.name,
                    "path": str(candidate_path),
                    "source": "staged_input",
                }
            )
        if _is_calibration_input(lower_name, bridge_id):
            provided_calibration_inputs.append(
                {
                    "id": _evidence_id(candidate_path.stem),
                    "label": candidate_path.name,
                    "path": str(candidate_path),
                    "source": "staged_input",
                }
            )

    return {
        "provided_calibration_inputs": _dedupe_items(provided_calibration_inputs),
        "provided_validation_targets": _dedupe_items(provided_validation_targets),
        "method_notes": _dedupe_strings(method_notes),
    }


def _load_question(workspace: Path) -> dict[str, Any]:
    analysis_plan_path = workspace / "analysis_plan.json"
    if not analysis_plan_path.exists():
        return {}
    return read_json(analysis_plan_path).get("question", {}) or {}


def _load_receipt_optional(workspace: Path) -> dict[str, Any] | None:
    receipt_path = workspace / "intake_receipt.json"
    if receipt_path.exists():
        return read_json(receipt_path)
    try:
        return load_receipt(workspace)
    except Exception:
        return None


def _engine_config(question: dict[str, Any], bridge_id: str) -> dict[str, Any]:
    detailed_engines = question.get("detailed_engines")
    if isinstance(detailed_engines, dict):
        entry = detailed_engines.get(bridge_id)
        if isinstance(entry, dict):
            return entry
    detailed_readiness = question.get("detailed_engine_readiness")
    if isinstance(detailed_readiness, dict):
        entry = detailed_readiness.get(bridge_id)
        if isinstance(entry, dict):
            return entry
    return {}


def _normalize_items(
    raw: Any,
    *,
    fallback: list[dict[str, str]] | None = None,
    kind: str,
) -> list[dict[str, Any]]:
    if raw is None:
        raw = fallback or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raw = fallback or []

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            label = item.strip()
            if not label:
                continue
            items.append({"id": _evidence_id(label), "label": label, "kind": kind})
            continue
        if not isinstance(item, dict):
            continue
        label = _string_or_none(
            item.get("label")
            or item.get("name")
            or item.get("metric")
            or item.get("id")
            or item.get("path")
        )
        if not label:
            label = f"{kind}_{index + 1}"
        normalized = {
            "id": _string_or_none(item.get("id")) or _evidence_id(label),
            "label": label,
            "kind": kind,
        }
        for field in ("metric", "path", "source", "notes", "target", "units"):
            value = _string_or_none(item.get(field))
            if value:
                normalized[field] = value
        items.append(normalized)
    return _dedupe_items(items)


def _missing_items(
    required: list[dict[str, Any]],
    provided: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provided_ids = {str(item.get("id", "")).strip() for item in provided}
    return [item for item in required if str(item.get("id", "")).strip() not in provided_ids]


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id", "")).strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _normalize_strings(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _readiness_summary(bridge_id: str, status: str, blockers: list[str]) -> str:
    if status == "validation_ready":
        return (
            f"{bridge_id} has project-specific calibration inputs, validation targets, and "
            "method notes recorded. Review executed model outputs before treating them as "
            "forecast-ready."
        )
    if status == "calibration_required":
        return (
            f"{bridge_id} has some project-specific readiness evidence recorded, but "
            f"{len(blockers)} blocker(s) still prevent forecast-ready claims."
        )
    return (
        f"{bridge_id} is currently a handoff package only. ClawModeler does not have "
        "project-specific calibration and validation evidence recorded for authoritative "
        "forecast claims."
    )


def _readiness_limitations(status: str, bridge_id: str, blockers: list[str]) -> list[str]:
    if status == "validation_ready":
        return [
            (
                f"{bridge_id} readiness evidence is recorded, but authoritative forecast "
                "language still depends on executing the external model and reviewing the "
                "results under project QA."
            )
        ]
    if status == "calibration_required":
        return [
            (
                f"{bridge_id} package validation can pass while forecast readiness remains "
                "blocked. Resolve the missing readiness blockers before presenting external "
                "engine outputs as detailed forecasts."
            )
        ]
    return [
        (
            f"{bridge_id} artifacts are suitable for bridge handoff and package validation, "
            "not for authoritative detailed-forecast claims."
        )
    ]


def _artifact_path_label(item: dict[str, Any]) -> Path:
    staged = _string_or_none(item.get("staged_path"))
    source = _string_or_none(item.get("source_path"))
    return Path(staged or source or "unknown")


def _is_method_note(lower_name: str) -> bool:
    return any(token in lower_name for token in ("method_note", "method-notes", "calibration_note"))


def _is_validation_target(lower_name: str) -> bool:
    return any(token in lower_name for token in ("validation", "benchmark", "target"))


def _is_calibration_input(lower_name: str, bridge_id: str) -> bool:
    common_tokens = ("observed", "count", "counts", "ridership", "boarding", "travel_time")
    if any(token in lower_name for token in common_tokens):
        return True
    if bridge_id in {"sumo", "dtalite"} and any(
        token in lower_name for token in ("signal", "timing", "queue", "delay")
    ):
        return True
    if bridge_id == "matsim" and any(
        token in lower_name for token in ("screenline", "mode_share", "survey", "od")
    ):
        return True
    if bridge_id == "urbansim" and any(
        token in lower_name for token in ("household_control", "job_control", "land_use")
    ):
        return True
    return False


def _evidence_id(text: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in text.lower()).strip("_")


__all__ = [
    "DETAILED_ENGINE_IDS",
    "build_bridge_forecast_readiness",
    "build_detailed_engine_readiness",
    "discover_local_calibration_evidence",
]
