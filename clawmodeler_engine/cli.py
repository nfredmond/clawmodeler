from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path

from .bridge_prepare import prepare_all_bridges
from .bridge_validation import validate_all_bridges
from .demo import write_demo_inputs
from .dtalite_bridge import prepare_dtalite_bridge
from .matsim_bridge import prepare_matsim_bridge
from .orchestration import select_engine, write_export, write_intake, write_plan, write_run
from .project import init_workspace, starter_question
from .routing import build_osmnx_graphml, build_zone_node_map
from .sumo_bridge import prepare_sumo_bridge, run_sumo_bridge, validate_sumo_bridge
from .tbest_bridge import prepare_tbest_bridge
from .toolbox import assess_toolbox, toolbox_summary_lines
from .urbansim_bridge import prepare_urbansim_bridge
from .workflow import (
    diagnose_workflow,
    run_demo_full_workflow,
    run_full_workflow,
    run_report_only_workflow,
)
from .workspace import (
    ENGINE_VERSION,
    ClawModelerError,
    InsufficientDataError,
    ensure_workspace,
    read_json,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ClawModelerError as error:
        print(str(error), file=sys.stderr)
        return error.exit_code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawmodeler-engine")
    parser.add_argument("--version", action="version", version=f"%(prog)s {ENGINE_VERSION}")
    subparsers = parser.add_subparsers(required=True)

    init = subparsers.add_parser("init", help="Create a ClawModeler workspace template.")
    init.add_argument("--workspace", required=True, type=Path)
    init.add_argument("--force", action="store_true", help="Overwrite starter files.")
    init.set_defaults(func=command_init)

    scaffold = subparsers.add_parser(
        "scaffold",
        help="Write starter artifacts planners can edit.",
    )
    scaffold_subparsers = scaffold.add_subparsers(required=True)
    scaffold_question = scaffold_subparsers.add_parser(
        "question",
        help="Write a starter question.json at the given path.",
    )
    scaffold_question.add_argument("--path", required=True, type=Path)
    scaffold_question.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing file at the same path.",
    )
    scaffold_question.add_argument("--title", help="Optional title override.")
    scaffold_question.add_argument(
        "--place-query",
        dest="place_query",
        help="Optional OSMnx place query for geography.place_query.",
    )
    scaffold_question.set_defaults(func=command_scaffold_question)

    intake = subparsers.add_parser("intake", help="Stage and validate workspace inputs.")
    intake.add_argument("--workspace", required=True, type=Path)
    intake.add_argument("--inputs", required=True, nargs="+", type=Path)
    intake.set_defaults(func=command_intake)

    plan = subparsers.add_parser("plan", help="Create an analysis and engine-selection plan.")
    plan.add_argument("--workspace", required=True, type=Path)
    plan.add_argument("--question", required=True, type=Path)
    plan.set_defaults(func=command_plan)

    run = subparsers.add_parser("run", help="Create a reproducible run manifest.")
    run.add_argument("--workspace", required=True, type=Path)
    run.add_argument("--run-id", required=True)
    run.add_argument("--scenarios", nargs="*", default=["baseline"])
    run.set_defaults(func=command_run)

    export = subparsers.add_parser("export", help="Export report artifacts when QA allows it.")
    export.add_argument("--workspace", required=True, type=Path)
    export.add_argument("--run-id", required=True)
    export.add_argument("--format", choices=["md", "pdf"], default="md")
    export.add_argument(
        "--report-type",
        choices=["technical", "layperson", "brief", "all"],
        default="technical",
        help="Which report template to render (default: technical).",
    )
    export.add_argument(
        "--ai-narrative",
        dest="ai_narrative",
        action="store_true",
        help=(
            "Generate a grounded AI narrative using the workspace llm_config; "
            "every sentence must cite a fact_id from the run or the export is blocked."
        ),
    )
    export.set_defaults(func=command_export)

    doctor = subparsers.add_parser("doctor", help="Check ClawModeler runtime dependencies.")
    doctor.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output machine-readable JSON.",
    )
    doctor.set_defaults(func=command_doctor)

    tools = subparsers.add_parser("tools", help="List the ClawModeler agent toolbox.")
    tools.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output machine-readable JSON.",
    )
    tools.set_defaults(func=command_tools)

    demo = subparsers.add_parser("demo", help="Create and run a complete demo workspace.")
    demo.add_argument("--workspace", required=True, type=Path)
    demo.add_argument("--run-id", default="demo")
    demo.set_defaults(func=command_demo)

    workflow = subparsers.add_parser("workflow", help="Run end-to-end modeling workflows.")
    workflow_subparsers = workflow.add_subparsers(required=True)
    workflow_full = workflow_subparsers.add_parser(
        "full",
        help="Run intake, plan, model, export, prepare bridges, and validate bridges.",
    )
    workflow_full.add_argument("--workspace", required=True, type=Path)
    workflow_full.add_argument("--inputs", required=True, nargs="+", type=Path)
    workflow_full.add_argument("--question", required=True, type=Path)
    workflow_full.add_argument("--run-id", required=True)
    workflow_full.add_argument("--scenarios", nargs="*", default=["baseline"])
    workflow_full.add_argument("--format", choices=["md"], default="md")
    workflow_full.add_argument(
        "--skip-bridges",
        action="store_true",
        help="Skip bridge package preparation and validation.",
    )
    workflow_full.set_defaults(func=command_workflow_full)
    workflow_demo_full = workflow_subparsers.add_parser(
        "demo-full",
        help="Create demo inputs and run the full workflow including bridge packages.",
    )
    workflow_demo_full.add_argument("--workspace", required=True, type=Path)
    workflow_demo_full.add_argument("--run-id", default="demo")
    workflow_demo_full.set_defaults(func=command_workflow_demo_full)
    workflow_report_only = workflow_subparsers.add_parser(
        "report-only",
        help="Regenerate report artifacts for an existing run.",
    )
    workflow_report_only.add_argument("--workspace", required=True, type=Path)
    workflow_report_only.add_argument("--run-id", required=True)
    workflow_report_only.add_argument("--format", choices=["md"], default="md")
    workflow_report_only.add_argument("--scenario-id", default="baseline")
    workflow_report_only.add_argument(
        "--skip-bridge-validation",
        action="store_true",
        help="Do not refresh bridge validation before report export.",
    )
    workflow_report_only.set_defaults(func=command_workflow_report_only)
    workflow_diagnose = workflow_subparsers.add_parser(
        "diagnose",
        help="Inspect workspace readiness and recommend next actions.",
    )
    workflow_diagnose.add_argument("--workspace", required=True, type=Path)
    workflow_diagnose.add_argument("--run-id")
    workflow_diagnose.set_defaults(func=command_workflow_diagnose)

    bridge = subparsers.add_parser("bridge", help="Prepare or run external model bridges.")
    bridge_subparsers = bridge.add_subparsers(required=True)
    bridge_prepare_all = bridge_subparsers.add_parser(
        "prepare-all",
        help="Prepare every applicable bridge package.",
    )
    bridge_prepare_all.add_argument("--workspace", required=True, type=Path)
    bridge_prepare_all.add_argument("--run-id", required=True)
    bridge_prepare_all.add_argument("--scenario-id", default="baseline")
    bridge_prepare_all.set_defaults(func=command_bridge_prepare_all)
    bridge_validate = bridge_subparsers.add_parser(
        "validate",
        help="Validate all prepared bridge packages.",
    )
    bridge_validate.add_argument("--workspace", required=True, type=Path)
    bridge_validate.add_argument("--run-id", required=True)
    bridge_validate.add_argument("--scenario-id", default="baseline")
    bridge_validate.set_defaults(func=command_bridge_validate)
    bridge_sumo = bridge_subparsers.add_parser("sumo", help="Prepare or run SUMO bridge files.")
    bridge_sumo_subparsers = bridge_sumo.add_subparsers(required=True)
    bridge_sumo_prepare = bridge_sumo_subparsers.add_parser(
        "prepare",
        help="Generate SUMO plain network, trips, config, and scripts.",
    )
    bridge_sumo_prepare.add_argument("--workspace", required=True, type=Path)
    bridge_sumo_prepare.add_argument("--run-id", required=True)
    bridge_sumo_prepare.add_argument("--scenario-id", default="baseline")
    bridge_sumo_prepare.set_defaults(func=command_bridge_sumo_prepare)
    bridge_sumo_run = bridge_sumo_subparsers.add_parser(
        "run",
        help="Run a prepared SUMO bridge package when SUMO is installed.",
    )
    bridge_sumo_run.add_argument("--workspace", required=True, type=Path)
    bridge_sumo_run.add_argument("--run-id", required=True)
    bridge_sumo_run.add_argument("--scenario-id", default="baseline")
    bridge_sumo_run.set_defaults(func=command_bridge_sumo_run)
    bridge_sumo_validate = bridge_sumo_subparsers.add_parser(
        "validate",
        help="Validate a prepared SUMO bridge package.",
    )
    bridge_sumo_validate.add_argument("--workspace", required=True, type=Path)
    bridge_sumo_validate.add_argument("--run-id", required=True)
    bridge_sumo_validate.add_argument("--scenario-id", default="baseline")
    bridge_sumo_validate.set_defaults(func=command_bridge_sumo_validate)
    bridge_matsim = bridge_subparsers.add_parser("matsim", help="Prepare MATSim bridge files.")
    bridge_matsim_subparsers = bridge_matsim.add_subparsers(required=True)
    bridge_matsim_prepare = bridge_matsim_subparsers.add_parser(
        "prepare",
        help="Generate MATSim network, population, config, and run script.",
    )
    bridge_matsim_prepare.add_argument("--workspace", required=True, type=Path)
    bridge_matsim_prepare.add_argument("--run-id", required=True)
    bridge_matsim_prepare.add_argument("--scenario-id", default="baseline")
    bridge_matsim_prepare.set_defaults(func=command_bridge_matsim_prepare)
    bridge_urbansim = bridge_subparsers.add_parser(
        "urbansim",
        help="Prepare UrbanSim bridge files.",
    )
    bridge_urbansim_subparsers = bridge_urbansim.add_subparsers(required=True)
    bridge_urbansim_prepare = bridge_urbansim_subparsers.add_parser(
        "prepare",
        help="Generate UrbanSim zone, household, job, building, and config tables.",
    )
    bridge_urbansim_prepare.add_argument("--workspace", required=True, type=Path)
    bridge_urbansim_prepare.add_argument("--run-id", required=True)
    bridge_urbansim_prepare.add_argument("--scenario-id", default="baseline")
    bridge_urbansim_prepare.set_defaults(func=command_bridge_urbansim_prepare)
    bridge_dtalite = bridge_subparsers.add_parser(
        "dtalite",
        help="Prepare DTALite bridge files.",
    )
    bridge_dtalite_subparsers = bridge_dtalite.add_subparsers(required=True)
    bridge_dtalite_prepare = bridge_dtalite_subparsers.add_parser(
        "prepare",
        help="Generate DTALite node, link, demand, and settings files.",
    )
    bridge_dtalite_prepare.add_argument("--workspace", required=True, type=Path)
    bridge_dtalite_prepare.add_argument("--run-id", required=True)
    bridge_dtalite_prepare.add_argument("--scenario-id", default="baseline")
    bridge_dtalite_prepare.set_defaults(func=command_bridge_dtalite_prepare)
    bridge_tbest = bridge_subparsers.add_parser("tbest", help="Prepare TBEST bridge files.")
    bridge_tbest_subparsers = bridge_tbest.add_subparsers(required=True)
    bridge_tbest_prepare = bridge_tbest_subparsers.add_parser(
        "prepare",
        help="Generate TBEST stop, route, service, and config files.",
    )
    bridge_tbest_prepare.add_argument("--workspace", required=True, type=Path)
    bridge_tbest_prepare.add_argument("--run-id", required=True)
    bridge_tbest_prepare.add_argument("--scenario-id", default="baseline")
    bridge_tbest_prepare.set_defaults(func=command_bridge_tbest_prepare)

    graph = subparsers.add_parser("graph", help="Prepare routing graph caches.")
    graph_subparsers = graph.add_subparsers(required=True)
    graph_osmnx = graph_subparsers.add_parser("osmnx", help="Build OSMnx GraphML cache.")
    graph_osmnx.add_argument("--workspace", required=True, type=Path)
    graph_osmnx.add_argument("--place", required=True)
    graph_osmnx.add_argument("--network-type", default="drive")
    graph_osmnx.add_argument("--graph-id", default="osmnx")
    graph_osmnx.set_defaults(func=command_graph_osmnx)

    graph_map_zones = graph_subparsers.add_parser(
        "map-zones",
        help="Create a zone_id to GraphML node_id mapping from staged zones.",
    )
    graph_map_zones.add_argument("--workspace", required=True, type=Path)
    graph_map_zones.add_argument("--graph", type=Path, help="GraphML path to map against.")
    graph_map_zones.add_argument(
        "--output",
        type=Path,
        help="Output CSV path. Defaults to <workspace>/inputs/zone_node_map.csv.",
    )
    graph_map_zones.set_defaults(func=command_graph_map_zones)

    llm = subparsers.add_parser(
        "llm",
        help="Inspect and configure the AI-narrative LLM provider.",
    )
    llm_subparsers = llm.add_subparsers(required=True)
    llm_doctor = llm_subparsers.add_parser(
        "doctor",
        help="Probe the configured LLM provider and print reachability.",
    )
    llm_doctor.add_argument("--workspace", required=True, type=Path)
    llm_doctor.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Output machine-readable JSON.",
    )
    llm_doctor.set_defaults(func=command_llm_doctor)

    llm_configure = llm_subparsers.add_parser(
        "configure",
        help="Update llm_config.json with key=value pairs.",
    )
    llm_configure.add_argument("--workspace", required=True, type=Path)
    llm_configure.add_argument(
        "pairs",
        nargs="+",
        metavar="KEY=VALUE",
        help="One or more key=value updates (e.g. provider=ollama model=phi3:mini).",
    )
    llm_configure.set_defaults(func=command_llm_configure)

    chat = subparsers.add_parser(
        "chat",
        help="Ask a grounded question against a finished run's fact_blocks.",
    )
    chat.add_argument("--workspace", required=True, type=Path)
    chat.add_argument("--run-id", dest="run_id", required=True)
    chat.add_argument(
        "--message",
        required=True,
        help="Planner question to ask against the run.",
    )
    chat.add_argument(
        "--no-history",
        dest="no_history",
        action="store_true",
        help="Ignore prior chat_history.jsonl turns when building the prompt.",
    )
    chat.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full ChatTurn payload as JSON.",
    )
    chat.set_defaults(func=command_chat)

    planner = subparsers.add_parser(
        "planner-pack",
        help="Produce Planner Pack regulatory deliverables (CEQA, LAPM, RTP, equity).",
    )
    planner_subparsers = planner.add_subparsers(required=True)
    ceqa_vmt = planner_subparsers.add_parser(
        "ceqa-vmt",
        help="Compute CEQA §15064.3 VMT significance determinations for a run.",
    )
    ceqa_vmt.add_argument("--workspace", required=True, type=Path)
    ceqa_vmt.add_argument("--run-id", dest="run_id", required=True)
    ceqa_vmt.add_argument(
        "--project-type",
        dest="project_type",
        choices=["residential", "employment", "retail"],
        default="residential",
    )
    ceqa_vmt.add_argument(
        "--reference-label",
        dest="reference_label",
        choices=["regional", "citywide", "custom"],
        default="regional",
    )
    ceqa_vmt.add_argument(
        "--reference-vmt-per-capita",
        dest="reference_vmt_per_capita",
        type=float,
        default=None,
        help="Override the regional/citywide VMT-per-capita baseline. "
        "Defaults to analysis_plan.json question.daily_vmt_per_capita, then 22.0.",
    )
    ceqa_vmt.add_argument(
        "--threshold-pct",
        dest="threshold_pct",
        type=float,
        default=0.15,
        help="Fraction below the reference baseline that is deemed less than "
        "significant (OPR default 0.15).",
    )
    ceqa_vmt.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full CEQA result summary as JSON.",
    )
    ceqa_vmt.set_defaults(func=command_planner_pack_ceqa_vmt)

    lapm_exhibit = planner_subparsers.add_parser(
        "lapm-exhibit",
        help="Render Caltrans LAPM project programming fact sheets for a run.",
    )
    lapm_exhibit.add_argument("--workspace", required=True, type=Path)
    lapm_exhibit.add_argument("--run-id", dest="run_id", required=True)
    lapm_exhibit.add_argument(
        "--lead-agency",
        dest="lead_agency",
        default=None,
        help="Lead agency name (populates every fact sheet header).",
    )
    lapm_exhibit.add_argument(
        "--district",
        dest="district",
        default=None,
        help="Caltrans district label (e.g. 'District 3').",
    )
    lapm_exhibit.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full LAPM exhibit summary as JSON.",
    )
    lapm_exhibit.set_defaults(func=command_planner_pack_lapm_exhibit)

    rtp_chapter = planner_subparsers.add_parser(
        "rtp-chapter",
        help="Compose the RTP Projects and Performance chapter for a run.",
    )
    rtp_chapter.add_argument("--workspace", required=True, type=Path)
    rtp_chapter.add_argument("--run-id", dest="run_id", required=True)
    rtp_chapter.add_argument(
        "--agency",
        dest="agency",
        default=None,
        help="Lead agency / RTPA name that will adopt this chapter.",
    )
    rtp_chapter.add_argument(
        "--rtp-cycle",
        dest="rtp_cycle",
        default=None,
        help="RTP adoption cycle label (e.g. '2026 RTP').",
    )
    rtp_chapter.add_argument(
        "--chapter-title",
        dest="chapter_title",
        default=None,
        help="Override the default 'Projects and Performance' chapter title.",
    )
    rtp_chapter.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full RTP chapter summary as JSON.",
    )
    rtp_chapter.set_defaults(func=command_planner_pack_rtp_chapter)

    equity_lens = planner_subparsers.add_parser(
        "equity-lens",
        help="Apply the SB 535 / AB 1550 / tribal equity lens to a run.",
    )
    equity_lens.add_argument("--workspace", required=True, type=Path)
    equity_lens.add_argument("--run-id", dest="run_id", required=True)
    equity_lens.add_argument(
        "--agency",
        dest="agency",
        default=None,
        help="Lead agency name for the equity packet header.",
    )
    equity_lens.add_argument(
        "--dataset-note",
        dest="dataset_note",
        default=None,
        help="Override the default dataset-provenance note.",
    )
    equity_lens.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full equity lens summary as JSON.",
    )
    equity_lens.set_defaults(func=command_planner_pack_equity_lens)

    atp_packet = planner_subparsers.add_parser(
        "atp-packet",
        help="Draft a California ATP application packet for each scored project.",
    )
    atp_packet.add_argument("--workspace", required=True, type=Path)
    atp_packet.add_argument("--run-id", dest="run_id", required=True)
    atp_packet.add_argument(
        "--agency",
        dest="agency",
        default=None,
        help="Lead agency name for the ATP application header.",
    )
    atp_packet.add_argument(
        "--cycle",
        dest="cycle",
        default=None,
        help="ATP cycle label (e.g. 'ATP Cycle 7').",
    )
    atp_packet.add_argument(
        "--rtp-cycle-label",
        dest="rtp_cycle_label",
        default=None,
        help="Optional RTP cycle label (e.g. '2026 RTP') for consistency wording.",
    )
    atp_packet.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full ATP packet summary as JSON.",
    )
    atp_packet.set_defaults(func=command_planner_pack_atp_packet)

    hsip = planner_subparsers.add_parser(
        "hsip",
        help=(
            "Screen a run's candidate projects against FHWA HSIP "
            "(23 USC 148) cycle eligibility."
        ),
    )
    hsip.add_argument("--workspace", required=True, type=Path)
    hsip.add_argument("--run-id", dest="run_id", required=True)
    hsip.add_argument(
        "--cycle-year",
        dest="cycle_year",
        required=True,
        type=int,
        help="HSIP cycle year (e.g. 2027).",
    )
    hsip.add_argument(
        "--cycle-label",
        dest="cycle_label",
        default=None,
        help="Optional HSIP cycle label (e.g. 'HSIP Cycle 12').",
    )
    hsip.add_argument(
        "--min-bc-ratio",
        dest="min_bc_ratio",
        default=None,
        type=float,
        help="Minimum benefit-cost ratio (default 1.0).",
    )
    hsip.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full HSIP screen summary as JSON.",
    )
    hsip.set_defaults(func=command_planner_pack_hsip)

    cmaq = planner_subparsers.add_parser(
        "cmaq",
        help=(
            "Screen a run's candidate projects against FHWA CMAQ "
            "(23 USC 149) emissions-reduction eligibility."
        ),
    )
    cmaq.add_argument("--workspace", required=True, type=Path)
    cmaq.add_argument("--run-id", dest="run_id", required=True)
    cmaq.add_argument(
        "--analysis-year",
        dest="analysis_year",
        required=True,
        type=int,
        help="CMAQ analysis year (e.g. 2027).",
    )
    cmaq.add_argument(
        "--pollutants",
        dest="pollutants",
        default=None,
        help=(
            "Comma-separated list of pollutants to include "
            "(default: pm2_5,pm10,nox,voc,co)."
        ),
    )
    cmaq.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full CMAQ packet summary as JSON.",
    )
    cmaq.set_defaults(func=command_planner_pack_cmaq)

    stip = planner_subparsers.add_parser(
        "stip",
        help=(
            "Program a run's candidate projects into a California STIP "
            "cycle packet (S&HC §§14525-14529.11 and §188; CTC STIP Guidelines)."
        ),
    )
    stip.add_argument("--workspace", required=True, type=Path)
    stip.add_argument("--run-id", dest="run_id", required=True)
    stip.add_argument(
        "--cycle",
        dest="cycle_label",
        default=None,
        help="STIP cycle label (default: '2026 STIP').",
    )
    stip.add_argument(
        "--region",
        dest="region",
        choices=("north", "south"),
        default=None,
        help=(
            "Optional region filter (north / south per S&HC §188). When "
            "omitted, all overlay rows are programmed into the packet."
        ),
    )
    stip.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full STIP packet summary as JSON.",
    )
    stip.set_defaults(func=command_planner_pack_stip)

    diff = subparsers.add_parser(
        "diff",
        help="Compare two finished runs across engine and Planner Pack artifacts.",
    )
    diff.add_argument("--workspace", required=True, type=Path)
    diff.add_argument(
        "--run-a",
        dest="run_a",
        required=True,
        help="Baseline run ID (the 'from' side of the diff).",
    )
    diff.add_argument(
        "--run-b",
        dest="run_b",
        required=True,
        help="Comparison run ID (the 'to' side of the diff).",
    )
    diff.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full diff summary as JSON.",
    )
    diff.set_defaults(func=command_diff)

    what_if = subparsers.add_parser(
        "what-if",
        help=(
            "Derive a new run from a finished baseline by applying "
            "deterministic parameter overrides (scoring weights, "
            "threshold_pct, project filters)."
        ),
    )
    what_if.add_argument("--workspace", required=True, type=Path)
    what_if.add_argument(
        "--base-run-id",
        dest="base_run_id",
        required=True,
        help="Finished run ID to derive from.",
    )
    what_if.add_argument(
        "--new-run-id",
        dest="new_run_id",
        required=True,
        help="New run ID (must not collide with an existing run).",
    )
    what_if.add_argument("--weight-safety", type=float, default=None)
    what_if.add_argument("--weight-equity", type=float, default=None)
    what_if.add_argument("--weight-climate", type=float, default=None)
    what_if.add_argument("--weight-feasibility", type=float, default=None)
    what_if.add_argument(
        "--reference-vmt-per-capita",
        dest="reference_vmt_per_capita",
        type=float,
        default=None,
        help="Recorded in manifest overrides for later planner-pack ceqa-vmt runs.",
    )
    what_if.add_argument(
        "--threshold-pct",
        dest="threshold_pct",
        type=float,
        default=None,
        help="CEQA VMT threshold fraction (0-1). Recorded in manifest overrides.",
    )
    what_if.add_argument(
        "--include-project",
        dest="include_project",
        action="append",
        default=None,
        help="Project ID to include (repeatable).",
    )
    what_if.add_argument(
        "--exclude-project",
        dest="exclude_project",
        action="append",
        default=None,
        help="Project ID to exclude (repeatable).",
    )
    what_if.add_argument(
        "--sensitivity-floor",
        dest="sensitivity_floor",
        choices=["LOW", "MEDIUM", "HIGH"],
        default=None,
        help="Drop rows whose sensitivity_flag is more assumption-heavy than the floor.",
    )
    what_if.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the WhatIfResult as JSON.",
    )
    what_if.set_defaults(func=command_what_if)

    portfolio = subparsers.add_parser(
        "portfolio",
        help=(
            "Summarize every run in the workspace as a single KPI row "
            "(screening score, VMT-flagged count, DAC share, engine "
            "version, base-run lineage)."
        ),
    )
    portfolio.add_argument("--workspace", required=True, type=Path)
    portfolio.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the PortfolioResult as JSON.",
    )
    portfolio.set_defaults(func=command_portfolio)

    return parser


