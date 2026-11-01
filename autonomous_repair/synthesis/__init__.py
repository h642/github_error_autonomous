"""Synthesis module exports."""

from autonomous_repair.synthesis.diff_parser import (
    DiffHunk,
    FilePatch,
    parse_unified_diff,
    apply_patch_to_lines,
    apply_unified_diff_to_dir,
)
from autonomous_repair.synthesis.prompt_templates import SYSTEM_PROMPT, build_repair_user_prompt
from autonomous_repair.synthesis.llm_client import (
    BaseLLMClient,
    RepairCandidate,
    OpenAILRepairClient,
    AnthropicRepairClient,
    DeterministicBenchmarkClient,
    get_llm_client,
)

__all__ = [
    "DiffHunk",
    "FilePatch",
    "parse_unified_diff",
    "apply_patch_to_lines",
    "apply_unified_diff_to_dir",
    "SYSTEM_PROMPT",
    "build_repair_user_prompt",
    "BaseLLMClient",
    "RepairCandidate",
    "OpenAILRepairClient",
    "AnthropicRepairClient",
    "DeterministicBenchmarkClient",
    "get_llm_client",
]
