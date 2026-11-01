"""Prompt engineering templates enforcing multi-hypothesis generation and minimal unified diffs (Stage 3)."""

from typing import List, Optional
from autonomous_repair.localization.context_extractor import SuspiciousBlock


SYSTEM_PROMPT = """You are an Autonomous Software Repair Agent operating on Public-Interest Software (aligned with UN SDGs 9 & 16: resilient digital infrastructure, peace, justice, and accountable institutions).

Your objective is to ingest localized faults, systematically analyze root causes, generate 3 to 5 distinct hypotheses, and synthesize minimal, correct unified git diff patches that resolve the failure without overfitting or breaking existing specifications.

CRITICAL INSTRUCTIONS:
1. HYPOTHESIS FORMULATION:
   Before providing any patch or code, you MUST formulate 3 to 5 distinct root-cause hypotheses explaining WHY the failure occurred from different architectural/algorithmic angles (e.g., edge-case input handling, temporal/timezone rollover, off-by-one boundary, state persistence flaw, type coercion).
2. MINIMAL UNIFIED GIT DIFF:
   Provide candidate patches strictly in standard Unified Git Diff format (`diff --git a/... b/...`, `--- a/...`, `+++ b/...`, `@@ ... @@`).
   Do NOT provide full files, markdown pseudocode, or conversational chatter inside the diff block.
3. ANTI-OVERFITTING:
   Do NOT simply hardcode a special case for the specific failing test value (e.g. `if val == "failing_val": return x`). Public interest software requires genuine general correctness that survives property-based generative fuzzing and mutation testing.

RESPONSE STRUCTURE FORMAT:
### HYPOTHESES
- Hypothesis 1: <Description & mechanism>
- Hypothesis 2: <Description & mechanism>
- Hypothesis 3: <Description & mechanism>
[Optional: Hypothesis 4 & 5]

### ROOT CAUSE SELECTION & EXPLANATION
<Identify which hypothesis is the true mechanical failure and explain why>

### PATCH
```diff
--- a/<path/to/file>
+++ b/<path/to/file>
@@ -<start>,<len> +<start>,<len> @@
<context and modifications>
```
"""


def build_repair_user_prompt(
    test_failure_log: str,
    suspicious_blocks: List[SuspiciousBlock],
    iteration: int = 1,
    prior_verification_feedback: Optional[str] = None,
) -> str:
    """Build structured user prompt containing test logs, SBFL blocks, and verification feedback."""
    blocks_text = []
    for i, b in enumerate(suspicious_blocks, 1):
        blocks_text.append(
            f"--- Suspicious Code Block {i}: {b.file_path} (Function: `{b.function_name}`, Lines {b.start_line}-{b.end_line}, Ochiai Score: {b.max_suspiciousness_score:.4f}) ---\n"
            f"{b.code_snippet}\n"
        )
    blocks_joined = "\n".join(blocks_text) if blocks_text else "No specific suspicious blocks localized."

    feedback_section = ""
    if prior_verification_feedback:
        feedback_section = f"""
### FEEDBACK FROM PREVIOUS REPAIR ATTEMPT (Iteration {iteration - 1}):
A previous patch failed our multi-layer verification gates. Please analyze why and address it:
{prior_verification_feedback}
"""

    return f"""### REPAIR TASK (Iteration {iteration})

### FAILING TEST SUITE OUTPUT & TRACE:
```
{test_failure_log.strip()}
```

### SPECTRUM-BASED FAULT LOCALIZATION (SBFL - Ochiai Top Suspicious Blocks):
{blocks_joined}
{feedback_section}
Please formulate 3 to 5 distinct root-cause hypotheses, select the true mechanical cause, and produce the minimal unified git diff.
"""