def command_init(args: argparse.Namespace) -> None:
    result = init_workspace(args.workspace, force=args.force)
    print(json.dumps(result))


def command_scaffold_question(args: argparse.Namespace) -> None:
    path: Path = args.path
    if path.exists() and not args.force:
        raise ClawModelerError(
            f"{path} already exists. Pass --force to overwrite."
        )
    question = starter_question()
    if args.title:
        question["title"] = args.title
    if args.place_query:
        question["geography"]["place_query"] = args.place_query
    write_json(path, question)
    print(json.dumps({"question_path": str(path), "created": True}))


def command_intake(args: argparse.Namespace) -> None:
    path = write_intake(args.workspace, args.inputs)
    print(json.dumps({"intake_receipt": str(path)}))


def command_plan(args: argparse.Namespace) -> None:
    analysis_path, engine_path = write_plan(args.workspace, args.question)
    print(
        json.dumps(
            {
                "analysis_plan": str(analysis_path),
                "engine_selection": str(engine_path),
            }
        )
    )


def command_run(args: argparse.Namespace) -> None:
    manifest_path, qa_report_path = write_run(args.workspace, args.run_id, args.scenarios)
    qa_report = read_json(qa_report_path)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "qa_report": str(qa_report_path),
                "export_ready": qa_report["export_ready"],
            }
        )
    )


