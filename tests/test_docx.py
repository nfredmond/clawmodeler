from __future__ import annotations

import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import (
    write_export,
    write_intake,
    write_plan,
    write_run,
)


def _docx_deps_available() -> bool:
    try:
        import docx  # noqa: F401
        import markdown_it  # noqa: F401

        return True
    except Exception:
        return False


@contextmanager
def demo_workspace(run_id: str = "docx"):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs = write_demo_inputs(root)
        workspace = root / "workspace"
        write_intake(
            workspace,
            [
                inputs["zones"],
                inputs["socio"],
                inputs["projects"],
                inputs["network_edges"],
                inputs["gtfs"],
            ],
        )
        write_plan(workspace, inputs["question"])
        write_run(workspace, run_id, ["baseline", "infill-growth"])
        yield workspace, run_id


@unittest.skipUnless(_docx_deps_available(), "python-docx and markdown-it-py required")
class DocxExportTest(unittest.TestCase):
    def test_each_report_type_renders_valid_docx(self) -> None:
        with demo_workspace() as (workspace, run_id):
            for report_type in ("technical", "layperson", "brief"):
                path = write_export(
                    workspace, run_id, "docx", report_type=report_type
                )
                self.assertIsInstance(path, Path)
                self.assertTrue(path.suffix == ".docx")
                self.assertTrue(
                    zipfile.is_zipfile(path),
                    f"{report_type} did not produce a valid DOCX (ZIP) container",
                )
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                    self.assertIn(
                        "word/document.xml",
                        names,
                        f"{report_type} DOCX missing word/document.xml",
                    )
                    body = zf.read("word/document.xml").decode("utf-8", errors="replace")
                # Every report type emits at least one heading via render_report.
                self.assertIn(
                    "<w:pStyle w:val=\"Heading",
                    body,
                    f"{report_type} DOCX has no heading paragraphs",
                )
                self.assertGreater(
                    path.stat().st_size,
                    2048,
                    f"{report_type} DOCX suspiciously small ({path.stat().st_size} bytes)",
                )

    def test_technical_report_round_trips_table(self) -> None:
        with demo_workspace() as (workspace, run_id):
            path = write_export(
                workspace, run_id, "docx", report_type="technical"
            )
            with zipfile.ZipFile(path) as zf:
                body = zf.read("word/document.xml").decode("utf-8", errors="replace")
            self.assertIn(
                "<w:tbl>",
                body,
                "technical DOCX should contain at least one table (scenarios, fact-blocks, or bridges)",
            )

    def test_all_report_types_via_format_all(self) -> None:
        with demo_workspace() as (workspace, run_id):
            paths = write_export(workspace, run_id, "docx", report_type="all")
            self.assertIsInstance(paths, list)
            self.assertEqual(len(paths), 3)
            for path in paths:
                self.assertTrue(path.suffix == ".docx")
                self.assertTrue(zipfile.is_zipfile(path))

    def test_docx_with_grounded_ai_narrative(self) -> None:
        from clawmodeler_engine.llm import FakeProvider

        with demo_workspace() as (workspace, run_id):
            fact_ids_path = (
                workspace
                / "runs"
                / run_id
                / "outputs"
                / "tables"
                / "fact_blocks.jsonl"
            )
            import json

            fact_ids: list[str] = []
            with fact_ids_path.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        fact_ids.append(json.loads(line)["fact_id"])
            self.assertGreaterEqual(len(fact_ids), 2)

            provider = FakeProvider(
                canned_text=(
                    f"Baseline VMT screening looks stable. [fact:{fact_ids[0]}] "
                    f"Jobs access improves under build. [fact:{fact_ids[1]}]"
                ),
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                path = write_export(
                    workspace,
                    run_id,
                    "docx",
                    report_type="technical",
                    ai_narrative=True,
                )
            self.assertTrue(zipfile.is_zipfile(path))
            self.assertGreater(path.stat().st_size, 2048)


class DocxQaGateTest(unittest.TestCase):
    """DOCX export must share the QA gate with Markdown and PDF."""

    def test_empty_workspace_blocks_docx_export(self) -> None:
        from clawmodeler_engine.orchestration import QaGateBlockedError

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir(parents=True)
            with self.assertRaises(QaGateBlockedError):
                write_export(workspace, "nonexistent", "docx")


class DocxDependencyMissingTest(unittest.TestCase):
    def test_missing_deps_raises_with_install_hint(self) -> None:
        from clawmodeler_engine.docx import (
            DocxDependencyMissingError,
            _require_docx_deps,
        )

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def fake_import(name, *args, **kwargs):
            if name in ("docx", "markdown_it"):
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(DocxDependencyMissingError) as ctx:
                _require_docx_deps()
            self.assertIn("docx", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
