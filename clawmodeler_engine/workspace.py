from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_VERSION = "0.9.5"

WORKSPACE_DIRS = (
    "inputs",
    "cache/graphs",
    "cache/gtfs",
    "runs",
    "reports",
    "logs",
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
    finally:
        connection.close()
    return "ready"


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
    elif {"from_zone_id", "to_zone_id", "minutes"}.issubset(set(reader.fieldnames)):
        kind = "network_edges_csv"
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
    socios = [artifact for artifact in artifacts if artifact.kind == "socio_csv"]
    if zones is None or not socios:
        return

    zone_ids = set(zones.zone_ids)
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
