from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clawmodeler_engine.bridge_execution import execute_bridge
from clawmodeler_engine.contracts import validate_artifact_file, validate_contract
from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.model import graphml_edge_minutes, load_graphml_zone_graph
from clawmodeler_engine.orchestration import normalize_scenario_ids
from clawmodeler_engine.toolbox import assess_model_inventory, load_toolbox
from clawmodeler_engine.workspace import InputValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]


class ClawModelerEngineTest(unittest.TestCase):
    def run_engine(
        self, *args: str, expected_code: int = 0, cwd: Path = REPO_ROOT
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "clawmodeler_engine", *args],
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_code,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def test_init_creates_workspace_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "project"
            self.run_engine("init", "--workspace", str(workspace))
            self.assertTrue((workspace / "README.md").exists())
            self.assertTrue((workspace / "inputs" / "README.md").exists())
            self.assertTrue((workspace / "data-dictionary.md").exists())
            question = json.loads((workspace / "question.json").read_text(encoding="utf-8"))
            self.assertEqual(question["question_type"], "accessibility")
            self.assertEqual(question["scenarios"][0]["scenario_id"], "baseline")

    def test_scaffold_question_writes_starter_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "question.json"
            result = self.run_engine(
                "scaffold",
                "question",
                "--path",
                str(path),
                "--title",
                "Sample question",
                "--place-query",
                "Grass Valley, California, USA",
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["question_path"], str(path))
            self.assertTrue(payload["created"])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["title"], "Sample question")
            self.assertEqual(data["geography"]["place_query"], "Grass Valley, California, USA")
            self.assertEqual(data["question_type"], "accessibility")

    def test_scaffold_question_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "question.json"
            self.run_engine("scaffold", "question", "--path", str(path))
            stamp = path.stat().st_mtime_ns
            failure = self.run_engine(
                "scaffold",
                "question",
                "--path",
                str(path),
                expected_code=1,
            )
            self.assertIn("already exists", failure.stderr)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            self.run_engine(
                "scaffold",
                "question",
                "--path",
                str(path),
                "--force",
                "--title",
                "Overwritten",
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["title"], "Overwritten")

    def test_tools_json_includes_model_inventory(self) -> None:
        result = self.run_engine("tools", "--json")
        payload = json.loads(result.stdout)
        inventory = {item["id"]: item for item in payload["model_inventory"]}
        self.assertIn("sumo", inventory)
        self.assertIn("matsim", inventory)
        self.assertIn("dtalite", inventory)
        self.assertIn("agent_next_step", inventory["sumo"])

    def test_normalize_scenario_ids_defaults_to_baseline(self) -> None:
        self.assertEqual(normalize_scenario_ids([]), ["baseline"])
        self.assertEqual(normalize_scenario_ids(["", " build "]), ["build"])

    def test_duckdb_sync_populates_input_and_run_tables_when_available(self) -> None:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            self.skipTest("duckdb not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            inputs = write_demo_inputs(workspace)
            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(inputs["zones"]),
                str(inputs["socio"]),
                str(inputs["projects"]),
                str(inputs["network_edges"]),
                "--question",
                str(inputs["question"]),
                "--run-id",
                "demo",
                "--skip-bridges",
                "--scenarios",
                "baseline",
            )

            connection = duckdb.connect(str(workspace / "project.duckdb"))
            try:
                self.assertGreater(connection.execute("SELECT count(*) FROM zones").fetchone()[0], 0)
                self.assertGreater(connection.execute("SELECT count(*) FROM socio").fetchone()[0], 0)
                self.assertGreater(
                    connection.execute("SELECT count(*) FROM run_scenarios").fetchone()[0],
                    0,
                )
                self.assertGreater(
                    connection.execute("SELECT count(*) FROM run_fact_blocks").fetchone()[0],
                    0,
                )
                self.assertGreater(
                    connection.execute("SELECT count(*) FROM workspace_inputs").fetchone()[0],
                    0,
                )
                self.assertGreater(
                    connection.execute("SELECT count(*) FROM import_validation").fetchone()[0],
                    0,
                )
                self.assertEqual(connection.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
                self.assertGreater(
                    connection.execute("SELECT count(*) FROM run_artifacts").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM run_qa").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM portfolio_runs").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM bridge_readiness").fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_data_index_command_writes_file_backed_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            inputs = write_demo_inputs(workspace)
            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(inputs["zones"]),
                str(inputs["socio"]),
                str(inputs["projects"]),
                str(inputs["network_edges"]),
                "--question",
                str(inputs["question"]),
                "--run-id",
                "demo",
                "--skip-bridges",
                "--scenarios",
                "baseline",
            )
            result = self.run_engine(
                "data",
                "index",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo",
                "--json",
            )
            payload = json.loads(result.stdout)
            self.assertIn(
                payload["database_status"],
                {"ready", "duckdb_python_module_missing"},
            )
            self.assertEqual(payload["run_count"], 1)
            self.assertEqual(payload["runs"][0]["run_id"], "demo")
            self.assertGreater(payload["input_count"], 0)
            self.assertGreater(payload["artifact_count"], 0)
            self.assertEqual(payload["portfolio_run_count"], 1)
            self.assertTrue((workspace / "logs" / "workspace_index.json").exists())

    def test_toolbox_packaged_fallback_and_model_root_override(self) -> None:
        toolbox = load_toolbox()
        self.assertEqual(toolbox["schema_version"], "1.0.0")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sumo" / "tools").mkdir(parents=True)
            (root / "sumo" / "tests").mkdir()
            (root / "sumo" / "README.md").write_text("sumo", encoding="utf-8")
            (root / "sumo" / "tools" / "randomTrips.py").write_text("", encoding="utf-8")
            (root / "sumo" / "tests" / "runTests.sh").write_text("", encoding="utf-8")
            old_root = os.environ.get("CLAWMODELER_MODEL_ROOT")
            os.environ["CLAWMODELER_MODEL_ROOT"] = str(root)
            try:
                inventory = {item["id"]: item for item in assess_model_inventory()}
            finally:
                if old_root is None:
                    os.environ.pop("CLAWMODELER_MODEL_ROOT", None)
                else:
                    os.environ["CLAWMODELER_MODEL_ROOT"] = old_root
            self.assertTrue(inventory["sumo"]["ready"])
            self.assertFalse(inventory["matsim"]["present"])

    def test_intake_plan_run_export_and_bridge_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            projects = temp / "projects.csv"
            gtfs = temp / "sample_gtfs.zip"
            question = temp / "question.json"

            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1", "name": "North"},
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
                                    ],
                                },
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z2", "name": "South"},
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]
                                    ],
                                },
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\nz1,100,50\nz2,200,80\n", encoding="utf-8")
            projects.write_text(
                "project_id,name,safety,equity,climate,feasibility\n"
                "p1,Main Street,80,70,60,90\n"
                "p2,Depot Connector,60,85,75,55\n",
                encoding="utf-8",
            )
            with zipfile.ZipFile(gtfs, "w") as archive:
                archive.writestr(
                    "agency.txt",
                    "agency_id,agency_name,agency_url,agency_timezone\n"
                    "1,Demo,http://example.com,America/Los_Angeles\n",
                )
                archive.writestr(
                    "routes.txt",
                    "route_id,agency_id,route_short_name,route_long_name,route_type\n"
                    "r1,1,10,Demo Route,3\n",
                )
                archive.writestr(
                    "trips.txt",
                    "route_id,service_id,trip_id\nr1,weekday,t1\nr1,weekday,t2\n",
                )
                archive.writestr(
                    "stops.txt",
                    "stop_id,stop_name,stop_lat,stop_lon\ns1,One,0,0\ns2,Two,0,1\n",
                )
                archive.writestr(
                    "stop_times.txt",
                    "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                    "t1,08:00:00,08:00:00,s1,1\n"
                    "t1,08:20:00,08:20:00,s2,2\n"
                    "t2,09:00:00,09:00:00,s1,1\n"
                    "t2,09:20:00,09:20:00,s2,2\n",
                )
            question.write_text(
                json.dumps(
                    {
                        "question_type": "accessibility",
                        "proxy_speed_kph": 500,
                        "daily_vmt_per_capita": 20,
                        "scenarios": [
                            {"scenario_id": "baseline", "name": "Baseline"},
                            {
                                "scenario_id": "scenario-a",
                                "name": "Jobs Scenario",
                                "jobs_multiplier": 1.5,
                                "population_multiplier": 1.1,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(projects),
                str(gtfs),
            )
            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo",
                "--scenarios",
                "baseline",
                "scenario-a",
            )

            manifest = json.loads((workspace / "runs" / "demo" / "manifest.json").read_text())
            self.assertEqual(manifest["manifest_version"], "1.2.0")
            self.assertEqual(manifest["engine"]["routing_engine"], "osmnx_networkx")
            self.assertEqual(len(manifest["scenarios"]), 2)
            self.assertGreater(manifest["fact_block_count"], 0)
            self.assertIn("detailed_engine_readiness", manifest)
            self.assertEqual(
                manifest["detailed_engine_readiness"]["engines"]["sumo"]["status"],
                "handoff_only",
            )

            qa_report = json.loads((workspace / "runs" / "demo" / "qa_report.json").read_text())
            self.assertTrue(qa_report["export_ready"])
            self.assertEqual(qa_report["blockers"], [])

            self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo",
                "--format",
                "md",
            )
            report = (workspace / "reports" / "demo_report.md").read_text(encoding="utf-8")
            self.assertIn("ClawModeler Technical Report", report)
            self.assertIn("screening-level", report)
            tables = workspace / "runs" / "demo" / "outputs" / "tables"
            self.assertTrue((tables / "accessibility_delta.csv").exists())
            self.assertTrue((tables / "transit_metrics_by_route.csv").exists())
            self.assertTrue((tables / "project_scores.csv").exists())
            self.assertTrue(
                (
                    workspace
                    / "runs"
                    / "demo"
                    / "outputs"
                    / "bridges"
                    / "sumo"
                    / "bridge_manifest.json"
                ).exists()
            )

    def test_export_parser_accepts_docx_format(self) -> None:
        try:
            import docx  # noqa: F401
            import markdown_it  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("python-docx and markdown-it-py required for DOCX export")

        import zipfile

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")

            self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                "--format",
                "docx",
            )

            report_path = workspace / "reports" / "sample_report.docx"
            self.assertTrue(report_path.exists(), f"{report_path} was not written")
            self.assertTrue(
                zipfile.is_zipfile(report_path),
                "docx export did not produce a valid ZIP container",
            )

    def test_run_resolves_relative_receipt_paths_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            intake_cwd = temp / "intake-cwd"
            later_cwd = temp / "later-cwd"
            intake_cwd.mkdir()
            later_cwd.mkdir()
            workspace = intake_cwd / "workspace"
            inputs = write_demo_inputs(intake_cwd)
            input_paths = [
                inputs["zones"],
                inputs["socio"],
                inputs["projects"],
                inputs["network_edges"],
                inputs["gtfs"],
            ]

            self.run_engine(
                "intake",
                "--workspace",
                "workspace",
                "--inputs",
                *(str(path.relative_to(intake_cwd)) for path in input_paths),
                cwd=intake_cwd,
            )
            self.run_engine(
                "plan",
                "--workspace",
                str(workspace),
                "--question",
                str(inputs["question"]),
                cwd=later_cwd,
            )
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "relpaths",
                "--scenarios",
                "baseline",
                cwd=later_cwd,
            )

            self.assertTrue(
                (
                    workspace
                    / "runs"
                    / "relpaths"
                    / "outputs"
                    / "tables"
                    / "accessibility_by_zone.csv"
                ).exists()
            )

    def test_intake_rejects_low_join_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\nmissing,10,5\n", encoding="utf-8")

            result = self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                expected_code=10,
            )
            self.assertIn("Socio join coverage", result.stderr)

    def test_intake_rejects_missing_socio_for_zones(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z2"},
                                "geometry": {"type": "Point", "coordinates": [1, 1]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\nz1,10,5\n", encoding="utf-8")

            result = self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                expected_code=10,
            )
            self.assertIn("Socio join coverage", result.stderr)

    def test_intake_rejects_malformed_network_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            network = temp / "network_edges.csv"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z2"},
                                "geometry": {"type": "Point", "coordinates": [1, 1]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\nz1,10,5\nz2,20,8\n", encoding="utf-8")
            network.write_text("from_zone_id,to_zone_id,minutes\nz1,z2,-4\n", encoding="utf-8")

            result = self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(network),
                expected_code=10,
            )
            self.assertIn("network_edges.csv has invalid minutes", result.stderr)

    def test_intake_rejects_network_edges_with_unknown_zones(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            network = temp / "network_edges.csv"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z2"},
                                "geometry": {"type": "Point", "coordinates": [1, 1]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\nz1,10,5\nz2,20,8\n", encoding="utf-8")
            network.write_text(
                "from_zone_id,to_zone_id,minutes\nz1,missing,4\n", encoding="utf-8"
            )

            result = self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(network),
                expected_code=10,
            )
            self.assertIn("Network edge zone IDs do not join", result.stderr)

    def test_workflow_routing_diagnosis_flags_disconnected_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            network = temp / "network_edges.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z1"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z2"},
                                "geometry": {"type": "Point", "coordinates": [1, 1]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "z3"},
                                "geometry": {"type": "Point", "coordinates": [2, 2]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text(
                "zone_id,population,jobs\nz1,10,5\nz2,20,8\nz3,30,13\n",
                encoding="utf-8",
            )
            network.write_text("from_zone_id,to_zone_id,minutes\nz1,z2,6\n", encoding="utf-8")
            question.write_text(json.dumps({"question_type": "accessibility"}), encoding="utf-8")

            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(network),
                "--question",
                str(question),
                "--run-id",
                "disconnected",
                "--skip-bridges",
                "--scenarios",
                "baseline",
            )

            workflow = json.loads(
                (workspace / "runs" / "disconnected" / "workflow_report.json").read_text()
            )
            comparison = workflow["routing"]["proxy_comparison"]
            self.assertEqual(comparison["coverage_status"], "partial")
            self.assertEqual(comparison["reachable_pairs"], 2)
            self.assertEqual(comparison["unreachable_pairs"], 4)
            self.assertIn("unreachable", comparison["coverage_detail"])

    def test_demo_creates_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.assertTrue((workspace / "reports" / "sample_report.md").exists())
            self.assertTrue((workspace / "runs" / "sample" / "manifest.json").exists())
            accessibility = (
                workspace
                / "runs"
                / "sample"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("network_edges_dijkstra", accessibility)

    def test_export_refreshes_qa_and_blocks_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            manifest_path = workspace / "runs" / "sample" / "manifest.json"
            manifest_path.unlink()

            result = self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                expected_code=40,
            )
            self.assertIn("Export blocked by QA gate", result.stderr)
            qa_report = json.loads(
                (workspace / "runs" / "sample" / "qa_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(qa_report["export_ready"])
            self.assertIn("manifest_missing", qa_report["blockers"])

    def test_export_refreshes_qa_and_blocks_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            manifest_path = workspace / "runs" / "sample" / "manifest.json"
            manifest_path.write_text('{"artifact_type": "run_manifest"}\n', encoding="utf-8")

            result = self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                expected_code=40,
            )
            self.assertIn("Export blocked by QA gate", result.stderr)
            qa_report = json.loads(
                (workspace / "runs" / "sample" / "qa_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(qa_report["export_ready"])
            self.assertIn("manifest_invalid", qa_report["blockers"])

    def test_export_refreshes_qa_and_blocks_invalid_fact_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            fact_blocks_path = (
                workspace
                / "runs"
                / "sample"
                / "outputs"
                / "tables"
                / "fact_blocks.jsonl"
            )
            with fact_blocks_path.open("a", encoding="utf-8") as file:
                file.write('{"fact_id": "broken"}\n')

            result = self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                expected_code=40,
            )
            self.assertIn("Export blocked by QA gate", result.stderr)
            qa_report = json.loads(
                (workspace / "runs" / "sample" / "qa_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(qa_report["export_ready"])
            self.assertIn("fact_blocks_invalid", qa_report["blockers"])
            self.assertGreater(qa_report["checks"]["fact_block_count"], 0)
            self.assertEqual(qa_report["checks"]["invalid_fact_block_count"], 1)

    def test_workflow_full_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workflow"
            inputs = write_demo_inputs(workspace)
            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(inputs["zones"]),
                str(inputs["socio"]),
                str(inputs["projects"]),
                str(inputs["network_edges"]),
                str(inputs["gtfs"]),
                "--question",
                str(inputs["question"]),
                "--run-id",
                "full",
                "--scenarios",
                "baseline",
                "infill-growth",
            )
            workflow_report = json.loads(
                (workspace / "runs" / "full" / "workflow_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(workflow_report["qa"]["export_ready"])
            self.assertTrue(workflow_report["bridge_validation"]["export_ready"])
            self.assertFalse(workflow_report["bridge_validation"]["detailed_forecast_ready"])
            self.assertGreater(
                len(workflow_report["bridge_validation"]["detailed_forecast_blockers"]),
                0,
            )
            self.assertTrue((workspace / "reports" / "full_report.md").exists())
            self.assertEqual(len(workflow_report["bridges"]["prepared"]), 5)
            self.assertEqual(
                workflow_report["detailed_engine_readiness"]["engines"]["sumo"]["status"],
                "handoff_only",
            )

    def test_manual_and_workflow_paths_share_core_artifact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            manual_workspace = temp / "manual"
            workflow_workspace = temp / "workflow"
            manual_inputs = write_demo_inputs(manual_workspace)
            workflow_inputs = write_demo_inputs(workflow_workspace)

            common_scenarios = ["baseline", "infill-growth"]
            self.run_engine(
                "intake",
                "--workspace",
                str(manual_workspace),
                "--inputs",
                str(manual_inputs["zones"]),
                str(manual_inputs["socio"]),
                str(manual_inputs["projects"]),
                str(manual_inputs["network_edges"]),
                str(manual_inputs["gtfs"]),
            )
            self.run_engine(
                "plan",
                "--workspace",
                str(manual_workspace),
                "--question",
                str(manual_inputs["question"]),
            )
            self.run_engine(
                "run",
                "--workspace",
                str(manual_workspace),
                "--run-id",
                "shared",
                "--scenarios",
                *common_scenarios,
            )
            self.run_engine(
                "export",
                "--workspace",
                str(manual_workspace),
                "--run-id",
                "shared",
            )

            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workflow_workspace),
                "--inputs",
                str(workflow_inputs["zones"]),
                str(workflow_inputs["socio"]),
                str(workflow_inputs["projects"]),
                str(workflow_inputs["network_edges"]),
                str(workflow_inputs["gtfs"]),
                "--question",
                str(workflow_inputs["question"]),
                "--run-id",
                "shared",
                "--scenarios",
                *common_scenarios,
                "--skip-bridges",
            )

            manual_plan = json.loads(
                (manual_workspace / "analysis_plan.json").read_text(encoding="utf-8")
            )
            workflow_plan = json.loads(
                (workflow_workspace / "analysis_plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manual_plan["methods"], workflow_plan["methods"])
            self.assertEqual(manual_plan["assumptions"], workflow_plan["assumptions"])

            manual_manifest = json.loads(
                (manual_workspace / "runs" / "shared" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            workflow_manifest = json.loads(
                (workflow_workspace / "runs" / "shared" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manual_manifest["engine"], workflow_manifest["engine"])
            self.assertEqual(manual_manifest["methods"], workflow_manifest["methods"])
            self.assertEqual(
                manual_manifest["fact_block_count"],
                workflow_manifest["fact_block_count"],
            )
            self.assertEqual(
                [scenario["scenario_id"] for scenario in manual_manifest["scenarios"]],
                [scenario["scenario_id"] for scenario in workflow_manifest["scenarios"]],
            )

            manual_report = (
                manual_workspace / "reports" / "shared_report.md"
            ).read_text(encoding="utf-8")
            workflow_report = (
                workflow_workspace / "reports" / "shared_report.md"
            ).read_text(encoding="utf-8")
            self.assertIn("ClawModeler Technical Report", manual_report)
            self.assertIn("ClawModeler Technical Report", workflow_report)

    def test_workflow_demo_full_and_report_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workflow-demo"
            self.run_engine(
                "workflow",
                "demo-full",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo-full",
            )
            workflow_report = json.loads(
                (workspace / "runs" / "demo-full" / "workflow_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(workflow_report["workflow"], "full")
            self.assertTrue(workflow_report["bridge_validation"]["export_ready"])
            self.assertFalse(workflow_report["bridge_validation"]["detailed_forecast_ready"])
            self.assertEqual(
                workflow_report["detailed_engine_readiness"]["engines"]["matsim"]["status"],
                "handoff_only",
            )
            self.run_engine(
                "workflow",
                "report-only",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo-full",
            )
            report_only = json.loads(
                (workspace / "runs" / "demo-full" / "workflow_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report_only["workflow"], "report-only")
            self.assertTrue((workspace / "reports" / "demo-full_report.md").exists())

    def test_versioned_artifact_contracts_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "contracts"
            self.run_engine(
                "workflow",
                "demo-full",
                "--workspace",
                str(workspace),
                "--run-id",
                "demo",
            )
            run_root = workspace / "runs" / "demo"
            bridge_root = run_root / "outputs" / "bridges"

            validate_artifact_file(workspace / "intake_receipt.json", "intake_receipt")
            validate_artifact_file(workspace / "analysis_plan.json", "analysis_plan")
            validate_artifact_file(workspace / "engine_selection.json", "engine_selection")
            validate_artifact_file(run_root / "manifest.json", "run_manifest")
            validate_artifact_file(run_root / "qa_report.json", "qa_report")
            validate_artifact_file(run_root / "workflow_report.json", "workflow_report")
            validate_artifact_file(
                bridge_root / "bridge_prepare_report.json",
                "bridge_prepare_report",
            )
            validate_artifact_file(
                bridge_root / "bridge_validation_report.json",
                "bridge_validation_report",
            )
            for bridge in ("sumo", "matsim", "urbansim", "dtalite", "tbest"):
                validate_artifact_file(
                    bridge_root / bridge / "bridge_manifest.json",
                    "bridge_manifest",
                )

            with self.assertRaises(InputValidationError):
                validate_contract({"schema_version": "0.0.0"}, "qa_report")

    def test_workflow_diagnose_empty_and_completed_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_workspace = Path(temp_dir) / "empty"
            self.run_engine("workflow", "diagnose", "--workspace", str(empty_workspace))
            empty_diagnosis = json.loads(
                (empty_workspace / "logs" / "workflow_diagnosis.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("Stage a zones GeoJSON", " ".join(empty_diagnosis["recommendations"]))

            complete_workspace = Path(temp_dir) / "complete"
            self.run_engine(
                "workflow",
                "demo-full",
                "--workspace",
                str(complete_workspace),
                "--run-id",
                "demo",
            )
            self.run_engine("workflow", "diagnose", "--workspace", str(complete_workspace))
            complete_diagnosis = json.loads(
                (complete_workspace / "runs" / "demo" / "workflow_diagnosis.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(complete_diagnosis["run_id"], "demo")
            self.assertTrue(complete_diagnosis["qa"]["export_ready"])
            self.assertTrue(complete_diagnosis["bridge_validation"]["export_ready"])
            self.assertEqual(
                complete_diagnosis["detailed_engine_readiness"]["engines"]["urbansim"]["status"],
                "handoff_only",
            )
            self.assertIn(
                "Record calibration inputs, validation targets, model year, geography, and method notes",
                " ".join(complete_diagnosis["recommendations"]),
            )

    def test_bridge_sumo_prepare_writes_executable_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.run_engine(
                "bridge",
                "sumo",
                "prepare",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                "--scenario-id",
                "baseline",
            )
            self.run_engine(
                "bridge",
                "sumo",
                "validate",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                "--scenario-id",
                "baseline",
            )
            bridge_dir = workspace / "runs" / "sample" / "outputs" / "bridges" / "sumo"
            self.assertTrue((bridge_dir / "network.nod.xml").exists())
            self.assertTrue((bridge_dir / "network.edg.xml").exists())
            self.assertTrue((bridge_dir / "baseline.trips.xml").exists())
            self.assertTrue((bridge_dir / "baseline.sumocfg").exists())
            self.assertTrue((bridge_dir / "build-net.sh").exists())
            self.assertTrue((bridge_dir / "bridge_qa_report.json").exists())
            run_manifest = json.loads(
                (bridge_dir / "sumo_run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(run_manifest["bridge"], "sumo")
            self.assertGreater(run_manifest["trip_count"], 0)
            self.assertEqual(run_manifest["demand_controls"]["demand_multiplier"], 1.0)
            bridge_qa = json.loads(
                (bridge_dir / "bridge_qa_report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(bridge_qa["export_ready"])
            self.assertEqual(bridge_qa["blockers"], [])
            bridge_manifest = json.loads(
                (bridge_dir / "bridge_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                bridge_manifest["sumo_run_manifest"],
                str(bridge_dir / "sumo_run_manifest.json"),
            )
            self.assertTrue(bridge_manifest["bridge_qa_export_ready"])

            self.run_engine(
                "export",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                "--format",
                "md",
            )
            report = (workspace / "reports" / "sample_report.md").read_text(encoding="utf-8")
            self.assertIn("Bridge Packages", report)
            self.assertIn("sumo", report)

    def test_bridge_matsim_prepare_writes_handoff_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.run_engine(
                "bridge",
                "matsim",
                "prepare",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
                "--scenario-id",
                "baseline",
            )
            bridge_dir = workspace / "runs" / "sample" / "outputs" / "bridges" / "matsim"
            self.assertTrue((bridge_dir / "network.xml").exists())
            self.assertTrue((bridge_dir / "baseline_population.xml").exists())
            self.assertTrue((bridge_dir / "baseline_config.xml").exists())
            self.assertTrue((bridge_dir / "run-matsim.sh").exists())
            matsim_manifest = json.loads(
                (bridge_dir / "matsim_bridge_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(matsim_manifest["bridge"], "matsim")
            self.assertGreater(matsim_manifest["person_count"], 0)
            bridge_manifest = json.loads(
                (bridge_dir / "bridge_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                bridge_manifest["matsim_bridge_manifest"],
                str(bridge_dir / "matsim_bridge_manifest.json"),
            )

    def test_bridge_urbansim_prepare_and_validate_all(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.run_engine(
                "bridge",
                "prepare-all",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
            )
            self.run_engine(
                "bridge",
                "validate",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
            )
            bridge_dir = workspace / "runs" / "sample" / "outputs" / "bridges"
            urbansim_dir = bridge_dir / "urbansim"
            self.assertTrue((urbansim_dir / "zones.csv").exists())
            self.assertTrue((urbansim_dir / "baseline_households.csv").exists())
            self.assertTrue((urbansim_dir / "baseline_jobs.csv").exists())
            self.assertTrue((urbansim_dir / "baseline_buildings.csv").exists())
            urbansim_manifest = json.loads(
                (urbansim_dir / "urbansim_bridge_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertGreater(urbansim_manifest["household_count"], 0)
            self.assertGreater(urbansim_manifest["job_count"], 0)
            self.assertTrue((bridge_dir / "dtalite" / "dtalite_bridge_manifest.json").exists())
            self.assertTrue((bridge_dir / "tbest" / "tbest_bridge_manifest.json").exists())
            prepare_report = json.loads(
                (bridge_dir / "bridge_prepare_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(prepare_report["prepared"]), 5)
            self.assertEqual(prepare_report["failed"], [])
            self.assertEqual(
                prepare_report["detailed_engine_readiness"]["engines"]["dtalite"]["status"],
                "handoff_only",
            )
            self.assertEqual(
                prepare_report["prepared"][0]["forecast_readiness"]["status"],
                "handoff_only",
            )
            validation = json.loads(
                (bridge_dir / "bridge_validation_report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(validation["export_ready"])
            self.assertFalse(validation["detailed_forecast_ready"])
            self.assertEqual(validation["blockers"], [])
            self.assertGreater(len(validation["detailed_forecast_blockers"]), 0)
            self.assertEqual(
                {bridge["bridge"] for bridge in validation["bridges"]},
                {"sumo", "matsim", "urbansim", "dtalite", "tbest"},
            )
            for bridge in validation["bridges"]:
                self.assertEqual(bridge["structural_blockers"], [])
                self.assertGreater(len(bridge["forecast_blockers"]), 0)
                self.assertIn("screening-level", bridge["planner_message"])

    def test_bridge_commands_surface_calibrated_readiness_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            inputs = write_demo_inputs(workspace)
            question_data = json.loads(inputs["question"].read_text(encoding="utf-8"))
            question_data["model_year"] = "2027"
            question_data["calibration_geography"] = "Grass Valley core"
            question_data["detailed_engine_readiness"] = {
                "sumo": {
                    "method_notes": ["Validated against weekday PM peak turning movement counts."],
                    "provided_calibration_inputs": [
                        {"id": "observed_counts", "label": "Observed counts"},
                        {"id": "network_controls", "label": "Signal timing set"},
                        {"id": "demand_controls", "label": "OD seed matrix"},
                    ],
                    "provided_validation_targets": [
                        {"id": "travel_times", "label": "Observed travel times"},
                        {"id": "delay_or_queue", "label": "Queue observations"},
                    ],
                }
            }
            inputs["question"].write_text(json.dumps(question_data), encoding="utf-8")

            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(inputs["zones"]),
                str(inputs["socio"]),
                str(inputs["projects"]),
                str(inputs["network_edges"]),
                str(inputs["gtfs"]),
                "--question",
                str(inputs["question"]),
                "--run-id",
                "ready",
                "--scenarios",
                "baseline",
            )
            prepare_stdout = json.loads(
                self.run_engine(
                    "bridge",
                    "prepare-all",
                    "--workspace",
                    str(workspace),
                    "--run-id",
                    "ready",
                ).stdout
            )
            self.assertEqual(
                prepare_stdout["detailed_engine_statuses"]["sumo"],
                "validation_ready",
            )
            validate_stdout = json.loads(
                self.run_engine(
                    "bridge",
                    "validate",
                    "--workspace",
                    str(workspace),
                    "--run-id",
                    "ready",
                ).stdout
            )
            self.assertFalse(validate_stdout["detailed_forecast_ready"])
            bridge_report = json.loads(
                (
                    workspace
                    / "runs"
                    / "ready"
                    / "outputs"
                    / "bridges"
                    / "bridge_validation_report.json"
                ).read_text(encoding="utf-8")
            )
            sumo_row = next(
                row for row in bridge_report["bridges"] if row["bridge"] == "sumo"
            )
            self.assertEqual(
                sumo_row["forecast_readiness"]["status"],
                "validation_ready",
            )
            self.assertIn(
                "matsim:method_notes_missing",
                bridge_report["detailed_forecast_blockers"],
            )

    def test_bridge_execute_dry_run_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.run_engine(
                "bridge",
                "prepare-all",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
            )

            stdout = json.loads(
                self.run_engine(
                    "bridge",
                    "matsim",
                    "execute",
                    "--workspace",
                    str(workspace),
                    "--run-id",
                    "sample",
                    "--dry-run",
                ).stdout
            )

            self.assertEqual(stdout["status"], "dry_run_ready")
            report = json.loads(Path(stdout["bridge_execution_report"]).read_text())
            self.assertEqual(report["artifact_type"], "bridge_execution_report")
            self.assertTrue(report["execution_ready"])
            self.assertEqual(report["blockers"], [])
            self.assertEqual(report["bridge"], "matsim")
            feedback = report["operator_feedback"]
            self.assertEqual(feedback["operator_status"], "dry_run_ready")
            self.assertEqual(feedback["evidence_level"], "handoff_package_ready")
            self.assertIn("dry run is ready", feedback["operator_summary"])
            self.assertIn("bash", feedback["command_display"])
            self.assertGreater(feedback["output_summary"]["expected_count"], 0)
            self.assertEqual(
                feedback["output_summary"]["missing_count"],
                len(feedback["missing_outputs"]),
            )
            bash_tool = next(
                tool for tool in feedback["required_tools"] if tool["id"] == "bash"
            )
            self.assertTrue(bash_tool["available"])

    def test_bridge_execute_reports_missing_external_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "demo"
            self.run_engine("demo", "--workspace", str(workspace), "--run-id", "sample")
            self.run_engine(
                "bridge",
                "prepare-all",
                "--workspace",
                str(workspace),
                "--run-id",
                "sample",
            )

            def fake_which(command: str) -> str | None:
                if command == "sumo":
                    return None
                return f"/usr/bin/{command}"

            with patch("clawmodeler_engine.bridge_execution.shutil.which", fake_which):
                report_path = execute_bridge(
                    workspace,
                    "sample",
                    "sumo",
                    dry_run=True,
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["execution_ready"])
            self.assertIn("sumo_binary_missing", report["blockers"])
            feedback = report["operator_feedback"]
            self.assertEqual(feedback["evidence_level"], "execution_blocked")
            sumo_tool = next(
                tool for tool in feedback["required_tools"] if tool["id"] == "sumo"
            )
            self.assertFalse(sumo_tool["available"])
            self.assertIn(
                "Install SUMO and make the sumo command available on PATH.",
                feedback["next_steps"],
            )

    def test_graphml_cache_drives_accessibility_when_edge_csv_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            zone_node_map = temp / "zone_node_map.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "b"},
                                "geometry": {"type": "Point", "coordinates": [1, 0]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\nb,20,80\n", encoding="utf-8")
            zone_node_map.write_text("zone_id,node_id\na,n1\nb,n2\n", encoding="utf-8")
            question.write_text(json.dumps({"question_type": "accessibility"}), encoding="utf-8")

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(zone_node_map),
            )
            graph_dir = workspace / "cache" / "graphs"
            graph_dir.mkdir(parents=True, exist_ok=True)
            (graph_dir / "zones.graphml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="edge" attr.name="travel_time" attr.type="double"/>
  <graph id="G" edgedefault="directed">
    <node id="n1"/>
    <node id="n2"/>
    <edge source="n1" target="n2"><data key="d0">600</data></edge>
  </graph>
</graphml>
""",
                encoding="utf-8",
            )
            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "graphml",
                "--scenarios",
                "baseline",
            )
            accessibility = (
                workspace
                / "runs"
                / "graphml"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("graphml_dijkstra", accessibility)

    def test_question_routing_graph_id_selects_named_graphml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            zone_node_map = temp / "zone_node_map.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "b"},
                                "geometry": {"type": "Point", "coordinates": [1, 0]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\nb,20,80\n", encoding="utf-8")
            zone_node_map.write_text("zone_id,node_id\na,n1\nb,n2\n", encoding="utf-8")
            question.write_text(
                json.dumps(
                    {
                        "question_type": "accessibility",
                        "routing": {"source": "auto", "graph_id": "fast", "impedance": "minutes"},
                    }
                ),
                encoding="utf-8",
            )

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(zone_node_map),
            )
            graph_dir = workspace / "cache" / "graphs"
            graph_dir.mkdir(parents=True, exist_ok=True)
            for graph_id, seconds in (("slow", 1800), ("fast", 300)):
                (graph_dir / f"{graph_id}.graphml").write_text(
                    f"""<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="edge" attr.name="travel_time" attr.type="double"/>
  <graph id="G" edgedefault="directed">
    <node id="n1"/>
    <node id="n2"/>
    <edge source="n1" target="n2"><data key="d0">{seconds}</data></edge>
  </graph>
</graphml>
""",
                    encoding="utf-8",
                )

            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "graphml",
                "--scenarios",
                "baseline",
            )
            accessibility = (
                workspace
                / "runs"
                / "graphml"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("graphml_dijkstra:fast", accessibility)

    def test_workflow_full_routing_override_updates_analysis_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            zone_node_map = temp / "zone_node_map.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "b"},
                                "geometry": {"type": "Point", "coordinates": [1, 0]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\nb,20,80\n", encoding="utf-8")
            zone_node_map.write_text("zone_id,node_id\na,n1\nb,n2\n", encoding="utf-8")
            question.write_text(json.dumps({"question_type": "accessibility"}), encoding="utf-8")
            graph_dir = workspace / "cache" / "graphs"
            graph_dir.mkdir(parents=True, exist_ok=True)
            (graph_dir / "fast.graphml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="edge" attr.name="travel_time" attr.type="double"/>
  <graph id="G" edgedefault="directed">
    <node id="n1"/>
    <node id="n2"/>
    <edge source="n1" target="n2"><data key="d0">300</data></edge>
  </graph>
</graphml>
""",
                encoding="utf-8",
            )

            self.run_engine(
                "workflow",
                "full",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
                str(zone_node_map),
                "--question",
                str(question),
                "--run-id",
                "override",
                "--skip-bridges",
                "--routing-source",
                "graphml",
                "--routing-graph-id",
                "fast",
                "--routing-impedance",
                "minutes",
                "--scenarios",
                "baseline",
            )

            analysis_plan = json.loads((workspace / "analysis_plan.json").read_text())
            self.assertEqual(analysis_plan["question"]["routing"]["source"], "graphml")
            workflow = json.loads(
                (workspace / "runs" / "override" / "workflow_report.json").read_text()
            )
            self.assertEqual(workflow["routing"]["selected_source"], "graphml")
            self.assertEqual(
                workflow["routing"]["proxy_comparison"]["network_engine"],
                "graphml_dijkstra:fast",
            )
            self.assertEqual(workflow["routing"]["proxy_comparison"]["reachable_pairs"], 1)
            accessibility = (
                workspace
                / "runs"
                / "override"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("graphml_dijkstra:fast", accessibility)

    def test_question_routing_rejects_unsupported_impedance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\n", encoding="utf-8")
            question.write_text(
                json.dumps(
                    {
                        "question_type": "accessibility",
                        "routing": {"source": "auto", "impedance": "distance"},
                    }
                ),
                encoding="utf-8",
            )

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
            )
            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            result = self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "bad-routing",
                "--scenarios",
                "baseline",
                expected_code=10,
            )
            self.assertIn("Unsupported routing impedance", result.stderr)

    def test_graph_map_zones_registers_generated_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [-121.75, 38.55]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "b"},
                                "geometry": {"type": "Point", "coordinates": [-121.73, 38.56]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\nb,20,80\n", encoding="utf-8")
            question.write_text(json.dumps({"question_type": "accessibility"}), encoding="utf-8")

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
            )
            graph_dir = workspace / "cache" / "graphs"
            graph_dir.mkdir(parents=True, exist_ok=True)
            graph_path = graph_dir / "osmnx.graphml"
            graph_path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="edge" attr.name="travel_time" attr.type="double"/>
  <key id="d1" for="node" attr.name="x" attr.type="double"/>
  <key id="d2" for="node" attr.name="y" attr.type="double"/>
  <graph id="G" edgedefault="directed">
    <node id="n1"><data key="d1">-121.75</data><data key="d2">38.55</data></node>
    <node id="n2"><data key="d1">-121.73</data><data key="d2">38.56</data></node>
    <edge source="n1" target="n2"><data key="d0">600</data></edge>
  </graph>
</graphml>
""",
                encoding="utf-8",
            )

            self.run_engine("graph", "map-zones", "--workspace", str(workspace))
            zone_node_map = workspace / "inputs" / "zone_node_map.csv"
            self.assertTrue(zone_node_map.exists())
            self.assertIn("a,n1", zone_node_map.read_text(encoding="utf-8"))
            receipt = json.loads((workspace / "intake_receipt.json").read_text())
            self.assertTrue(
                any(item.get("kind") == "zone_node_map_csv" for item in receipt["inputs"])
            )

            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "mapped-graphml",
                "--scenarios",
                "baseline",
            )
            accessibility = (
                workspace
                / "runs"
                / "mapped-graphml"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("graphml_dijkstra", accessibility)

    def test_graphml_edge_minutes_accepts_osmnx_seconds_and_length_speed(self) -> None:
        self.assertEqual(graphml_edge_minutes({"travel_time": "600"}), 10)
        self.assertEqual(graphml_edge_minutes({"length": "1000", "speed_kph": "60"}), 1)

    def test_graphml_loader_handles_missing_namespace_or_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graphml = Path(temp_dir) / "bare.graphml"
            graphml.write_text(
                """<graphml>
  <key id="d0" for="edge" attr.name="travel_time" attr.type="double"/>
  <edge source="n1" target="n2"><data key="d0">300</data></edge>
</graphml>
""",
                encoding="utf-8",
            )

            graph = load_graphml_zone_graph(graphml)

            self.assertEqual(graph["n1"], [("n2", 5)])

    def test_graphml_cache_without_zone_node_map_uses_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            zones = temp / "zones.geojson"
            socio = temp / "socio.csv"
            question = temp / "question.json"
            zones.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "a"},
                                "geometry": {"type": "Point", "coordinates": [-121.75, 38.55]},
                            },
                            {
                                "type": "Feature",
                                "properties": {"zone_id": "b"},
                                "geometry": {"type": "Point", "coordinates": [-121.73, 38.56]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            socio.write_text("zone_id,population,jobs\na,10,5\nb,20,80\n", encoding="utf-8")
            question.write_text(json.dumps({"question_type": "accessibility"}), encoding="utf-8")

            self.run_engine(
                "intake",
                "--workspace",
                str(workspace),
                "--inputs",
                str(zones),
                str(socio),
            )
            graph_dir = workspace / "cache" / "graphs"
            graph_dir.mkdir(parents=True, exist_ok=True)
            (graph_dir / "osmnx.graphml").write_text(
                """<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph id="G" edgedefault="directed">
    <edge source="n1" target="n2"/>
  </graph>
</graphml>
""",
                encoding="utf-8",
            )

            self.run_engine("plan", "--workspace", str(workspace), "--question", str(question))
            self.run_engine(
                "run",
                "--workspace",
                str(workspace),
                "--run-id",
                "unmapped-graphml",
                "--scenarios",
                "baseline",
            )
            accessibility = (
                workspace
                / "runs"
                / "unmapped-graphml"
                / "outputs"
                / "tables"
                / "accessibility_by_zone.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("euclidean_proxy", accessibility)

    def test_osmnx_graph_command_reports_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            result = self.run_engine(
                "graph",
                "osmnx",
                "--workspace",
                str(workspace),
                "--place",
                "Demo, CA",
                expected_code=30,
            )
            self.assertIn("OSMnx is not installed", result.stderr)


def _has_matplotlib() -> bool:
    try:
        import matplotlib  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


def _has_folium() -> bool:
    try:
        import folium  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


def _has_jinja2() -> bool:
    try:
        import jinja2  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


@unittest.skipUnless(_has_matplotlib(), "matplotlib not installed")
class ChartsTest(unittest.TestCase):
    def test_render_standard_figures_produces_non_empty_pngs(self) -> None:
        from clawmodeler_engine.charts import render_standard_figures

        with tempfile.TemporaryDirectory() as temp_dir:
            figures_dir = Path(temp_dir) / "figures"
            accessibility_rows = [
                {"scenario_id": "baseline", "origin_zone_id": "Z1", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 1200},
                {"scenario_id": "baseline", "origin_zone_id": "Z2", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 800},
                {"scenario_id": "scenario-a", "origin_zone_id": "Z1", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 1400},
                {"scenario_id": "scenario-a", "origin_zone_id": "Z2", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 900},
            ]
            vmt_rows = [
                {"scenario_id": "baseline", "daily_vmt": 50000, "daily_kg_co2e": 20000,
                 "population": 3000, "daily_vmt_delta": 0, "tier": "screening",
                 "method": "per_capita_proxy"},
                {"scenario_id": "scenario-a", "daily_vmt": 55000, "daily_kg_co2e": 22000,
                 "population": 3200, "daily_vmt_delta": 5000, "tier": "screening",
                 "method": "per_capita_proxy"},
            ]
            score_rows = [
                {"project_id": "p1", "name": "Project One", "total_score": 80.0,
                 "safety_score": 75, "equity_score": 80, "climate_score": 85,
                 "feasibility_score": 80, "sensitivity_flag": "LOW"},
                {"project_id": "p2", "name": "Project Two", "total_score": 65.5,
                 "safety_score": 60, "equity_score": 65, "climate_score": 70,
                 "feasibility_score": 65, "sensitivity_flag": "MED"},
            ]
            delta_rows = [
                {"scenario_id": "scenario-a", "origin_zone_id": "Z1", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible_baseline": 1200,
                 "jobs_accessible_scenario": 1400, "delta_jobs_accessible": 200},
            ]

            paths, blocks = render_standard_figures(
                accessibility_rows=accessibility_rows,
                vmt_rows=vmt_rows,
                score_rows=score_rows,
                delta_rows=delta_rows,
                figures_dir=figures_dir,
            )
            self.assertGreaterEqual(len(paths), 3)
            for path in paths:
                self.assertTrue(path.exists(), f"Expected figure at {path}")
                self.assertGreater(path.stat().st_size, 0, f"Figure {path} is empty")
                self.assertTrue(str(path).endswith(".png"))
            self.assertEqual(len(paths), len(blocks))
            for block in blocks:
                self.assertIn("figure_ref", block)
                self.assertIn("claim_text", block)
                self.assertIn("fact_id", block)


@unittest.skipUnless(_has_folium(), "folium not installed")
class MapsTest(unittest.TestCase):
    def _zones_geojson(self) -> dict:
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature",
                 "properties": {"zone_id": "Z1", "name": "North"},
                 "geometry": {"type": "Polygon",
                              "coordinates": [[[-121.6, 39.2], [-121.5, 39.2],
                                               [-121.5, 39.3], [-121.6, 39.3],
                                               [-121.6, 39.2]]]}},
                {"type": "Feature",
                 "properties": {"zone_id": "Z2", "name": "South"},
                 "geometry": {"type": "Polygon",
                              "coordinates": [[[-121.5, 39.2], [-121.4, 39.2],
                                               [-121.4, 39.3], [-121.5, 39.3],
                                               [-121.5, 39.2]]]}},
            ],
        }

    def test_render_standard_maps_produces_non_empty_html(self) -> None:
        from clawmodeler_engine.maps import render_standard_maps

        with tempfile.TemporaryDirectory() as temp_dir:
            zones_path = Path(temp_dir) / "zones.geojson"
            zones_path.write_text(json.dumps(self._zones_geojson()), encoding="utf-8")
            maps_dir = Path(temp_dir) / "maps"

            accessibility_rows = [
                {"scenario_id": "baseline", "origin_zone_id": "Z1", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 1200},
                {"scenario_id": "baseline", "origin_zone_id": "Z2", "mode": "car",
                 "cutoff_min": 30, "jobs_accessible": 800},
            ]
            socio_rows = [
                {"zone_id": "Z1", "population": 1500.0, "jobs": 400.0},
                {"zone_id": "Z2", "population": 1200.0, "jobs": 300.0},
            ]

            paths, blocks = render_standard_maps(
                zones_geojson_path=zones_path,
                accessibility_rows=accessibility_rows,
                socio_rows=socio_rows,
                project_rows=[],
                maps_dir=maps_dir,
                daily_vmt_per_capita=22.0,
            )
            self.assertGreaterEqual(len(paths), 3)
            for path in paths:
                self.assertTrue(path.exists())
                content = path.read_text(encoding="utf-8")
                self.assertIn("<html", content.lower())
                self.assertGreater(len(content), 1000)
            for block in blocks:
                self.assertIn("map_ref", block)
                self.assertIn("claim_text", block)


@unittest.skipUnless(_has_jinja2(), "jinja2 not installed")
class TemplatesTest(unittest.TestCase):
    def _minimal_manifest(self, workspace_root: Path, run_id: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "artifact_type": "run_manifest",
            "manifest_version": "1.0.0",
            "run_id": run_id,
            "app": {"name": "ClawModeler", "engine_version": "0.3.0"},
            "engine": {"routing_engine": "osmnx_networkx", "note": "test"},
            "workspace": {"root": str(workspace_root)},
            "inputs": [],
            "outputs": {"tables": [], "figures": [], "maps": [], "bridges": []},
            "scenarios": [{"scenario_id": "baseline"}],
            "methods": ["intake", "model_brain"],
            "assumptions": ["Screening-level only."],
            "fact_block_count": 2,
        }

    def _write_fact_blocks(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        blocks = [
            {"fact_id": "vmt-baseline", "fact_type": "vmt_screening",
             "claim_text": "Baseline daily VMT is 50,000.", "scenario_id": "baseline",
             "method_ref": "vmt.per_capita_proxy",
             "artifact_refs": [{"type": "table", "path": "t.csv"}]},
            {"fact_id": "score-top", "fact_type": "project_scoring",
             "claim_text": "Top project scores 80.", "scenario_id": None,
             "method_ref": "scoring.weighted_rubric",
             "artifact_refs": [{"type": "table", "path": "t.csv"}]},
        ]
        with path.open("w", encoding="utf-8") as file:
            for block in blocks:
                file.write(json.dumps(block))
                file.write("\n")

    def test_technical_report_includes_evidence_table(self) -> None:
        from clawmodeler_engine.report import render_technical_report

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_root = workspace / "runs" / "t1"
            self._write_fact_blocks(run_root / "outputs" / "tables" / "fact_blocks.jsonl")
            (run_root / "qa_report.json").parent.mkdir(parents=True, exist_ok=True)
            (run_root / "qa_report.json").write_text(
                json.dumps({"export_ready": True, "manifest_present": True,
                            "fact_blocks_present": True, "fact_block_count": 2,
                            "blockers": []}),
                encoding="utf-8",
            )
            output = render_technical_report(self._minimal_manifest(workspace, "t1"))
            self.assertIn("Technical Report", output)
            self.assertIn("Evidence (fact-blocks)", output)
            self.assertIn("vmt-baseline", output)
            self.assertIn("score-top", output)
            self.assertIn("QA status: **READY**", output)

    def test_layperson_report_has_headlines_and_findings(self) -> None:
        from clawmodeler_engine.report import render_layperson_report

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_root = workspace / "runs" / "t1"
            self._write_fact_blocks(run_root / "outputs" / "tables" / "fact_blocks.jsonl")
            (run_root / "qa_report.json").parent.mkdir(parents=True, exist_ok=True)
            (run_root / "qa_report.json").write_text(
                json.dumps({"export_ready": True, "manifest_present": True,
                            "fact_blocks_present": True, "fact_block_count": 2,
                            "blockers": []}),
                encoding="utf-8",
            )
            output = render_layperson_report(self._minimal_manifest(workspace, "t1"))
            self.assertIn("Planner Report", output)
            self.assertIn("Headline numbers", output)
            self.assertIn("Key findings", output)
            self.assertIn("screening-level", output)

    def test_stakeholder_brief_limits_to_five_findings(self) -> None:
        from clawmodeler_engine.report import render_stakeholder_brief

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_root = workspace / "runs" / "t1"
            self._write_fact_blocks(run_root / "outputs" / "tables" / "fact_blocks.jsonl")
            (run_root / "qa_report.json").parent.mkdir(parents=True, exist_ok=True)
            (run_root / "qa_report.json").write_text(
                json.dumps({"export_ready": True, "manifest_present": True,
                            "fact_blocks_present": True, "fact_block_count": 2,
                            "blockers": []}),
                encoding="utf-8",
            )
            output = render_stakeholder_brief(self._minimal_manifest(workspace, "t1"))
            self.assertIn("Stakeholder Brief", output)
            self.assertIn("Top findings", output)
            self.assertIn("fact-blocks grounding each claim", output)


if __name__ == "__main__":
    unittest.main()
