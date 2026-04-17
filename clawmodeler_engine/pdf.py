from __future__ import annotations

from pathlib import Path
from typing import Any

from .report import render_report


class PdfDependencyMissingError(RuntimeError):
    pass


def _require_pdf_deps():
    try:
        from markdown_it import MarkdownIt
        from weasyprint import HTML
    except ModuleNotFoundError as error:
        raise PdfDependencyMissingError(
            "PDF export requires markdown-it-py and weasyprint. Install the pdf extra: "
            "`pip install clawmodeler-engine[pdf]` (WeasyPrint also needs system libs "
            "libpango and libcairo on Linux — see README for details)."
        ) from error
    return MarkdownIt, HTML


PDF_CSS = """
@page { size: Letter; margin: 0.75in; }
body { font-family: 'Helvetica', 'Arial', sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a202c; }
h1 { font-size: 22pt; margin: 0 0 0.4em 0; color: #2b6cb0; }
h2 { font-size: 15pt; margin: 1.2em 0 0.3em 0; color: #2c5282; border-bottom: 1px solid #cbd5e0; padding-bottom: 0.1em; }
h3 { font-size: 12pt; margin: 1em 0 0.3em 0; color: #2d3748; }
p, li { margin: 0.3em 0; }
ul, ol { margin: 0.3em 0 0.3em 1.4em; }
code { font-family: 'Menlo', 'Consolas', monospace; font-size: 9.5pt; background: #edf2f7; padding: 0 0.25em; border-radius: 2px; }
pre { background: #edf2f7; padding: 0.5em; border-radius: 3px; overflow: auto; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 9.5pt; }
th, td { border: 1px solid #cbd5e0; padding: 0.3em 0.5em; text-align: left; vertical-align: top; }
th { background: #edf2f7; font-weight: 600; }
img { max-width: 100%; height: auto; margin: 0.5em 0; }
blockquote { border-left: 3px solid #cbd5e0; margin: 0.5em 0; padding: 0.1em 0.8em; color: #4a5568; background: #f7fafc; }
a { color: #2b6cb0; text-decoration: underline; }
hr { border: none; border-top: 1px solid #cbd5e0; margin: 1em 0; }
"""


def render_pdf(
    manifest: dict[str, Any],
    report_type: str,
    reports_dir: Path,
    *,
    ai_narrative: dict[str, Any] | None = None,
) -> bytes:
    """Render a report-type to PDF bytes.

    ``reports_dir`` is used as the WeasyPrint ``base_url`` so relative
    figure paths (``../runs/<id>/outputs/figures/chart.png``) resolve
    against the same reference point the Markdown report uses.
    """

    MarkdownIt, HTML = _require_pdf_deps()
    markdown = render_report(manifest, report_type, ai_narrative=ai_narrative)
    html_body = MarkdownIt("commonmark", {"html": True}).enable("table").render(markdown)
    html_document = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{PDF_CSS}</style></head><body>{html_body}</body></html>"
    )
    base_url = str(reports_dir) + "/"
    return HTML(string=html_document, base_url=base_url).write_pdf()
