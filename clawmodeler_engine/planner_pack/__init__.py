"""Planner Pack — regulatory deliverables grounded in run fact_blocks.

Each submodule produces a deliverable planners hand to a client or
agency: a CEQA §15064.3 VMT significance memo, a Caltrans LAPM exhibit,
an RTP chapter, or an equity-lens overlay. Every deliverable reads from
a finished run's `fact_blocks.jsonl`, appends its own grounded
fact_blocks, and renders under the same citation contract that gates
`export --ai-narrative` and `chat`.
"""

from .atp import (
    ATP_DAC_SCORING_CATEGORIES,
    AtpGrantResult,
    AtpPortfolioSummary,
    AtpProjectApplication,
    atp_grant_fact_blocks,
    compute_atp_packet,
    render_atp_markdown,
    write_atp_packet,
)
from .atp import DEFAULT_AGENCY as DEFAULT_ATP_AGENCY
from .atp import DEFAULT_CYCLE as DEFAULT_ATP_CYCLE
from .ceqa import (
    OPR_DEFAULT_THRESHOLD_PCT,
    PROJECT_TYPES,
    REFERENCE_LABELS,
    CeqaVmtResult,
    CeqaVmtScenario,
    ceqa_vmt_fact_blocks,
    compute_ceqa_vmt,
    render_ceqa_vmt_markdown,
    write_ceqa_vmt,
)
from .cmaq import (
    ALLOWED_POLLUTANTS as CMAQ_ALLOWED_POLLUTANTS,
)
from .cmaq import (
    CmaqEmissionsEstimate,
    CmaqPortfolioSummary,
    CmaqResult,
    cmaq_fact_blocks,
    compute_cmaq,
    render_cmaq_markdown,
    write_cmaq,
)
from .equity import (
    AB1550_TARGET_DAC_SHARE,
    AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE,
    AB1550_TARGET_LOW_INCOME_SHARE,
    BENEFIT_CATEGORIES,
    DEFAULT_DATASET_NOTE,
    EquityLensResult,
    EquityPortfolioSummary,
    EquityProjectFinding,
    compute_equity_lens,
    equity_lens_fact_blocks,
    render_equity_lens_markdown,
    write_equity_lens,
)
from .equity import DEFAULT_AGENCY as DEFAULT_EQUITY_AGENCY
from .hsip import (
    DEFAULT_CYCLE_LABEL as DEFAULT_HSIP_CYCLE_LABEL,
)
from .hsip import (
    DEFAULT_MIN_BC_RATIO as DEFAULT_HSIP_MIN_BC_RATIO,
)
from .hsip import (
    HsipPortfolioSummary,
    HsipProjectScreen,
    HsipResult,
    compute_hsip,
    hsip_fact_blocks,
    render_hsip_markdown,
    write_hsip,
)
from .lapm import (
    DEFAULT_DISTRICT,
    DEFAULT_LEAD_AGENCY,
    LapmExhibitResult,
    LapmProgrammingExhibit,
    compute_lapm_exhibit,
    lapm_fact_blocks,
    render_lapm_markdown,
    write_lapm_exhibit,
)
from .rtp import (
    DEFAULT_AGENCY,
    DEFAULT_CHAPTER_TITLE,
    DEFAULT_RTP_CYCLE,
    RtpChapterResult,
    RtpProjectEntry,
    RtpScenarioEntry,
    compute_rtp_chapter,
    render_rtp_chapter_markdown,
    rtp_chapter_fact_blocks,
    write_rtp_chapter,
)
from .stip import (
    ALLOWED_PHASES as STIP_ALLOWED_PHASES,
)
from .stip import (
    ALLOWED_REGIONS as STIP_ALLOWED_REGIONS,
)
from .stip import (
    DEFAULT_CYCLE_LABEL as DEFAULT_STIP_CYCLE_LABEL,
)
from .stip import (
    StipPortfolioSummary,
    StipProgrammingRow,
    StipResult,
    compute_stip,
    render_stip_markdown,
    stip_fact_blocks,
    write_stip,
)

__all__ = [
    "AB1550_TARGET_DAC_SHARE",
    "AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE",
    "AB1550_TARGET_LOW_INCOME_SHARE",
    "ATP_DAC_SCORING_CATEGORIES",
    "AtpGrantResult",
    "AtpPortfolioSummary",
    "AtpProjectApplication",
    "BENEFIT_CATEGORIES",
    "CMAQ_ALLOWED_POLLUTANTS",
    "CmaqEmissionsEstimate",
    "CmaqPortfolioSummary",
    "CmaqResult",
    "DEFAULT_AGENCY",
    "DEFAULT_ATP_AGENCY",
    "DEFAULT_ATP_CYCLE",
    "DEFAULT_CHAPTER_TITLE",
    "DEFAULT_DATASET_NOTE",
    "DEFAULT_DISTRICT",
    "DEFAULT_EQUITY_AGENCY",
    "DEFAULT_HSIP_CYCLE_LABEL",
    "DEFAULT_HSIP_MIN_BC_RATIO",
    "DEFAULT_LEAD_AGENCY",
    "DEFAULT_RTP_CYCLE",
    "DEFAULT_STIP_CYCLE_LABEL",
    "EquityLensResult",
    "EquityPortfolioSummary",
    "EquityProjectFinding",
    "HsipPortfolioSummary",
    "HsipProjectScreen",
    "HsipResult",
    "LapmExhibitResult",
    "LapmProgrammingExhibit",
    "OPR_DEFAULT_THRESHOLD_PCT",
    "PROJECT_TYPES",
    "REFERENCE_LABELS",
    "RtpChapterResult",
    "RtpProjectEntry",
    "RtpScenarioEntry",
    "STIP_ALLOWED_PHASES",
    "STIP_ALLOWED_REGIONS",
    "StipPortfolioSummary",
    "StipProgrammingRow",
    "StipResult",
    "CeqaVmtResult",
    "CeqaVmtScenario",
    "atp_grant_fact_blocks",
    "ceqa_vmt_fact_blocks",
    "cmaq_fact_blocks",
    "compute_atp_packet",
    "compute_ceqa_vmt",
    "compute_cmaq",
    "compute_equity_lens",
    "compute_hsip",
    "compute_lapm_exhibit",
    "compute_rtp_chapter",
    "compute_stip",
    "equity_lens_fact_blocks",
    "hsip_fact_blocks",
    "lapm_fact_blocks",
    "render_atp_markdown",
    "render_ceqa_vmt_markdown",
    "render_cmaq_markdown",
    "render_equity_lens_markdown",
    "render_hsip_markdown",
    "render_lapm_markdown",
    "render_rtp_chapter_markdown",
    "render_stip_markdown",
    "rtp_chapter_fact_blocks",
    "stip_fact_blocks",
    "write_atp_packet",
    "write_ceqa_vmt",
    "write_cmaq",
    "write_equity_lens",
    "write_hsip",
    "write_lapm_exhibit",
    "write_rtp_chapter",
    "write_stip",
]