def command_export(args: argparse.Namespace) -> None:
    report_paths = write_export(
        args.workspace,
        args.run_id,
        args.format,
        report_type=args.report_type,
        ai_narrative=getattr(args, "ai_narrative", False),
    )
    if isinstance(report_paths, list):
        print(json.dumps({"reports": [str(path) for path in report_paths]}))
    else:
        print(json.dumps({"report": str(report_paths)}))


def command_doctor(args: argparse.Namespace) -> None:
    toolbox = assess_toolbox()
    checks = [
        {
            "name": tool["name"],
            "id": tool["id"],
            "status": tool["status"],
            "detail": tool["detail"],
            "category": tool["category"],
            "profile": tool["profile"],
        }
        for tool in toolbox["tools"]
    ]
    ok = all(check["status"] in {"ok", "optional"} for check in checks)
    payload = {"ok": ok, "checks": checks, "toolbox": toolbox}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(
                f"{check['status']}: {check['name']} "
                f"[{check['profile']}/{check['category']}] - {check['detail']}"
            )
    if not ok:
        raise InsufficientDataError("ClawModeler doctor found missing required dependencies.")


def command_tools(args: argparse.Namespace) -> None:
    assessment = assess_toolbox()
    if args.as_json:
        print(json.dumps(assessment, indent=2, sort_keys=True))
        return
    print("\n".join(toolbox_summary_lines(assessment)))


