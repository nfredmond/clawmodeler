"""LLM integration for ClawModeler AI-narrative reports.

The grounding contract is load-bearing: every narrative sentence must
cite a fact_id that exists in the run's fact_blocks.jsonl. Citation
enforcement is deterministic (regex + set membership), not an LLM judge.
"""

from .anthropic import (
    AnthropicMissingKeyError,
    AnthropicNotInstalledError,
    AnthropicProvider,
)
from .config import (
    CLOUD_PROVIDERS,
    CONFIG_FILENAME,
    SUPPORTED_PROVIDERS,
    LLMConfig,
    LLMConfigError,
    apply_updates,
    build_provider,
    config_path,
    default_config,
    load_config,
    parse_key_value_pairs,
    save_config,
)
from .grounding import (
    CITATION_PATTERN,
    GroundedOutput,
    GroundingIssue,
    GroundingMode,
    Sentence,
    split_sentences,
    validate_and_ground,
)
from .ollama import (
    DEFAULT_ENDPOINT as OLLAMA_DEFAULT_ENDPOINT,
)
from .ollama import (
    DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL,
)
from .ollama import (
    OllamaNotInstalledError,
    OllamaProvider,
)
from .openai import (
    OpenAIMissingKeyError,
    OpenAINotInstalledError,
    OpenAIProvider,
)
from .provider import (
    FakeProvider,
    GenerationResult,
    LLMProvider,
    ProviderProbe,
)

__all__ = [
    "AnthropicMissingKeyError",
    "AnthropicNotInstalledError",
    "AnthropicProvider",
    "CITATION_PATTERN",
    "CLOUD_PROVIDERS",
    "CONFIG_FILENAME",
    "FakeProvider",
    "GenerationResult",
    "GroundedOutput",
    "GroundingIssue",
    "GroundingMode",
    "LLMConfig",
    "LLMConfigError",
    "LLMProvider",
    "OLLAMA_DEFAULT_ENDPOINT",
    "OLLAMA_DEFAULT_MODEL",
    "OllamaNotInstalledError",
    "OllamaProvider",
    "OpenAIMissingKeyError",
    "OpenAINotInstalledError",
    "OpenAIProvider",
    "ProviderProbe",
    "SUPPORTED_PROVIDERS",
    "Sentence",
    "apply_updates",
    "build_provider",
    "config_path",
    "default_config",
    "load_config",
    "parse_key_value_pairs",
    "save_config",
    "split_sentences",
    "validate_and_ground",
]
