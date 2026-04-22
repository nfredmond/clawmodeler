from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_VERSION = "1.0.0"

WORKSPACE_DIRS = (
    "inputs",
    "cache/graphs",
    "cache/gtfs",
    "runs",
    "reports",
    "logs",
)

WORKSPACE_INDEX_SCHEMA_VERSION = "1.0.0"

WORKSPACE_INDEX_TABLES = (
    "workspace_inputs",
    "import_validation",
    "runs",
    "run_artifacts",
    "run_qa",
    "bridge_readiness",
    "portfolio_runs",
    "run_diffs",
)


class ClawModelerError(Exception):
    exit_code = 1


class InputValidationError(ClawModelerError):
    exit_code = 10


class InsufficientDataError(ClawModelerError):
    exit_code = 30


class QaGateBlockedError(ClawModelerError):
    exit_code = 40


@dataclass(frozen=True)
class InputArtifact:
    source_path: str
    staged_path: str
    kind: str
    sha256: str
    rows: int | None = None
    zone_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "staged_path": self.staged_path,
            "kind": self.kind,
            "sha256": self.sha256,
            "rows": self.rows,
            "zone_ids": list(self.zone_ids),
            "warnings": list(self.warnings),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise InputValidationError(f"{path} must contain a JSON object")
    return data


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError, InputValidationError):
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_workspace(workspace: Path) -> dict[str, str]:
    workspace.mkdir(parents=True, exist_ok=True)
    for relative in WORKSPACE_DIRS:
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    database_status = ensure_project_database(workspace / "project.duckdb")
    return {
        "root": str(workspace),
        "project_database": str(workspace / "project.duckdb"),
        "database_status": database_status,
    }