def command_demo(args: argparse.Namespace) -> None:
    inputs = write_demo_inputs(args.workspace)
    command_intake(
        Namespace(
            workspace=args.workspace,
            inputs=[
                inputs["zones"],
                inputs["socio"],
                inputs["projects"],
                inputs["network_edges"],
                inputs["gtfs"],
            ],
        )
    )
    command_plan(Namespace(workspace=args.workspace, question=inputs["question"]))
    command_run(
        Namespace(
            workspace=args.workspace,
            run_id=args.run_id,
            scenarios=["baseline", "infill-growth"],
        )
    )
    command_export(
        Namespace(
            workspace=args.workspace,
            run_id=args.run_id,
            format="md",
            report_type="technical",
        )
    )
    print(
        json.dumps(
            {
                "workspace": str(args.workspace),
                "run_id": args.run_id,
                "report": str(args.workspace / "reports" / f"{args.run_id}_report.md"),
            }
        )
    )


def command_workflow_full(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = run_full_workflow(
        args.workspace,
        input_paths=args.inputs,
        question_path=args.question,
        run_id=args.run_id,
        scenarios=args.scenarios,
        export_format=args.format,
        prepare_bridges=not args.skip_bridges,
    )
    report = read_json(path)
    print(
        json.dumps(
            {
                "workflow_report": str(path),
                "report": report["artifacts"]["report"],
                "qa_export_ready": report["qa"]["export_ready"],
                "bridge_export_ready": (
                    report["bridge_validation"]["export_ready"]
                    if report.get("bridge_validation")
                    else None
                ),
                "detailed_engine_statuses": {
                    bridge: readiness["status"]
                    for bridge, readiness in (
                        report.get("detailed_engine_readiness", {}) or {}
                    ).get("engines", {}).items()
                },
            }
        )
    )


def command_workflow_demo_full(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = run_demo_full_workflow(args.workspace, run_id=args.run_id)
    report = read_json(path)
    print(
        json.dumps(
            {
                "workflow_report": str(path),
                "report": report["artifacts"]["report"],
                "qa_export_ready": report["qa"]["export_ready"],
                "bridge_export_ready": report["bridge_validation"]["export_ready"],
                "detailed_engine_statuses": {
                    bridge: readiness["status"]
                    for bridge, readiness in (
                        report.get("detailed_engine_readiness", {}) or {}
                    ).get("engines", {}).items()
                },
            }
        )
    )


def command_workflow_report_only(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = run_report_only_workflow(
        args.workspace,
        run_id=args.run_id,
        export_format=args.format,
        validate_bridges=not args.skip_bridge_validation,
        scenario_id=args.scenario_id,
    )
    report = read_json(path)
    print(
        json.dumps(
            {
                "workflow_report": str(path),
                "report": report["artifacts"]["report"],
                "qa_export_ready": report["qa"]["export_ready"],
                "bridge_export_ready": (
                    report["bridge_validation"]["export_ready"]
                    if report.get("bridge_validation")
                    else None
                ),
                "detailed_engine_statuses": {
                    bridge: readiness["status"]
                    for bridge, readiness in (
                        report.get("detailed_engine_readiness", {}) or {}
                    ).get("engines", {}).items()
                },
            }
        )
    )


def command_workflow_diagnose(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = diagnose_workflow(args.workspace, run_id=args.run_id)
    diagnosis = read_json(path)
    print(
        json.dumps(
            {
                "workflow_diagnosis": str(path),
                "run_id": diagnosis["run_id"],
                "recommendation_count": len(diagnosis["recommendations"]),
                "detailed_engine_statuses": {
                    bridge: readiness["status"]
                    for bridge, readiness in (
                        diagnosis.get("detailed_engine_readiness", {}) or {}
                    ).get("engines", {}).items()
                },
            }
        )
    )


def command_bridge_sumo_prepare(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_sumo_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"sumo_run_manifest": str(path)}))


def command_bridge_prepare_all(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_all_bridges(args.workspace, args.run_id, scenario_id=args.scenario_id)
    report = read_json(path)
    print(
        json.dumps(
            {
                "bridge_prepare_report": str(path),
                "prepared_count": len(report["prepared"]),
                "skipped_count": len(report["skipped"]),
                "failed_count": len(report["failed"]),
                "detailed_engine_statuses": {
                    bridge: readiness["status"]
                    for bridge, readiness in (
                        report.get("detailed_engine_readiness", {}) or {}
                    ).get("engines", {}).items()
                },
            }
        )
    )


def command_bridge_validate(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = validate_all_bridges(args.workspace, args.run_id, scenario_id=args.scenario_id)
    report = read_json(path)
    print(
        json.dumps(
            {
                "bridge_validation_report": str(path),
                "export_ready": report["export_ready"],
                "detailed_forecast_ready": report.get("detailed_forecast_ready"),
                "detailed_forecast_blockers": report.get("detailed_forecast_blockers", []),
            }
        )
    )


def command_bridge_sumo_run(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = run_sumo_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"sumo_run_manifest": str(path)}))


def command_bridge_sumo_validate(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = validate_sumo_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    report = read_json(path)
    print(json.dumps({"bridge_qa_report": str(path), "export_ready": report["export_ready"]}))


def command_bridge_matsim_prepare(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_matsim_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"matsim_bridge_manifest": str(path)}))


def command_bridge_urbansim_prepare(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_urbansim_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"urbansim_bridge_manifest": str(path)}))


