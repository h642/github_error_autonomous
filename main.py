"""CLI entrypoint for the Autonomous Software Repair Pipeline (UN SDGs 9 & 16)."""

import argparse
import os
import sys
from pathlib import Path

from autonomous_repair.config import RepairConfig
from autonomous_repair.pipeline import AutonomousRepairPipeline, PipelineResult


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autonomous Software Repair Pipeline for Public-Interest Software (UN SDGs 9 & 16)"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=str(Path(__file__).resolve().parent / "benchmark" / "repo"),
        help="Path to repository to repair (default: benchmark/repo)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run deterministic leap-year benchmark scenario",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=os.getenv("LLM_PROVIDER", "mock"),
        choices=["openai", "anthropic", "gemini", "mock"],
        help="LLM provider for hypothesis and patch synthesis (default: mock/deterministic)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("LLM_MODEL", "gpt-4o"),
        help="Model name (e.g., gpt-4o, claude-3-5-sonnet-20241022)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum repair iterations ceiling (default: 5)",
    )
    parser.add_argument(
        "--output-pr",
        type=str,
        default="PULL_REQUEST.md",
        help="Output filepath for generated Pull Request markdown (default: PULL_REQUEST.md)",
    )
    parser.add_argument(
        "--no-property",
        action="store_true",
        help="Disable Gate 2 Property-Based Testing",
    )
    parser.add_argument(
        "--no-mutation",
        action="store_true",
        help="Disable Gate 3 Mutation Testing",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"Error: Target repository path does not exist: {repo_path}")
        sys.exit(1)

    config = RepairConfig(
        llm_provider=args.provider,
        llm_model=args.model,
        max_repair_iterations=args.max_iterations,
        enforce_property_gate=not args.no_property,
        enforce_mutation_gate=not args.no_mutation,
    )

    pipeline = AutonomousRepairPipeline(config=config)
    result: PipelineResult = pipeline.run(repo_path)

    if result.pr_package and args.output_pr:
        out_file = Path(args.output_pr).resolve()
        out_file.write_text(result.pr_package.body_markdown, encoding="utf-8")
        print(f"\n✓ Generated Reviewer-Ready Pull Request written to: {out_file}")

    if result.success:
        print("\nPipeline finished successfully.")
        sys.exit(0)
    else:
        print(f"\nPipeline failed: {result.error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