def ensure_project_database(path: Path) -> str:
    try:
        import duckdb  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        write_json(
            path.with_suffix(".duckdb.missing-dependency.json"),
            {
                "created_at": utc_now(),
                "status": "duckdb_python_module_missing",
                "message": "Install the duckdb Python package to create project.duckdb.",
            },
        )
        return "duckdb_python_module_missing"

    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS zones (
              zone_id VARCHAR PRIMARY KEY,
              name VARCHAR,
              source_crs VARCHAR,
              ingested_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS socio (
              zone_id VARCHAR,
              base_year INTEGER,
              population DOUBLE,
              jobs DOUBLE,
              source_file VARCHAR
            );
            CREATE TABLE IF NOT EXISTS scenarios (
              scenario_id VARCHAR,
              name VARCHAR,
              created_at TIMESTAMP,
              transform_spec_json JSON
            );
            CREATE TABLE IF NOT EXISTS fact_blocks (
              fact_id VARCHAR,
              fact_type VARCHAR,
              claim_text VARCHAR,
              artifact_refs_json JSON,
              scenario_id VARCHAR,
              created_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
              project_id VARCHAR,
              name VARCHAR,
              safety DOUBLE,
              equity DOUBLE,
              climate DOUBLE,
              feasibility DOUBLE,
              source_file VARCHAR,
              ingested_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS network_edges (
              from_zone_id VARCHAR,
              to_zone_id VARCHAR,
              minutes DOUBLE,
              directed BOOLEAN,
              source_file VARCHAR,
              ingested_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS zone_node_map (
              zone_id VARCHAR,
              node_id VARCHAR,
              distance_km DOUBLE,
              source_file VARCHAR,
              ingested_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_scenarios (
              run_id VARCHAR,
              scenario_id VARCHAR,
              name VARCHAR,
              population_multiplier DOUBLE,
              jobs_multiplier DOUBLE,
              transform_spec_json JSON,
              created_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_fact_blocks (
              run_id VARCHAR,
              fact_id VARCHAR,
              fact_type VARCHAR,
              claim_text VARCHAR,
              artifact_refs_json JSON,
              scenario_id VARCHAR,
              created_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS workspace_inputs (
              kind VARCHAR,
              source_path VARCHAR,
              staged_path VARCHAR,
              sha256 VARCHAR,
              row_count INTEGER,
              zone_id_count INTEGER,
              warnings_json JSON,
              ingested_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS import_validation (
              check_name VARCHAR,
              status VARCHAR,
              detail VARCHAR,
              expected_value VARCHAR,
              actual_value VARCHAR,
              created_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
              run_id VARCHAR PRIMARY KEY,
              created_at TIMESTAMP,
              engine_version VARCHAR,
              scenario_count INTEGER,
              base_run_id VARCHAR,
              manifest_path VARCHAR,
              workflow_report_path VARCHAR,
              report_path VARCHAR,
              export_ready BOOLEAN,
              qa_blockers_json JSON,
              planner_pack_artifacts_json JSON,
              bridge_execution_report_count INTEGER,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_artifacts (
              run_id VARCHAR,
              artifact_category VARCHAR,
              artifact_name VARCHAR,
              path VARCHAR,
              suffix VARCHAR,
              size_bytes BIGINT,
              sha256 VARCHAR,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_qa (
              run_id VARCHAR PRIMARY KEY,
              export_ready BOOLEAN,
              fact_block_count INTEGER,
              blockers_json JSON,
              checks_json JSON,
              qa_report_path VARCHAR,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS bridge_readiness (
              run_id VARCHAR,
              bridge VARCHAR,
              package_status VARCHAR,
              forecast_status VARCHAR,
              forecast_status_label VARCHAR,
              validation_ready BOOLEAN,
              structural_ready BOOLEAN,
              blockers_json JSON,
              execution_status VARCHAR,
              execution_ready BOOLEAN,
              validation_report_path VARCHAR,
              execution_report_path VARCHAR,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_runs (
              run_id VARCHAR PRIMARY KEY,
              engine_version VARCHAR,
              created_at TIMESTAMP,
              base_run_id VARCHAR,
              scenario_count INTEGER,
              project_count INTEGER,
              mean_total_score DOUBLE,
              top_project_id VARCHAR,
              top_project_name VARCHAR,
              top_project_score DOUBLE,
              vmt_flagged_count INTEGER,
              dac_share DOUBLE,
              fact_block_count INTEGER,
              export_ready BOOLEAN,
              qa_blockers_json JSON,
              planner_pack_artifacts_json JSON,
              has_what_if_overrides BOOLEAN,
              source_path VARCHAR,
              generated_at TIMESTAMP,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS run_diffs (
              run_a_id VARCHAR,
              run_b_id VARCHAR,
              report_path VARCHAR,
              csv_path VARCHAR,
              json_path VARCHAR,
              totals_json JSON,
              generated_at TIMESTAMP,
              updated_at TIMESTAMP
            );
            """
        )
    finally:
        connection.close()
    return "ready"


def sync_project_database(
    workspace: Path,
    *,
    receipt: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> str:
    status = ensure_project_database(workspace / "project.duckdb")
    if status != "ready":
        return status

    try:
        import duckdb  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return "duckdb_python_module_missing"

    connection = duckdb.connect(str(workspace / "project.duckdb"))
    try:
        if receipt:
            sync_input_tables(connection, workspace, receipt)
        if run_id:
            sync_run_tables(connection, workspace, run_id)
        sync_workspace_index(connection, workspace, receipt=receipt)
    finally:
        connection.close()
    return "ready"


def refresh_workspace_index(workspace: Path, *, run_id: str | None = None) -> dict[str, Any]:
    """Refresh project.duckdb when available and persist a JSON index summary."""
    ensure_workspace(workspace)
    status = sync_project_database(workspace, run_id=run_id)
    summary = build_workspace_index_summary(
        workspace,
        run_id=run_id,
        database_status=status,
    )
    write_json(workspace / "logs" / "workspace_index.json", summary)
    return summary


def sync_workspace_index(
    connection: Any,
    workspace: Path,
    *,
    receipt: dict[str, Any] | None = None,
) -> None:
    """Sync workspace-level query tables from the file-backed artifacts."""
    summary = build_workspace_index_summary(
        workspace,
        receipt=receipt,
        database_status="ready",
    )
    updated_at = summary["created_at"]

    for table in WORKSPACE_INDEX_TABLES:
        connection.execute(f"DELETE FROM {table}")

    for item in summary["inputs"]:
        connection.execute(
            """
            INSERT INTO workspace_inputs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item["kind"],
                item["source_path"],
                item["staged_path"],
                item["sha256"],
                item["row_count"],
                item["zone_id_count"],
                dump_json(item["warnings"]),
                updated_at,
            ],
        )

    for check in summary["import_validation"]["checks"]:
        connection.execute(
            """
            INSERT INTO import_validation
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                check["check_name"],
                check["status"],
                check["detail"],
                check["expected_value"],
                check["actual_value"],
                updated_at,
            ],
        )

    for run in summary["runs"]:
        connection.execute(
            """
            INSERT INTO runs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run["run_id"],
                run["created_at"],
                run["engine_version"],
                run["scenario_count"],
                run["base_run_id"],
                run["manifest_path"],
                run["workflow_report_path"],
                run["report_path"],
                run["export_ready"],
                dump_json(run["qa_blockers"]),
                dump_json(run["planner_pack_artifacts"]),
                run["bridge_execution_report_count"],
                updated_at,
            ],
        )

    for artifact in summary["artifacts"]:
        connection.execute(
            """
            INSERT INTO run_artifacts
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                artifact["run_id"],
                artifact["artifact_category"],
                artifact["artifact_name"],
                artifact["path"],
                artifact["suffix"],
                artifact["size_bytes"],
                artifact["sha256"],
                updated_at,
            ],
        )

    for qa in summary["qa"]:
        connection.execute(
            """
            INSERT INTO run_qa
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                qa["run_id"],
                qa["export_ready"],
                qa["fact_block_count"],
                dump_json(qa["blockers"]),
                dump_json(qa["checks"]),
                qa["qa_report_path"],
                updated_at,
            ],
        )

    for bridge in summary["bridge_readiness"]:
        connection.execute(
            """
            INSERT INTO bridge_readiness
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                bridge["run_id"],
                bridge["bridge"],
                bridge["package_status"],
                bridge["forecast_status"],
                bridge["forecast_status_label"],
                bridge["validation_ready"],
                bridge["structural_ready"],
                dump_json(bridge["blockers"]),
                bridge["execution_status"],
                bridge["execution_ready"],
                bridge["validation_report_path"],
                bridge["execution_report_path"],
                updated_at,
            ],
        )

    for run in summary["portfolio_runs"]:
        connection.execute(
            """
            INSERT INTO portfolio_runs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run["run_id"],
                run["engine_version"],
                run["created_at"],
                run["base_run_id"],
                run["scenario_count"],
                run["project_count"],
                run["mean_total_score"],
                run["top_project_id"],
                run["top_project_name"],
                run["top_project_score"],
                run["vmt_flagged_count"],
                run["dac_share"],
                run["fact_block_count"],
                run["export_ready"],
                dump_json(run["qa_blockers"]),
                dump_json(run["planner_pack_artifacts"]),
                run["has_what_if_overrides"],
                run["source_path"],
                run["generated_at"],
                updated_at,
            ],
        )

    for diff in summary["diffs"]:
        connection.execute(
            """
            INSERT INTO run_diffs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                diff["run_a_id"],
                diff["run_b_id"],
                diff["report_path"],
                diff["csv_path"],
                diff["json_path"],
                dump_json(diff["totals"]),
                diff["generated_at"],
                updated_at,
            ],
        )


def build_workspace_index_summary(
    workspace: Path,
    *,
    receipt: dict[str, Any] | None = None,
    run_id: str | None = None,
    database_status: str = "unknown",
) -> dict[str, Any]:
    receipt = receipt or read_optional_json(workspace / "intake_receipt.json")
    inputs = workspace_input_rows(workspace, receipt)
    import_checks = build_import_validation_rows(receipt)
    all_runs = workspace_run_rows(workspace)
    selected_runs = [run for run in all_runs if run_id in (None, run["run_id"])]
    selected_run_ids = [run["run_id"] for run in selected_runs]
    artifacts = [
        artifact
        for selected_run_id in selected_run_ids
        for artifact in collect_run_artifact_rows(workspace, selected_run_id)
    ]
    qa_rows = [workspace_qa_row(workspace, selected_run_id) for selected_run_id in selected_run_ids]
    bridge_rows = [
        bridge
        for selected_run_id in selected_run_ids
        for bridge in workspace_bridge_readiness_rows(workspace, selected_run_id)
    ]
    portfolio_rows = [
        row for row in workspace_portfolio_rows(workspace) if run_id in (None, row["run_id"])
    ]
    diff_rows = [
        row
        for row in workspace_diff_rows(workspace)
        if run_id is None or run_id in {row["run_a_id"], row["run_b_id"]}
    ]
    checks = import_checks["checks"]
    return {
        "schema_version": WORKSPACE_INDEX_SCHEMA_VERSION,
        "created_at": utc_now(),
        "workspace": str(workspace),
        "project_database": str(workspace / "project.duckdb"),
        "database_status": database_status,
        "run_id": run_id,
        "tables": list(WORKSPACE_INDEX_TABLES),
        "input_count": len(inputs),
        "input_kinds": sorted({item["kind"] for item in inputs}),
        "inputs": inputs,
        "import_validation": {
            "check_count": len(checks),
            "pass_count": sum(1 for check in checks if check["status"] == "pass"),
            "warning_count": sum(1 for check in checks if check["status"] == "warn"),
            "checks": checks,
        },
        "run_count": len(selected_runs),
        "runs": selected_runs,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "qa": qa_rows,
        "bridge_readiness_count": len(bridge_rows),
        "bridge_readiness": bridge_rows,
        "portfolio_run_count": len(portfolio_rows),
        "portfolio_runs": portfolio_rows,
        "diff_count": len(diff_rows),
        "diffs": diff_rows,
    }


def dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def workspace_input_rows(
    workspace: Path,
    receipt: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not receipt:
        return []
    rows: list[dict[str, Any]] = []
    for item in receipt.get("inputs", []):
        if not isinstance(item, dict):
            continue
        staged_path = resolve_workspace_path(workspace, receipt, item.get("staged_path"))
        rows.append(
            {
                "kind": str(item.get("kind", "unknown")),
                "source_path": str(item.get("source_path", "")),
                "staged_path": str(staged_path),
                "sha256": str(item.get("sha256", "")),
                "row_count": optional_int(item.get("rows")),
                "zone_id_count": len(item.get("zone_ids", []) or []),
                "warnings": [str(warning) for warning in item.get("warnings", []) or []],
            }
        )
    return rows


def build_import_validation_rows(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt:
        return {
            "checks": [
                {
                    "check_name": "intake_receipt_present",
                    "status": "warn",
                    "detail": "No intake_receipt.json found in the workspace.",
                    "expected_value": "intake_receipt.json",
                    "actual_value": "missing",
                }
            ]
        }

    inputs = [item for item in receipt.get("inputs", []) if isinstance(item, dict)]
    checks: list[dict[str, Any]] = [
        {
            "check_name": "intake_receipt_present",
            "status": "pass",
            "detail": "Workspace intake receipt is available.",
            "expected_value": "intake_receipt.json",
            "actual_value": "present",
        },
        {
            "check_name": "input_count",
            "status": "pass" if inputs else "warn",
            "detail": "Number of staged input artifacts recorded in the receipt.",
            "expected_value": ">0",
            "actual_value": str(len(inputs)),
        },
    ]

    validation = receipt.get("validation")
    if isinstance(validation, dict):
        zone_present = bool(validation.get("zone_id_present"))
        checks.append(
            {
                "check_name": "zone_id_present",
                "status": "pass" if zone_present else "warn",
                "detail": "At least one staged input includes zone IDs.",
                "expected_value": "true",
                "actual_value": str(zone_present).lower(),
            }
        )
        if validation.get("join_coverage_threshold"):
            checks.append(
                {
                    "check_name": "join_coverage_threshold",
                    "status": "pass",
                    "detail": "Configured minimum join coverage for zone-linked tables.",
                    "expected_value": ">=95%",
                    "actual_value": str(validation["join_coverage_threshold"]),
                }
            )

    checks.extend(socio_join_validation_checks(inputs))
    for item in inputs:
        warnings = [str(warning) for warning in item.get("warnings", []) or []]
        if warnings:
            checks.append(
                {
                    "check_name": f"input_warnings:{item.get('kind', 'unknown')}",
                    "status": "warn",
                    "detail": "; ".join(warnings),
                    "expected_value": "no warnings",
                    "actual_value": str(len(warnings)),
                }
            )
    return {"checks": checks}


def socio_join_validation_checks(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones = next((item for item in inputs if item.get("kind") == "zones_geojson"), None)
    if not zones:
        return []

    zone_ids = {str(zone_id) for zone_id in zones.get("zone_ids", []) or []}
    checks: list[dict[str, Any]] = []
    for socio in (item for item in inputs if item.get("kind") == "socio_csv"):
        socio_zone_ids = {str(zone_id) for zone_id in socio.get("zone_ids", []) or []}
        matched = zone_ids & socio_zone_ids
        extra_socio = sorted(socio_zone_ids - zone_ids)
        missing_socio = sorted(zone_ids - socio_zone_ids)
        socio_coverage = len(matched) / len(socio_zone_ids) if socio_zone_ids else 0.0
        zone_coverage = len(matched) / len(zone_ids) if zone_ids else 0.0
        coverage = min(socio_coverage, zone_coverage)
        status = "pass" if coverage >= 0.95 and not extra_socio and not missing_socio else "warn"
        checks.append(
            {
                "check_name": "socio_join_coverage",
                "status": status,
                "detail": (
                    f"{len(matched)} matched zone(s), {len(extra_socio)} extra socio "
                    f"zone(s), {len(missing_socio)} GeoJSON zone(s) without socio rows."
                ),
                "expected_value": ">=95% coverage in both directions",
                "actual_value": f"{coverage:.1%}",
            }
        )
    return checks


def workspace_run_rows(workspace: Path) -> list[dict[str, Any]]:
    runs = list_workspace_run_summaries(workspace)
    rows: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("run_id", ""))
        if not run_id:
            continue
        rows.append(
            {
                "run_id": run_id,
                "created_at": run.get("created_at"),
                "engine_version": run.get("engine_version"),
                "scenario_count": optional_int(run.get("scenario_count")) or 0,
                "base_run_id": run.get("base_run_id"),
                "manifest_path": str(workspace / "runs" / run_id / "manifest.json"),
                "workflow_report_path": existing_path(
                    workspace / "runs" / run_id / "workflow_report.json"
                ),
                "report_path": report_path_for_run(workspace, run_id),
                "export_ready": bool(run.get("export_ready")),
                "qa_blockers": list(run.get("qa_blockers", []) or []),
                "planner_pack_artifacts": list(run.get("planner_pack_artifacts", []) or []),
                "bridge_execution_report_count": len(
                    list(
                        (workspace / "runs" / run_id / "outputs" / "bridges").glob(
                            "*/bridge_execution_report.json"
                        )
                    )
                ),
            }
        )
    return rows


def list_workspace_run_summaries(workspace: Path) -> list[dict[str, Any]]:
    try:
        from .portfolio import list_runs
    except ImportError:
        return []

    try:
        return [run.to_json() for run in list_runs(workspace)]
    except ClawModelerError:
        return []


def collect_run_artifact_rows(workspace: Path, run_id: str) -> list[dict[str, Any]]:
    run_root = workspace / "runs" / run_id
    paths: list[Path] = []
    if run_root.exists():
        paths.extend(sorted(path for path in run_root.rglob("*") if path.is_file()))
    reports_dir = workspace / "reports"
    if reports_dir.exists():
        paths.extend(sorted(path for path in reports_dir.glob(f"{run_id}_*") if path.is_file()))

    rows: list[dict[str, Any]] = []
    for path in unique_paths(paths):
        try:
            size_bytes = path.stat().st_size
            checksum = sha256_file(path)
        except OSError:
            continue
        rows.append(
            {
                "run_id": run_id,
                "artifact_category": artifact_category(workspace, run_root, path),
                "artifact_name": path.name,
                "path": str(path),
                "suffix": path.suffix,
                "size_bytes": size_bytes,
                "sha256": checksum,
            }
        )
    return rows


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def artifact_category(workspace: Path, run_root: Path, path: Path) -> str:
    reports_dir = workspace / "reports"
    try:
        path.relative_to(reports_dir)
        return "report"
    except ValueError:
        pass

    try:
        relative = path.relative_to(run_root)
    except ValueError:
        return "artifact"
    parts = relative.parts
    if not parts:
        return "artifact"
    if parts[0] == "manifest.json":
        return "manifest"
    if parts[0] == "qa_report.json":
        return "qa"
    if parts[0] == "workflow_report.json":
        return "workflow"
    if parts[:2] == ("outputs", "tables"):
        return "table"
    if parts[:2] == ("outputs", "maps"):
        return "map"
    if parts[:2] == ("outputs", "figures"):
        return "figure"
    if parts[:2] == ("outputs", "bridges"):
        return "bridge"
    if parts[0] == "logs":
        return "log"
    return "artifact"


def workspace_qa_row(workspace: Path, run_id: str) -> dict[str, Any]:
    qa_report_path = workspace / "runs" / run_id / "qa_report.json"
    qa = read_optional_json(qa_report_path) or {}
    checks = qa.get("checks") if isinstance(qa.get("checks"), dict) else {}
    fact_block_count = optional_int(checks.get("fact_block_count")) if checks else 0
    return {
        "run_id": run_id,
        "export_ready": bool(qa.get("export_ready")) if qa else False,
        "fact_block_count": fact_block_count or 0,
        "blockers": list(qa.get("blockers", []) or []) if qa else [],
        "checks": checks,
        "qa_report_path": str(qa_report_path) if qa_report_path.exists() else None,
    }


def workspace_bridge_readiness_rows(workspace: Path, run_id: str) -> list[dict[str, Any]]:
    run_root = workspace / "runs" / run_id
    manifest = read_optional_json(run_root / "manifest.json") or {}
    detailed = manifest.get("detailed_engine_readiness")
    engines = detailed.get("engines", {}) if isinstance(detailed, dict) else {}
    if not isinstance(engines, dict):
        engines = {}

    validation_path = run_root / "outputs" / "bridges" / "bridge_validation_report.json"
    validation = read_optional_json(validation_path) or {}
    raw_validation_bridges = validation.get("bridges") if isinstance(validation, dict) else []
    validation_bridges = (
        raw_validation_bridges if isinstance(raw_validation_bridges, list) else []
    )
    validation_by_bridge = {
        str(item.get("bridge")): item
        for item in validation_bridges
        if isinstance(item, dict) and item.get("bridge")
    }

    execution_by_bridge: dict[str, dict[str, Any]] = {}
    bridges_root = run_root / "outputs" / "bridges"
    if bridges_root.exists():
        for path in sorted(bridges_root.glob("*/bridge_execution_report.json")):
            report = read_optional_json(path)
            if not report:
                continue
            bridge = str(report.get("bridge") or path.parent.name)
            execution_by_bridge[bridge] = {**report, "_path": str(path)}

    bridge_names = sorted(set(engines) | set(validation_by_bridge) | set(execution_by_bridge))
    rows: list[dict[str, Any]] = []
    for bridge in bridge_names:
        readiness = engines.get(bridge, {}) if isinstance(engines.get(bridge), dict) else {}
        validation_row = validation_by_bridge.get(bridge, {})
        forecast = (
            validation_row.get("forecast_readiness")
            if isinstance(validation_row.get("forecast_readiness"), dict)
            else readiness
        )
        execution = execution_by_bridge.get(bridge, {})
        blockers = bridge_blockers(validation_row, forecast, execution)
        forecast_status = forecast.get("status") if isinstance(forecast, dict) else None
        if isinstance(forecast, dict):
            validation_ready = (
                bool(forecast.get("authoritative_forecast_ready"))
                or forecast_status == "validation_ready"
            )
        else:
            validation_ready = forecast_status == "validation_ready"
        rows.append(
            {
                "run_id": run_id,
                "bridge": bridge,
                "package_status": validation_row.get("status") or readiness.get("status"),
                "forecast_status": forecast_status,
                "forecast_status_label": (
                    forecast.get("status_label") if isinstance(forecast, dict) else None
                ),
                "validation_ready": validation_ready,
                "structural_ready": validation_row.get("ready"),
                "blockers": blockers,
                "execution_status": execution.get("status"),
                "execution_ready": execution.get("execution_ready"),
                "validation_report_path": str(validation_path) if validation_path.exists() else None,
                "execution_report_path": execution.get("_path"),
            }
        )
    return rows


def bridge_blockers(
    validation_row: dict[str, Any],
    forecast: dict[str, Any] | None,
    execution: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for key in ("blockers", "structural_blockers", "forecast_blockers"):
        raw = validation_row.get(key)
        if isinstance(raw, list):
            blockers.extend(str(item) for item in raw)
    if isinstance(forecast, dict):
        raw = forecast.get("missing_readiness_blockers")
        if isinstance(raw, list):
            blockers.extend(str(item) for item in raw)
    raw_execution = execution.get("blockers")
    if isinstance(raw_execution, list):
        blockers.extend(str(item) for item in raw_execution)
    return sorted(set(blockers))


def workspace_portfolio_rows(workspace: Path) -> list[dict[str, Any]]:
    source_path = workspace / "portfolio" / "summary.json"
    data = read_optional_json(source_path)
    generated_at = data.get("generated_at") if data else None
    raw_runs = data.get("runs") if isinstance(data, dict) else None
    runs = raw_runs if isinstance(raw_runs, list) else list_workspace_run_summaries(workspace)
    rows: list[dict[str, Any]] = []
    for raw_run in runs:
        if not isinstance(raw_run, dict) or not raw_run.get("run_id"):
            continue
        rows.append(
            {
                "run_id": str(raw_run["run_id"]),
                "engine_version": raw_run.get("engine_version"),
                "created_at": raw_run.get("created_at"),
                "base_run_id": raw_run.get("base_run_id"),
                "scenario_count": optional_int(raw_run.get("scenario_count")) or 0,
                "project_count": optional_int(raw_run.get("project_count")) or 0,
                "mean_total_score": optional_float(raw_run.get("mean_total_score")),
                "top_project_id": raw_run.get("top_project_id"),
                "top_project_name": raw_run.get("top_project_name"),
                "top_project_score": optional_float(raw_run.get("top_project_score")),
                "vmt_flagged_count": optional_int(raw_run.get("vmt_flagged_count")) or 0,
                "dac_share": optional_float(raw_run.get("dac_share")),
                "fact_block_count": optional_int(raw_run.get("fact_block_count")) or 0,
                "export_ready": bool(raw_run.get("export_ready")),
                "qa_blockers": list(raw_run.get("qa_blockers", []) or []),
                "planner_pack_artifacts": list(raw_run.get("planner_pack_artifacts", []) or []),
                "has_what_if_overrides": bool(raw_run.get("has_what_if_overrides")),
                "source_path": str(source_path) if source_path.exists() else None,
                "generated_at": generated_at,
            }
        )
    return rows


def workspace_diff_rows(workspace: Path) -> list[dict[str, Any]]:
    diffs_root = workspace / "diffs"
    rows: list[dict[str, Any]] = []
    if not diffs_root.exists():
        return rows
    for path in sorted(diffs_root.glob("*/diff.json")):
        data = read_optional_json(path)
        if not data:
            continue
        run_a_id = str(data.get("run_a_id", ""))
        run_b_id = str(data.get("run_b_id", ""))
        if not run_a_id or not run_b_id:
            continue
        rows.append(
            {
                "run_a_id": run_a_id,
                "run_b_id": run_b_id,
                "report_path": str(workspace / "reports" / f"{run_a_id}_vs_{run_b_id}_diff.md"),
                "csv_path": str(path.parent / "diff.csv"),
                "json_path": str(path),
                "totals": diff_totals(data),
                "generated_at": data.get("generated_at"),
            }
        )
    return rows


def diff_totals(data: dict[str, Any]) -> dict[str, int]:
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        return {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    artifact_dicts = [item for item in artifacts if isinstance(item, dict)]
    return {
        "added": sum(optional_int(item.get("added_count")) or 0 for item in artifact_dicts),
        "removed": sum(optional_int(item.get("removed_count")) or 0 for item in artifact_dicts),
        "changed": sum(optional_int(item.get("changed_count")) or 0 for item in artifact_dicts),
        "unchanged": sum(
            optional_int(item.get("unchanged_count")) or 0 for item in artifact_dicts
        ),
    }


def report_path_for_run(workspace: Path, run_id: str) -> str | None:
    reports_dir = workspace / "reports"
    preferred = reports_dir / f"{run_id}_report.md"
    if preferred.exists():
        return str(preferred)
    if not reports_dir.exists():
        return None
    matches = sorted(path for path in reports_dir.glob(f"{run_id}_report*") if path.is_file())
    return str(matches[0]) if matches else None


def existing_path(path: Path) -> str | None:
    return str(path) if path.exists() else None


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def sync_input_tables(connection: Any, workspace: Path, receipt: dict[str, Any]) -> None:
    ingested_at = utc_now()
    for table in ("zones", "socio", "projects", "network_edges", "zone_node_map"):
        connection.execute(f"DELETE FROM {table}")

    for item in receipt.get("inputs", []):
        kind = item.get("kind")
        path = resolve_workspace_path(workspace, receipt, item.get("staged_path"))
        if not path.exists():
            continue
        if kind == "zones_geojson":
            sync_zones_table(connection, path, ingested_at)
        elif kind == "socio_csv":
            sync_socio_table(connection, path, ingested_at)
        elif kind == "candidate_projects_csv":
            sync_projects_table(connection, path, ingested_at)
        elif kind == "network_edges_csv":
            sync_network_edges_table(connection, path, ingested_at)
        elif kind == "zone_node_map_csv":
            sync_zone_node_map_table(connection, path, ingested_at)


def sync_run_tables(connection: Any, workspace: Path, run_id: str) -> None:
    run_root = workspace / "runs" / run_id
    scenario_path = run_root / "outputs" / "tables" / "scenario_diff_summary.csv"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    created_at = utc_now()

    connection.execute("DELETE FROM run_scenarios WHERE run_id = ?", [run_id])
    connection.execute("DELETE FROM run_fact_blocks WHERE run_id = ?", [run_id])

    if scenario_path.exists():
        for row in read_csv_rows(scenario_path):
            connection.execute(
                """
                INSERT INTO run_scenarios
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    str(row.get("scenario_id", "")),
                    str(row.get("name", "")),
                    parse_number(row.get("population_multiplier"), 1.0),
                    parse_number(row.get("jobs_multiplier"), 1.0),
                    row.get("zone_adjustments_json") or "{}",
                    created_at,
                ],
            )

    if fact_blocks_path.exists():
        with fact_blocks_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                block = json.loads(line)
                connection.execute(
                    """
                    INSERT INTO run_fact_blocks
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        str(block.get("fact_id", "")),
                        str(block.get("fact_type", "")),
                        str(block.get("claim_text", "")),
                        json.dumps(block.get("artifact_refs", []), sort_keys=True),
                        str(block.get("scenario_id", "")),
                        str(block.get("created_at") or created_at),
                    ],
                )


def sync_zones_table(connection: Any, path: Path, ingested_at: str) -> None:
    data = read_json(path)
    crs = data.get("crs") if isinstance(data.get("crs"), dict) else {}
    crs_properties = crs.get("properties") if isinstance(crs.get("properties"), dict) else {}
    for feature in data.get("features", []):
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        zone_id = str(properties.get("zone_id", "")).strip()
        if not zone_id:
            continue
        connection.execute(
            "INSERT INTO zones VALUES (?, ?, ?, ?)",
            [
                zone_id,
                str(properties.get("name") or zone_id),
                str(crs_properties.get("name", "")),
                ingested_at,
            ],
        )


def sync_socio_table(connection: Any, path: Path, ingested_at: str) -> None:
    for row in read_csv_rows(path):
        connection.execute(
            "INSERT INTO socio VALUES (?, ?, ?, ?, ?)",
            [
                str(row.get("zone_id", "")).strip(),
                int(parse_number(row.get("base_year"), 2020)),
                parse_number(row.get("population"), 0.0),
                parse_number(row.get("jobs"), 0.0),
                str(path),
            ],
        )


def sync_projects_table(connection: Any, path: Path, ingested_at: str) -> None:
    for row in read_csv_rows(path):
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                str(row.get("project_id", "")).strip(),
                str(row.get("name", "")),
                parse_number(row.get("safety"), 0.0),
                parse_number(row.get("equity"), 0.0),
                parse_number(row.get("climate"), 0.0),
                parse_number(row.get("feasibility"), 0.0),
                str(path),
                ingested_at,
            ],
        )


def sync_network_edges_table(connection: Any, path: Path, ingested_at: str) -> None:
    for row in read_csv_rows(path):
        connection.execute(
            "INSERT INTO network_edges VALUES (?, ?, ?, ?, ?, ?)",
            [
                str(row.get("from_zone_id", "")).strip(),
                str(row.get("to_zone_id", "")).strip(),
                parse_number(row.get("minutes"), 0.0),
                str(row.get("directed", "")).lower() in {"1", "true", "yes"},
                str(path),
                ingested_at,
            ],
        )


def sync_zone_node_map_table(connection: Any, path: Path, ingested_at: str) -> None:
    for row in read_csv_rows(path):
        connection.execute(
            "INSERT INTO zone_node_map VALUES (?, ?, ?, ?, ?)",
            [
                str(row.get("zone_id", "")).strip(),
                str(row.get("node_id", "")).strip(),
                parse_number(row.get("distance_km"), 0.0),
                str(path),
                ingested_at,
            ],
        )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def parse_number(value: object, fallback: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def resolve_workspace_path(workspace: Path, receipt: dict[str, Any], raw_path: object) -> Path:
    path = Path(str(raw_path))
    if path.is_absolute():
        return path
    receipt_root_raw = receipt.get("workspace", {}).get("root")
    if receipt_root_raw:
        receipt_root = Path(str(receipt_root_raw))
        if not receipt_root.is_absolute():
            try:
                return workspace / path.relative_to(receipt_root)
            except ValueError:
                pass
    return workspace / path


def stage_inputs(workspace: Path, input_paths: list[Path]) -> list[InputArtifact]:
    if not input_paths:
        raise InputValidationError("At least one input file is required.")

    ensure_workspace(workspace)
    staged: list[InputArtifact] = []
    for input_path in input_paths:
        if not input_path.exists() or not input_path.is_file():
            raise InputValidationError(f"Input file not found: {input_path}")
        target = unique_target(workspace / "inputs", input_path.name)
        shutil.copy2(input_path, target)
        staged.append(describe_input(input_path, target))

    validate_join_coverage(staged)
    return staged


def unique_target(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def describe_input(source_path: Path, staged_path: Path) -> InputArtifact:
    suffix = staged_path.suffix.lower()
    if suffix == ".csv":
        return describe_csv(source_path, staged_path)
    if suffix in {".json", ".geojson"}:
        return describe_geojson(source_path, staged_path)
    if suffix == ".zip":
        return InputArtifact(
            source_path=str(source_path),
            staged_path=str(staged_path),
            kind="gtfs_zip",
            sha256=sha256_file(staged_path),
        )
    if suffix == ".shp":
        return InputArtifact(
            source_path=str(source_path),
            staged_path=str(staged_path),
            kind="shapefile",
            sha256=sha256_file(staged_path),
            warnings=("Shapefile sidecar files must be staged with matching basename.",),
        )
    return InputArtifact(
        source_path=str(source_path),
        staged_path=str(staged_path),
        kind="unknown",
        sha256=sha256_file(staged_path),
        warnings=("Unsupported extension staged for audit only.",),
    )


def describe_csv(source_path: Path, staged_path: Path) -> InputArtifact:
    with staged_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise InputValidationError(f"CSV has no header row: {source_path}")
        rows = list(reader)

    zone_ids: tuple[str, ...] = ()
    kind = "csv"
    warnings: list[str] = []
    if {"zone_id", "node_id"}.issubset(set(reader.fieldnames)):
        kind = "zone_node_map_csv"
        zone_ids = validate_zone_node_map_csv(rows, source_path)
    elif {"from_zone_id", "to_zone_id", "minutes"}.issubset(set(reader.fieldnames)):
        kind = "network_edges_csv"
        zone_ids, network_warnings = validate_network_edges_csv(rows, source_path)
        warnings.extend(network_warnings)
    elif "project_id" in reader.fieldnames:
        kind = "candidate_projects_csv"
    elif "zone_id" in reader.fieldnames:
        zone_values = [str(row.get("zone_id", "")).strip() for row in rows]
        missing = [index + 2 for index, value in enumerate(zone_values) if not value]
        if missing:
            raise InputValidationError(f"CSV has missing zone_id values on rows: {missing}")
        zone_ids = tuple(sorted(set(zone_values)))
        kind = "socio_csv"
    else:
        warnings.append("CSV does not include zone_id; it cannot join to zones without mapping.")

    return InputArtifact(
        source_path=str(source_path),
        staged_path=str(staged_path),
        kind=kind,
        sha256=sha256_file(staged_path),
        rows=len(rows),
        zone_ids=zone_ids,
        warnings=tuple(warnings),
    )


def validate_zone_node_map_csv(rows: list[dict[str, str]], source_path: Path) -> tuple[str, ...]:
    if not rows:
        raise InputValidationError(f"zone_node_map.csv has no rows: {source_path}")

    zone_ids: list[str] = []
    missing_rows: list[int] = []
    for index, row in enumerate(rows, start=2):
        zone_id = str(row.get("zone_id", "")).strip()
        node_id = str(row.get("node_id", "")).strip()
        if not zone_id or not node_id:
            missing_rows.append(index)
            continue
        zone_ids.append(zone_id)

    if missing_rows:
        raise InputValidationError(
            f"zone_node_map.csv has missing zone_id or node_id values on rows: {missing_rows}"
        )
    if len(zone_ids) != len(set(zone_ids)):
        raise InputValidationError("zone_node_map.csv zone_id values must be unique.")
    return tuple(sorted(zone_ids))


def validate_network_edges_csv(
    rows: list[dict[str, str]], source_path: Path
) -> tuple[tuple[str, ...], list[str]]:
    if not rows:
        raise InputValidationError(f"network_edges.csv has no rows: {source_path}")

    endpoint_ids: list[str] = []
    missing_endpoint_rows: list[int] = []
    invalid_minute_rows: list[int] = []
    self_loop_rows: list[int] = []
    for index, row in enumerate(rows, start=2):
        from_zone_id = str(row.get("from_zone_id", "")).strip()
        to_zone_id = str(row.get("to_zone_id", "")).strip()
        if not from_zone_id or not to_zone_id:
            missing_endpoint_rows.append(index)
        else:
            endpoint_ids.extend([from_zone_id, to_zone_id])
            if from_zone_id == to_zone_id:
                self_loop_rows.append(index)

        minutes = parse_number(row.get("minutes"), math.inf)
        if not math.isfinite(minutes) or minutes <= 0:
            invalid_minute_rows.append(index)

    if missing_endpoint_rows:
        raise InputValidationError(
            "network_edges.csv has missing from_zone_id or to_zone_id values on rows: "
            f"{missing_endpoint_rows}"
        )
    if invalid_minute_rows:
        raise InputValidationError(
            "network_edges.csv has invalid minutes values on rows: "
            f"{invalid_minute_rows}; minutes must be positive numbers."
        )

    warnings: list[str] = []
    if self_loop_rows:
        warnings.append(f"network_edges.csv includes self-loop edges on rows: {self_loop_rows}")
    return tuple(sorted(set(endpoint_ids))), warnings


def describe_geojson(source_path: Path, staged_path: Path) -> InputArtifact:
    data = read_json(staged_path)
    if data.get("type") != "FeatureCollection":
        return InputArtifact(
            source_path=str(source_path),
            staged_path=str(staged_path),
            kind="json",
            sha256=sha256_file(staged_path),
            warnings=("JSON file is not a GeoJSON FeatureCollection.",),
        )

    features = data.get("features")
    if not isinstance(features, list):
        raise InputValidationError(f"GeoJSON features must be an array: {source_path}")

    zone_ids: list[str] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            raise InputValidationError(f"GeoJSON feature {index} has no properties object.")
        zone_id = str(properties.get("zone_id", "")).strip()
        if not zone_id:
            raise InputValidationError(f"GeoJSON feature {index} is missing properties.zone_id.")
        zone_ids.append(zone_id)

    if len(zone_ids) != len(set(zone_ids)):
        raise InputValidationError("GeoJSON zone_id values must be unique.")

    return InputArtifact(
        source_path=str(source_path),
        staged_path=str(staged_path),
        kind="zones_geojson",
        sha256=sha256_file(staged_path),
        rows=len(features),
        zone_ids=tuple(sorted(zone_ids)),
    )


def validate_join_coverage(artifacts: list[InputArtifact]) -> None:
    zones = next((artifact for artifact in artifacts if artifact.kind == "zones_geojson"), None)
    if zones is None:
        return

    zone_ids = set(zones.zone_ids)
    socios = [artifact for artifact in artifacts if artifact.kind == "socio_csv"]
    for socio in socios:
        socio_zone_ids = set(socio.zone_ids)
        matched_zone_ids = zone_ids & socio_zone_ids
        socio_coverage = len(matched_zone_ids) / len(socio_zone_ids) if socio_zone_ids else 0
        zone_coverage = len(matched_zone_ids) / len(zone_ids) if zone_ids else 0
        coverage = min(socio_coverage, zone_coverage)
        if coverage < 0.95:
            raise InputValidationError(
                "Socio join coverage is "
                f"{coverage:.1%}; expected at least 95% of both socio and zone IDs to match."
            )

    for network in (artifact for artifact in artifacts if artifact.kind == "network_edges_csv"):
        unknown_zone_ids = sorted(set(network.zone_ids) - zone_ids)
        if unknown_zone_ids:
            raise InputValidationError(
                "Network edge zone IDs do not join to GeoJSON zones: "
                f"{', '.join(unknown_zone_ids[:10])}"
            )

    for zone_node_map in (
        artifact for artifact in artifacts if artifact.kind == "zone_node_map_csv"
    ):
        mapped_zone_ids = set(zone_node_map.zone_ids)
        unknown_zone_ids = sorted(mapped_zone_ids - zone_ids)
        missing_zone_ids = sorted(zone_ids - mapped_zone_ids)
        if unknown_zone_ids:
            raise InputValidationError(
                "Zone-node map zone IDs do not join to GeoJSON zones: "
                f"{', '.join(unknown_zone_ids[:10])}"
            )
        if missing_zone_ids:
            raise InputValidationError(
                "Zone-node map is missing GeoJSON zones: "
                f"{', '.join(missing_zone_ids[:10])}"
            )


def load_receipt(workspace: Path) -> dict[str, Any]:
    receipt_path = workspace / "intake_receipt.json"
    if not receipt_path.exists():
        raise InsufficientDataError("Run intake before planning or analysis.")
    from .contracts import validate_artifact_file

    return validate_artifact_file(receipt_path, "intake_receipt")


def discover_workspace_inputs(workspace: Path) -> dict[str, bool]:
    inputs_dir = workspace / "inputs"
    files = list(inputs_dir.glob("*")) if inputs_dir.exists() else []
    return {
        "gtfs_present": any(path.suffix.lower() == ".zip" for path in files),
        "network_present": any((workspace / "cache/graphs").glob("*.graphml")),
        "offline_graph_available": any((workspace / "cache/graphs").glob("*.graphml")),
    }


def run_paths(workspace: Path, run_id: str) -> dict[str, Path]:
    run_root = workspace / "runs" / run_id
    paths = {
        "root": run_root,
        "outputs": run_root / "outputs",
        "tables": run_root / "outputs" / "tables",
        "maps": run_root / "outputs" / "maps",
        "figures": run_root / "outputs" / "figures",
        "logs": run_root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def collect_artifact_hashes(root: Path) -> list[dict[str, str]]:
    if not root.exists():
        return []
    artifacts: list[dict[str, str]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        artifacts.append({"path": str(path), "sha256": sha256_file(path)})
    return artifacts
