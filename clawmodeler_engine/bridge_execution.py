from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .bridge_prepare import manifest_file_links
from .bridge_validation import validate_all_bridges
from .contracts import stamp_contract, validate_artifact_file, validate_contract
from .workspace import ClawModelerError, InputValidationError, read_json, utc_now, write_json

BRIDGE_MANIFEST_NAMES = {
    "sumo": "sumo_run_manifest.json",
    "matsim": "matsim_bridge_manifest.json",
    "urbansim": "urbansim_bridge_manifest.json",
    "dtalite": "dtalite_bridge_manifest.json",
    "tbest": "tbest_bridge_manifest.json",
}


def execute_bridge(
    workspace: Path,
    run_id: str,
    bridge: str,
    *,
    scenario_id: str = "baseline",
    dry_run: bool = False,
) -> Path:
    if bridge not in BRIDGE_MANIFEST_NAMES:
        raise InputValidationError(f"Unsupported bridge execution target: {bridge}")

    bridge_dir = workspace / "runs" / run_id / "outputs" / "bridges" / bridge
    bridge_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = bridge_dir / BRIDGE_MANIFEST_NAMES[bridge]
    report_path = bridge_dir / "bridge_execution_report.json"

    if not manifest_path.exists():
        return write_execution_report(
            report_path,
            bridge=bridge,
            run_id=run_id,
            scenario_id=scenario_id,
            status="blocked",
            execution_ready=False,
            blockers=["bridge_package_missing"],
            dry_run=dry_run,
            command=None,
            return_code=None,
            stdout_log=None,
            stderr_log=None,
            generated_outputs=[],
            forecast_readiness=None,
            limitations=["Prepare and validate the bridge package before execution."],
        )

    manifest = validate_artifact_file(manifest_path, "bridge_manifest")
    ready, structural_blockers = validate_bridge_for_execution(
        workspace, run_id, bridge, scenario_id
    )
    command = bridge_command(manifest)
    blockers = list(structural_blockers)
    blockers.extend(execution_preflight_blockers(bridge, manifest, command))

    if blockers:
        path = write_execution_report(
            report_path,
            bridge=bridge,
            run_id=run_id,
            scenario_id=scenario_id,
            status="blocked",
            execution_ready=False,
            blockers=blockers,
            dry_run=dry_run,
            command=command,
            return_code=None,
            stdout_log=None,
            stderr_log=None,
            generated_outputs=manifest_file_links(manifest_path),
            forecast_readiness=manifest.get("forecast_readiness"),
            limitations=execution_limitations(manifest),
        )
        update_manifest_execution(manifest_path, manifest, path, "blocked")
        return path

    if dry_run:
        path = write_execution_report(
            report_path,
            bridge=bridge,
            run_id=run_id,
            scenario_id=scenario_id,
            status="dry_run_ready",
            execution_ready=ready,
            blockers=[],
            dry_run=True,
            command=command,
            return_code=None,
            stdout_log=None,
            stderr_log=None,
            generated_outputs=manifest_file_links(manifest_path),
            forecast_readiness=manifest.get("forecast_readiness"),
            limitations=execution_limitations(manifest),
        )
        update_manifest_execution(manifest_path, manifest, path, "dry_run_ready")
        return path

    assert command is not None
    stdout_log = bridge_dir / f"{scenario_id}.{bridge}.stdout.log"
    stderr_log = bridge_dir / f"{scenario_id}.{bridge}.stderr.log"
    result = subprocess.run(
        command,
        cwd=bridge_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    status = "execution_succeeded" if result.returncode == 0 else "execution_failed"
    path = write_execution_report(
        report_path,
        bridge=bridge,
        run_id=run_id,
        scenario_id=scenario_id,
        status=status,
        execution_ready=result.returncode == 0,
        blockers=[] if result.returncode == 0 else ["external_command_failed"],
        dry_run=False,
        command=command,
        return_code=result.returncode,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        generated_outputs=sorted(
            set(manifest_file_links(manifest_path)) | {str(stdout_log), str(stderr_log)}
        ),
        forecast_readiness=manifest.get("forecast_readiness"),
        limitations=execution_limitations(manifest),
    )
    update_manifest_execution(manifest_path, manifest, path, status)
    return path


def validate_bridge_for_execution(
    workspace: Path, run_id: str, bridge: str, scenario_id: str
) -> tuple[bool, list[str]]:
    try:
        validation_path = validate_all_bridges(workspace, run_id, scenario_id=scenario_id)
        validation = read_json(validation_path)
    except ClawModelerError as error:
        return False, [f"bridge_validation_failed:{error}"]

    row = next(
        (item for item in validation.get("bridges", []) if item.get("bridge") == bridge),
        None,
    )
    if row is None:
        return False, ["bridge_package_missing"]
    return bool(row.get("ready")), list(row.get("structural_blockers") or row.get("blockers", []))


def bridge_command(manifest: dict[str, Any]) -> list[str] | None:
    raw = (manifest.get("commands") or {}).get("run")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return shlex.split(raw)


def execution_preflight_blockers(
    bridge: str, manifest: dict[str, Any], command: list[str] | None
) -> list[str]:
    blockers: list[str] = []
    if command is None:
        blockers.append("run_command_missing")
    if bridge == "sumo":
        if not shutil.which("sumo"):
            blockers.append("sumo_binary_missing")
        net_path = (manifest.get("inputs") or {}).get("net")
        if not net_path or not Path(str(net_path)).exists():
            blockers.append("sumo_network_missing")
    return blockers


def execution_limitations(manifest: dict[str, Any]) -> list[str]:
    readiness = manifest.get("forecast_readiness") or {}
    limitations = list(readiness.get("limitations", []))
    limitations.append(
        "Bridge execution status only confirms that the external command ran; calibrated "
        "forecast claims still require validation-ready detailed-engine evidence."
    )
    return limitations


def write_execution_report(
    path: Path,
    *,
    bridge: str,
    run_id: str,
    scenario_id: str,
    status: str,
    execution_ready: bool,
    blockers: list[str],
    dry_run: bool,
    command: list[str] | None,
    return_code: int | None,
    stdout_log: str | None,
    stderr_log: str | None,
    generated_outputs: list[str],
    forecast_readiness: dict[str, Any] | None,
    limitations: list[str],
) -> Path:
    report = stamp_contract(
        {
            "bridge": bridge,
            "run_id": run_id,
            "scenario_id": scenario_id,
            "created_at": utc_now(),
            "status": status,
            "execution_ready": execution_ready,
            "dry_run": dry_run,
            "command": command,
            "return_code": return_code,
            "stdout_log": stdout_log,
            "stderr_log": stderr_log,
            "generated_outputs": generated_outputs,
            "forecast_readiness": forecast_readiness,
            "limitations": limitations,
            "blockers": blockers,
        },
        "bridge_execution_report",
    )
    validate_contract(report, "bridge_execution_report")
    write_json(path, report)
    return path


def update_manifest_execution(
    manifest_path: Path, manifest: dict[str, Any], report_path: Path, status: str
) -> None:
    manifest["bridge_execution_report"] = str(report_path)
    manifest["last_execution_status"] = status
    validate_contract(manifest, "bridge_manifest")
    write_json(manifest_path, manifest)
