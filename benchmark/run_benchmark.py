"""Isolated benchmark test runner executing deterministic leap-year timezone edge-case bug."""

import os
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from autonomous_repair.config import RepairConfig
from autonomous_repair.pipeline import AutonomousRepairPipeline, PipelineResult


def run_benchmark() -> int:
    """Execute the end-to-end autonomous repair pipeline against the benchmark repository."""
    benchmark_repo = WORKSPACE_ROOT / "benchmark" / "repo"
    
    print("======================================================================")
    print("  AUTONOMOUS SOFTWARE REPAIR PIPELINE - BENCHMARK RUNNER")
    print("  Public-Interest Software Evaluation (UN SDGs 9 & 16)")
    print("======================================================================")
    print(f"Target Benchmark Repository: {benchmark_repo}\n")

    # Configure pipeline with strict anti-overfitting verification gates
    config = RepairConfig(
        max_repair_iterations=5,
        top_k_suspicious_blocks=5,
        min_suspiciousness_threshold=0.05,
        enforce_regression_gate=True,
        enforce_property_gate=True,
        enforce_mutation_gate=True,
        property_test_max_examples=100,
        min_mutation_score_threshold=0.65,
        target_repo_name="public-audit/civic-timestamp-service",
    )

    pipeline = AutonomousRepairPipeline(config=config)
    result: PipelineResult = pipeline.run(benchmark_repo)

    print("\n" + "=" * 70)
    print("BENCHMARK EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Pipeline Status:          {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Iterations Used:          {result.iterations_used}")
    print(f"Total Pipeline Runtime:   {result.total_pipeline_duration_seconds:.2f}s")

    if not result.success:
        print(f"Error: {result.error_message}")
        return 1

    # Print SBFL findings
    print("\n[Spectrum-Based Fault Localization Results]")
    print(f"Lines Scored: {len(result.ranked_lines)}")
    for i, line in enumerate(result.ranked_lines[:3], 1):
        print(f"  Rank #{i}: {line.file_path}:{line.line_number} -> Ochiai Score: {line.score:.4f} "
              f"(Failed: {line.failed_count}/{line.total_failed}, Passed: {line.passed_count}/{line.total_passed})")

    # Print Hypotheses
    if result.selected_candidate:
        print("\n[Formulated Root-Cause Hypotheses]")
        for idx, h in enumerate(result.selected_candidate.hypotheses, 1):
            print(f"  Hypothesis {idx}: {h}")
        print(f"\nSelected Mechanical Cause: {result.selected_candidate.chosen_hypothesis}")

    # Print Verification Matrix
    if result.verification_matrix:
        print("\n[Multi-Layer Verification Matrix]")
        print(result.verification_matrix.summary_table())

    # Write PR artifact
    if result.pr_package:
        output_pr_file = WORKSPACE_ROOT / "PULL_REQUEST.md"
        output_pr_file.write_text(result.pr_package.body_markdown, encoding="utf-8")
        print(f"✓ Reviewer-Ready PR saved to: {output_pr_file}")

    print("\n🎉 Benchmark passed with 100% verification compliance!")
    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark())
