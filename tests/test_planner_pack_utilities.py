from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clawmodeler_engine.planner_pack.utilities import (
    append_fact_blocks,
    coerce_str,
    jinja_env,
    manifest_artifact_paths,
    parse_optional_float,
    validate_fact_block_shape,
)


def _valid_block(fact_id: str) -> dict:
    return {
        "fact_id": fact_id,
        "fact_type": "test_block",
        "claim_text": "claim",
        "method_ref": "test.method",
        "artifact_refs": [{"path": "a.csv", "type": "table"}],
    }


class AppendFactBlocksTest(unittest.TestCase):
    def test_appends_new_blocks_and_creates_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "fact_blocks.jsonl"
            blocks = [_valid_block("a"), _valid_block("b")]
            appended = append_fact_blocks(path, blocks)
            self.assertEqual(appended, 2)
            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["fact_id"], "a")

    def test_skips_duplicate_fact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fact_blocks.jsonl"
            append_fact_blocks(path, [_valid_block("a")])
            appended = append_fact_blocks(
                path, [_valid_block("a"), _valid_block("b")]
            )
            self.assertEqual(appended, 1)
            ids = [json.loads(line)["fact_id"] for line in path.read_text().splitlines()]
            self.assertEqual(ids, ["a", "b"])

    def test_returns_zero_on_empty_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fact_blocks.jsonl"
            self.assertEqual(append_fact_blocks(path, []), 0)
            self.assertFalse(path.exists())


class CoerceStrTest(unittest.TestCase):
    def test_returns_default_for_missing(self) -> None:
        self.assertEqual(coerce_str(None, "fallback"), "fallback")
        self.assertEqual(coerce_str("", "fallback"), "fallback")
        self.assertEqual(coerce_str("   ", "fallback"), "fallback")

    def test_trims_and_returns_value(self) -> None:
        self.assertEqual(coerce_str("  hello  "), "hello")
        self.assertEqual(coerce_str(42), "42")


class ParseOptionalFloatTest(unittest.TestCase):
    def test_returns_none_for_missing(self) -> None:
        self.assertIsNone(parse_optional_float(None))
        self.assertIsNone(parse_optional_float(""))

    def test_returns_none_for_non_numeric(self) -> None:
        self.assertIsNone(parse_optional_float("not a number"))

    def test_parses_numeric_strings_and_numbers(self) -> None:
        self.assertEqual(parse_optional_float("3.14"), 3.14)
        self.assertEqual(parse_optional_float(2), 2.0)


class JinjaEnvTest(unittest.TestCase):
    def test_env_resolves_existing_planner_pack_template(self) -> None:
        env = jinja_env()
        template = env.get_template("ceqa_vmt.md.j2")
        self.assertIsNotNone(template)


class ManifestArtifactPathsTest(unittest.TestCase):
    def test_reads_current_manifest_string_and_list_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            run_root = workspace / "runs" / "demo"
            run_root.mkdir(parents=True)
            (workspace / "inputs").mkdir()
            overlay = workspace / "inputs" / "custom_cmaq.csv"
            overlay.write_text("project_id,pollutant\np1,nox\n", encoding="utf-8")
            run_root.joinpath("manifest.json").write_text(
                json.dumps(
                    {
                        "artifacts": {
                            "cmaq_overlay_csv": "inputs/custom_cmaq.csv",
                            "hsip_overlay_csv": [{"path": str(overlay)}],
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                manifest_artifact_paths(workspace, run_root, "cmaq_overlay_csv"),
                [overlay],
            )
            self.assertEqual(
                manifest_artifact_paths(workspace, run_root, "hsip_overlay_csv"),
                [overlay],
            )

    def test_reads_legacy_outputs_manifest_without_iterating_string_chars(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            run_root = workspace / "runs" / "demo"
            legacy_dir = run_root / "outputs"
            legacy_dir.mkdir(parents=True)
            overlay = workspace / "stip_overlay.csv"
            overlay.write_text("project_id,phase\np1,CON\n", encoding="utf-8")
            legacy_dir.joinpath("run_manifest.json").write_text(
                json.dumps({"artifacts": {"stip_overlay_csv": str(overlay)}}),
                encoding="utf-8",
            )

            self.assertEqual(
                manifest_artifact_paths(workspace, run_root, "stip_overlay_csv"),
                [overlay],
            )


class ValidateFactBlockShapeTest(unittest.TestCase):
    def test_accepts_well_formed_block(self) -> None:
        validate_fact_block_shape(_valid_block("x"))

    def test_rejects_missing_method_ref(self) -> None:
        block = _valid_block("x")
        del block["method_ref"]
        with self.assertRaisesRegex(ValueError, "method_ref"):
            validate_fact_block_shape(block)

    def test_rejects_empty_artifact_refs(self) -> None:
        block = _valid_block("x")
        block["artifact_refs"] = []
        with self.assertRaisesRegex(ValueError, "artifact_refs"):
            validate_fact_block_shape(block)

    def test_rejects_missing_fact_id(self) -> None:
        block = _valid_block("x")
        block["fact_id"] = ""
        with self.assertRaisesRegex(ValueError, "fact_id"):
            validate_fact_block_shape(block)


if __name__ == "__main__":
    unittest.main()