def command_bridge_dtalite_prepare(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_dtalite_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"dtalite_bridge_manifest": str(path)}))


def command_bridge_tbest_prepare(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = prepare_tbest_bridge(args.workspace, args.run_id, scenario_id=args.scenario_id)
    print(json.dumps({"tbest_bridge_manifest": str(path)}))


def command_graph_osmnx(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = build_osmnx_graphml(
        args.workspace,
        place=args.place,
        network_type=args.network_type,
        graph_id=args.graph_id,
    )
    print(json.dumps({"graphml": str(path)}))


def command_graph_map_zones(args: argparse.Namespace) -> None:
    ensure_workspace(args.workspace)
    path = build_zone_node_map(args.workspace, graph_path=args.graph, output_path=args.output)
    print(json.dumps({"zone_node_map": str(path)}))


def command_llm_doctor(args: argparse.Namespace) -> None:
    from .llm.config import CLOUD_PROVIDERS, build_provider, load_config

    ensure_workspace(args.workspace)
    config = load_config(args.workspace)
    provider = build_provider(config)
    probe = provider.probe()

    payload = {
        "provider": probe.provider,
        "model": probe.model,
        "ok": probe.ok,
        "detail": probe.detail,
        "metadata": probe.metadata,
        "grounding_mode": config.grounding_mode,
        "is_cloud": provider.is_cloud,
        "cloud_confirmed": config.cloud_confirmed,
    }

    if args.as_json:
        print(json.dumps(payload))
        return

    print(f"Provider: {probe.provider}")
    print(f"Model:    {probe.model}")
    print(f"Status:   {'OK' if probe.ok else 'FAIL'}")
    print(f"Detail:   {probe.detail}")
    print(f"Grounding mode: {config.grounding_mode}")

    if config.provider in CLOUD_PROVIDERS:
        print()
        print("CONFIDENTIALITY WARNING: this is a cloud provider.")
        print(
            "  Narrative prompts (including fact_blocks) will be sent to "
            f"{config.provider} servers when `export --ai-narrative` runs."
        )
        if config.cloud_confirmed:
            print("  Cloud use is confirmed in llm_config.json (cloud_confirmed=true).")
        else:
            print(
                "  Cloud use is NOT confirmed. Run "
                "`clawmodeler-engine llm configure cloud_confirmed=true` "
                "to allow `export --ai-narrative` to call this provider."
            )


def command_llm_configure(args: argparse.Namespace) -> None:
    from .llm.config import (
        CLOUD_PROVIDERS,
        apply_updates,
        load_config,
        parse_key_value_pairs,
        save_config,
    )

    ensure_workspace(args.workspace)
    try:
        updates = parse_key_value_pairs(args.pairs)
        config = load_config(args.workspace)
        new_config = apply_updates(config, updates)
        path = save_config(args.workspace, new_config)
    except ValueError as e:
        raise ClawModelerError(str(e)) from e

    payload = {
        "path": str(path),
        "provider": new_config.provider,
        "model": new_config.model,
        "grounding_mode": new_config.grounding_mode,
        "cloud_confirmed": new_config.cloud_confirmed,
    }
    if new_config.provider in CLOUD_PROVIDERS and not new_config.cloud_confirmed:
        payload["warning"] = (
            f"{new_config.provider} is a cloud provider; set "
            "cloud_confirmed=true to allow export --ai-narrative."
        )
    print(json.dumps(payload))


def command_chat(args: argparse.Namespace) -> None:
    from .chat import chat_from_workspace

    ensure_workspace(args.workspace)
    try:
        turn = chat_from_workspace(
            args.workspace,
            args.run_id,
            args.message,
            include_history=not args.no_history,
        )
    except InsufficientDataError:
        raise
    except ClawModelerError:
        raise

    if args.as_json:
        print(json.dumps(turn.to_json()))
        return

    print(f"[{turn.provider}/{turn.model}] turn {turn.turn_id}")
    print(turn.text)
    if turn.cited_fact_ids:
        print()
        print(f"Cited fact_ids: {', '.join(turn.cited_fact_ids)}")
    if turn.ungrounded_sentence_count:
        print(
            f"Dropped {turn.ungrounded_sentence_count} ungrounded sentence(s)."
        )
    if turn.unknown_fact_ids:
        print(f"Unknown fact_ids in model output: {', '.join(turn.unknown_fact_ids)}")


def command_planner_pack_ceqa_vmt(args: argparse.Namespace) -> None:
    from .planner_pack import write_ceqa_vmt

    ensure_workspace(args.workspace)
    summary = write_ceqa_vmt(
        args.workspace,
        args.run_id,
        project_type=args.project_type,
        reference_label=args.reference_label,
        reference_vmt_per_capita=args.reference_vmt_per_capita,
        threshold_pct=args.threshold_pct,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    print(
        f"CEQA §15064.3 VMT screening — {summary['scenario_count']} scenario(s), "
        f"threshold {summary['threshold_vmt_per_capita']} VMT/capita "
        f"({summary['reference_label']} × {1 - summary['threshold_pct']:.2f})"
    )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_lapm_exhibit(args: argparse.Namespace) -> None:
    from .planner_pack import DEFAULT_DISTRICT, DEFAULT_LEAD_AGENCY, write_lapm_exhibit

    ensure_workspace(args.workspace)
    summary = write_lapm_exhibit(
        args.workspace,
        args.run_id,
        lead_agency=args.lead_agency or DEFAULT_LEAD_AGENCY,
        district=args.district or DEFAULT_DISTRICT,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    print(
        f"Caltrans LAPM programming exhibits — {summary['project_count']} project(s), "
        f"lead agency: {summary['lead_agency']}, district: {summary['district']}."
    )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_rtp_chapter(args: argparse.Namespace) -> None:
    from .planner_pack import (
        DEFAULT_AGENCY,
        DEFAULT_CHAPTER_TITLE,
        DEFAULT_RTP_CYCLE,
        write_rtp_chapter,
    )

    ensure_workspace(args.workspace)
    summary = write_rtp_chapter(
        args.workspace,
        args.run_id,
        agency=args.agency or DEFAULT_AGENCY,
        rtp_cycle=args.rtp_cycle or DEFAULT_RTP_CYCLE,
        chapter_title=args.chapter_title or DEFAULT_CHAPTER_TITLE,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    print(
        f"RTP chapter — {summary['project_count']} project(s), "
        f"{summary['scenario_count']} scenario(s), agency: {summary['agency']}, "
        f"cycle: {summary['rtp_cycle']}."
    )
    print(f"Report:           {summary['report_path']}")
    print(f"Projects CSV:     {summary['projects_csv_path']}")
    print(f"Scenarios CSV:    {summary['scenarios_csv_path']}")
    print(f"JSON:             {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_equity_lens(args: argparse.Namespace) -> None:
    from .planner_pack import DEFAULT_EQUITY_AGENCY, write_equity_lens

    ensure_workspace(args.workspace)
    summary = write_equity_lens(
        args.workspace,
        args.run_id,
        agency=args.agency or DEFAULT_EQUITY_AGENCY,
        dataset_note=args.dataset_note,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    portfolio = summary["summary"] or {}
    print(
        f"Equity lens — {summary['project_count']} project(s), "
        f"{summary['overlay_supplied_count']} with overlay staged, "
        f"agency: {summary['agency']}."
    )
    if portfolio:
        print(
            f"  SB 535 DAC share: {portfolio['dac_share'] * 100:.1f}% "
            f"(AB 1550 target 25%){' — met' if portfolio['ab1550_dac_target_met'] else ' — not yet met'}."
        )
        print(
            f"  AB 1550 low-income within 1/2 mile of DAC share: "
            f"{portfolio['low_income_near_dac_share'] * 100:.1f}% "
            f"(target 10%){' — met' if portfolio['ab1550_low_income_near_dac_target_met'] else ' — not yet met'}."
        )
        print(
            f"  AB 1550 low-income outside 1/2 mile share: "
            f"{portfolio['low_income_share'] * 100:.1f}% "
            f"(target 5%){' — met' if portfolio['ab1550_low_income_target_met'] else ' — not yet met'}."
        )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_atp_packet(args: argparse.Namespace) -> None:
    from .planner_pack import DEFAULT_ATP_AGENCY, DEFAULT_ATP_CYCLE, write_atp_packet

    ensure_workspace(args.workspace)
    summary = write_atp_packet(
        args.workspace,
        args.run_id,
        agency=args.agency or DEFAULT_ATP_AGENCY,
        cycle=args.cycle or DEFAULT_ATP_CYCLE,
        rtp_cycle_label=args.rtp_cycle_label,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    portfolio = summary["summary"] or {}
    print(
        f"California ATP packet — {summary['application_count']} application "
        f"draft(s), agency: {summary['agency']}, cycle: {summary['cycle']}."
    )
    if portfolio:
        print(
            f"  Mean screening total score: "
            f"{portfolio['mean_total_score']}/100; "
            f"{portfolio['dac_application_count']} SB 535 DAC "
            f"({portfolio['dac_share'] * 100:.1f}%), "
            f"{portfolio['low_income_application_count']} AB 1550 low-income, "
            f"{portfolio['tribal_application_count']} tribal-area."
        )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_cmaq(args: argparse.Namespace) -> None:
    from .planner_pack import write_cmaq

    ensure_workspace(args.workspace)
    pollutants: list[str] | None = None
    if args.pollutants:
        pollutants = [
            token.strip()
            for token in args.pollutants.split(",")
            if token.strip()
        ]
    summary = write_cmaq(
        args.workspace,
        args.run_id,
        analysis_year=args.analysis_year,
        pollutants=pollutants,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    pollutant_totals = summary["total_kg_per_day_by_pollutant"] or {}
    totals_text = ", ".join(
        f"{p.upper().replace('PM2_5', 'PM2.5')} {kg:.3f} kg/day"
        for p, kg in pollutant_totals.items()
    ) or "no pollutant totals"
    print(
        f"CMAQ packet — {summary['project_count']} candidate(s), "
        f"{summary['estimate_count']} estimate(s), analysis year "
        f"{summary['analysis_year']}."
    )
    print(
        f"  Overlay staged for {summary['overlay_supplied_project_count']} "
        f"candidate(s); totals: {totals_text}."
    )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_stip(args: argparse.Namespace) -> None:
    from .planner_pack import DEFAULT_STIP_CYCLE_LABEL, write_stip

    ensure_workspace(args.workspace)
    summary = write_stip(
        args.workspace,
        args.run_id,
        cycle_label=args.cycle_label or DEFAULT_STIP_CYCLE_LABEL,
        region=args.region,
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    fy_totals = summary["total_cost_thousands_by_fiscal_year"] or {}
    fy_text = ", ".join(
        f"FY {fy} ${cost:,.0f}K" for fy, cost in fy_totals.items()
    ) or "no fiscal-year totals"
    split = summary["north_south_split"] or {}
    split_text = (
        (
            f"north {split['north_share'] * 100:.1f}% / "
            f"south {split['south_share'] * 100:.1f}% "
            f"({'meets' if split.get('meets_target') else 'does not yet meet'} "
            "40/60 target)"
        )
        if split
        else "no N/S split computed"
    )
    print(
        f"STIP packet — {summary['project_count']} candidate(s), "
        f"{summary['programming_row_count']} programming row(s), cycle "
        f"{summary['cycle_label']!r}"
        + (
            f" (region: {summary['region_filter']})"
            if summary["region_filter"]
            else ""
        )
        + "."
    )
    print(
        f"  Overlay staged for {summary['overlay_supplied_project_count']} "
        f"candidate(s); totals: {fy_text}."
    )
    print(f"  N/S split: {split_text}.")
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_planner_pack_hsip(args: argparse.Namespace) -> None:
    from .planner_pack import (
        DEFAULT_HSIP_CYCLE_LABEL,
        DEFAULT_HSIP_MIN_BC_RATIO,
        write_hsip,
    )

    ensure_workspace(args.workspace)
    summary = write_hsip(
        args.workspace,
        args.run_id,
        cycle_year=args.cycle_year,
        cycle_label=args.cycle_label or DEFAULT_HSIP_CYCLE_LABEL,
        min_bc_ratio=(
            args.min_bc_ratio
            if args.min_bc_ratio is not None
            else DEFAULT_HSIP_MIN_BC_RATIO
        ),
    )
    if args.as_json:
        print(json.dumps(summary))
        return
    print(
        f"HSIP screen — {summary['project_count']} candidate(s), "
        f"cycle year {summary['cycle_year']}, minimum B/C "
        f"{summary['min_bc_ratio']:.2f}."
    )
    print(
        f"  Overlay staged for {summary['overlay_supplied_count']} candidate(s); "
        f"{summary['bc_ratio_passes_count']} clear the B/C minimum; "
        f"{summary['proven_countermeasure_count']} report a proven countermeasure."
    )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
    print(f"Appended {summary['fact_block_count']} fact_block(s) to fact_blocks.jsonl.")


def command_diff(args: argparse.Namespace) -> None:
    from .diff import write_run_diff

    ensure_workspace(args.workspace)
    summary = write_run_diff(args.workspace, args.run_a, args.run_b)
    if args.as_json:
        print(json.dumps(summary))
        return
    totals = summary["totals"]
    print(
        f"Run diff {summary['run_a_id']} → {summary['run_b_id']}: "
        f"{totals['added']} added, {totals['removed']} removed, "
        f"{totals['changed']} changed, {totals['unchanged']} unchanged."
    )
    print(f"Report:   {summary['report_path']}")
    print(f"CSV:      {summary['csv_path']}")
    print(f"JSON:     {summary['json_path']}")
    print(f"Diff dir: {summary['diff_dir']}")
    print(
        f"Appended {summary['fact_block_count']} fact_block(s) to "
        f"{summary['diff_dir']}/fact_blocks.jsonl."
    )


def command_what_if(args: argparse.Namespace) -> None:
    from .what_if import WhatIfOverrides, write_what_if

    ensure_workspace(args.workspace)
    weight_keys = ("safety", "equity", "climate", "feasibility")
    weight_values = [
        getattr(args, f"weight_{key}") for key in weight_keys
    ]
    supplied = [v for v in weight_values if v is not None]
    scoring_weights: dict[str, float] | None
    if supplied:
        if len(supplied) != len(weight_values):
            raise ClawModelerError(
                "--weight-safety/--weight-equity/--weight-climate/"
                "--weight-feasibility must all be supplied together "
                "(they must sum to 1.0)."
            )
        scoring_weights = dict(zip(weight_keys, weight_values))
    else:
        scoring_weights = None
    overrides = WhatIfOverrides(
        scoring_weights=scoring_weights,
        reference_vmt_per_capita=args.reference_vmt_per_capita,
        threshold_pct=args.threshold_pct,
        project_ids_include=args.include_project,
        project_ids_exclude=args.exclude_project,
        sensitivity_floor=args.sensitivity_floor,
    )
    manifest_path, result = write_what_if(
        args.workspace, args.base_run_id, args.new_run_id, overrides
    )
    if args.as_json:
        print(json.dumps(result.to_json()))
        return
    print(
        f"What-if: `{result.base_run_id}` → `{result.new_run_id}` "
        f"({len(result.project_deltas)} project(s), "
        f"{len(result.dropped_project_ids)} dropped, "
        f"{result.new_fact_block_count} fact_block(s))."
    )
    print(f"Manifest: {manifest_path}")
    print(f"Report:   {args.workspace}/reports/{result.new_run_id}_what_if.md")


def command_portfolio(args: argparse.Namespace) -> None:
    from .portfolio import write_portfolio

    ensure_workspace(args.workspace)
    summary = write_portfolio(args.workspace)
    if args.as_json:
        print(json.dumps(summary))
        return
    portfolio_summary = summary.get("summary") or {}
    print(
        f"Portfolio: {summary['run_count']} run(s), "
        f"{portfolio_summary.get('export_ready_count', 0)} export-ready, "
        f"{summary['fact_block_count']} fact_block(s)."
    )
    print(f"Report: {summary['report_path']}")
    print(f"CSV:    {summary['csv_path']}")
    print(f"JSON:   {summary['json_path']}")
