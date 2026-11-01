"""End-to-end Autonomous Software Repair Pipeline orchestrator."""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from autonomous_repair.config import RepairConfig
from autonomous_repair.localization.context_extractor import ASTContextExtractor, SuspiciousBlock
from autonomous_repair.localization.coverage_tracer import CoverageTracer
from autonomous_repair.localization.ochiai import LineSuspiciousness, OchiaiCalculator
from autonomous_repair.pr_generator.pr_packager import PRPackager, PullRequestPackage
from autonomous_repair.sandbox import AbstractSandbox, create_sandbox
from autonomous_repair.synthesis.diff_parser import parse_unified_diff
from autonomous_repair.synthesis.llm_client import BaseLLMClient, RepairCandidate, get_llm_client
from autonomous_repair.verification.verification_matrix import MultiLayerVerifier, VerificationMatrix


@dataclass
class PipelineResult:
    """Complete outcome of the autonomous repair pipeline execution."""
    success: bool
    iterations_used: int
    ranked_lines: List[LineSuspiciousness]
    top_blocks: List[SuspiciousBlock]
    selected_candidate: Optional[RepairCandidate]
    verification_matrix: Optional[VerificationMatrix]
    pr_package: Optional[PullRequestPackage]
    error_message: str = ""
    total_pipeline_duration_seconds: float = 0.0


class AutonomousRepairPipeline:
    """End-to-end pipeline executing all 5 stages of autonomous software repair."""

    def __init__(
        self,
        config: Optional[RepairConfig] = None,
        custom_llm_client: Optional[BaseLLMClient] = None,
        event_callback: Optional[callable] = None,
    ):
        self.config = config or RepairConfig()
        self.llm_client = custom_llm_client or get_llm_client(self.config)
        self.pr_packager = PRPackager(self.config)
        self.event_callback = event_callback

    def _emit(self, event_type: str, data: dict) -> None:
        if self.event_callback:
            try:
                self.event_callback(event_type, data)
            except Exception:
                pass

    def run(
        self,
        repo_path: Union[str, Path],
        target_issue: Optional[str] = None,
    ) -> PipelineResult:
        start_time = time.perf_counter()
        repo = Path(repo_path).resolve()
        sandbox: Optional[AbstractSandbox] = None
        issue_ctx = None

        print("=" * 70)
        print("AUTONOMOUS SOFTWARE REPAIR PIPELINE (UN SDGs 9 & 16)")
        print(f"Target Repository: {repo}")
        if target_issue:
            print(f"Target Issue: {target_issue}")
        print("=" * 70)

        try:
            # Stage 1: Secure Sandboxing & Ingestion
            self._emit("stage_change", {"stage": 1, "title": "Secure Sandboxing & Ingestion", "status": "running"})
            print("\n[Stage 1/5] Initializing Secure Ephemeral Sandbox & Ingestion...")
            sandbox = create_sandbox(
                repo_path=repo,
                prefer_docker=self.config.use_docker_if_available,
                timeout_seconds=self.config.sandbox_timeout_seconds,
            )
            print(f"  ✓ Sandbox provisioned: {sandbox.sandbox_dir}")
            print(f"  ✓ Detected Ecosystem: {sandbox.manifest_info.ecosystem}")
            print(f"  ✓ Test Command: {sandbox.manifest_info.default_test_command}")

            self._emit("log", {"level": "info", "message": f"Sandbox provisioned: {sandbox.sandbox_dir}"})
            self._emit("log", {"level": "info", "message": f"Detected Ecosystem: {sandbox.manifest_info.ecosystem} | Framework: {sandbox.manifest_info.test_framework}"})

            # Check if GitHub Issue Mode is active
            if target_issue:
                from autonomous_repair.issue_mode import IssueFetcher, ReproductionAgent
                issue_ctx = IssueFetcher.resolve_issue(target_issue)
                self._emit("log", {"level": "info", "message": f"Targeting Issue: {issue_ctx.title} ({issue_ctx.url or 'User Bug Report'})"})
                self._emit("issue_targeted", {
                    "title": issue_ctx.title,
                    "number": issue_ctx.issue_number,
                    "url": issue_ctx.url,
                    "description": issue_ctx.description,
                })

                # Synthesize reproducing test
                self._emit("log", {"level": "info", "message": "Synthesizing minimal reproduction unit test for reported issue..."})
                repro_agent = ReproductionAgent(sandbox, self.llm_client)
                repro_res = repro_agent.synthesize_and_validate(issue_ctx)

                if repro_res.reproduced:
                    self._emit("log", {"level": "warning", "message": f"✓ Issue reproduced via {repro_res.test_file_path}! Test failure confirmed."})
                else:
                    self._emit("log", {"level": "info", "message": f"Added test {repro_res.test_file_path} to verify issue resolution."})

            # Run baseline tests
            baseline_run = sandbox.run_tests()

            # Auto-heal missing dependencies if baseline failed due to ModuleNotFoundError
            for attempt in range(3):
                if baseline_run.exit_code in (2, 4) and ("ModuleNotFoundError" in baseline_run.combined_output or "No module named" in baseline_run.combined_output):
                    missing_pkgs = re.findall(r"No module named ['\"]([^'\"]+)['\"]", baseline_run.combined_output)
                    if missing_pkgs:
                        pkg = missing_pkgs[0].split(".")[0].strip()
                        # Map removed standard library modules in Python 3.13+ to backport packages
                        pkg_map = {
                            "cgi": "legacy-cgi",
                            "pipes": "legacy-pipes",
                        }
                        install_pkg = pkg_map.get(pkg, pkg)
                        print(f"  ⚡ Detected missing dependency '{pkg}'. Auto-installing {install_pkg} into sandbox environment...")
                        self._emit("log", {"level": "info", "message": f"Detected missing dependency '{pkg}'. Auto-installing {install_pkg}..."})
                        install_res = sandbox.execute(f"python3 -m pip install {install_pkg}")
                        if install_res.success:
                            self._emit("log", {"level": "success", "message": f"Installed '{pkg}'. Re-running test collection..."})
                            baseline_run = sandbox.run_tests()
                            if baseline_run.success:
                                break
                        else:
                            break
                    else:
                        break
                else:
                    break

            if baseline_run.success:
                print("  ✓ All baseline tests pass! No faults detected in target repository.")
                self._emit("stage_change", {"stage": 1, "title": "Secure Sandboxing & Ingestion", "status": "completed"})
                self._emit("log", {"level": "success", "message": "All baseline tests pass! No faults detected."})
                return PipelineResult(
                    success=True,
                    iterations_used=0,
                    ranked_lines=[],
                    top_blocks=[],
                    selected_candidate=None,
                    verification_matrix=None,
                    pr_package=None,
                    error_message="Repository tests are already passing.",
                    total_pipeline_duration_seconds=time.perf_counter() - start_time,
                )

            print(f"  ✗ Baseline test failure confirmed (Exit code: {baseline_run.exit_code}).")
            self._emit("log", {"level": "warning", "message": f"Baseline test suite failure confirmed (Exit code: {baseline_run.exit_code})"})
            self._emit("stage_change", {"stage": 1, "title": "Secure Sandboxing & Ingestion", "status": "completed"})

            # Stage 2: Spectrum-Based Fault Localization (SBFL)
            self._emit("stage_change", {"stage": 2, "title": "Spectrum-Based Fault Localization (SBFL)", "status": "running"})
            print("\n[Stage 2/5] Running Spectrum-Based Fault Localization (Ochiai SBFL)...")
            tracer = CoverageTracer(sandbox)
            test_traces = tracer.trace_all()

            if len(test_traces) == 0 and baseline_run.exit_code in (2, 4):
                # Tests could not even be collected (syntax error or environment failure)
                clean_err = baseline_run.stderr.strip() or baseline_run.stdout.strip()
                first_lines = "\n".join(clean_err.splitlines()[-8:])
                error_msg = (
                    f"Pytest could not collect or execute test cases (Exit code {baseline_run.exit_code}).\n"
                    f"Possible causes: Missing build tools, C-extensions, or unsupported environment.\n"
                    f"Details:\n{first_lines}"
                )
                print(f"  ✗ {error_msg}")
                self._emit("log", {"level": "error", "message": error_msg})
                self._emit("pipeline_failed", {"error": error_msg})
                return PipelineResult(
                    success=False,
                    iterations_used=0,
                    ranked_lines=[],
                    top_blocks=[],
                    selected_candidate=None,
                    verification_matrix=None,
                    pr_package=None,
                    error_message=error_msg,
                    total_pipeline_duration_seconds=time.perf_counter() - start_time,
                )

            print(f"  ✓ Collected coverage traces across {len(test_traces)} individual test cases.")
            self._emit("log", {"level": "info", "message": f"Collected coverage traces across {len(test_traces)} individual test cases."})

            def file_content_reader(fpath: str, lineno: int) -> str:
                try:
                    lines = sandbox.read_file(fpath).splitlines()
                    return lines[lineno - 1] if 0 < lineno <= len(lines) else ""
                except Exception:
                    return ""

            ranked_lines = OchiaiCalculator.calculate(test_traces, file_content_getter=file_content_reader)
            print(f"  ✓ Calculated Ochiai suspiciousness for {len(ranked_lines)} executable statements.")
            if ranked_lines:
                print(f"  ✓ Top suspicious line: {ranked_lines[0].file_path}:{ranked_lines[0].line_number} "
                      f"(Ochiai Score: {ranked_lines[0].score:.4f}, failed={ranked_lines[0].failed_count}, passed={ranked_lines[0].passed_count})")
                self._emit("log", {"level": "info", "message": f"Top suspicious line: {ranked_lines[0].file_path}:{ranked_lines[0].line_number} (Ochiai: {ranked_lines[0].score:.4f})"})

            extractor = ASTContextExtractor(sandbox, context_padding=self.config.surrounding_context_lines)
            top_blocks = extractor.extract_top_k_blocks(
                ranked_lines=ranked_lines,
                top_k=self.config.top_k_suspicious_blocks,
                min_score=self.config.min_suspiciousness_threshold,
            )
            print(f"  ✓ Extracted top-{len(top_blocks)} suspicious AST function/context blocks.")

            self._emit("sbfl_results", {
                "total_scored_lines": len(ranked_lines),
                "top_lines": [
                    {
                        "file": l.file_path,
                        "line": l.line_number,
                        "score": round(l.score, 4),
                        "failed": l.failed_count,
                        "passed": l.passed_count,
                        "code": l.code_content,
                    }
                    for l in ranked_lines[:10]
                ],
                "top_blocks": [
                    {
                        "file": b.file_path,
                        "function": b.function_name,
                        "start_line": b.start_line,
                        "end_line": b.end_line,
                        "score": round(b.max_suspiciousness_score, 4),
                        "snippet": b.code_snippet,
                    }
                    for b in top_blocks
                ]
            })
            self._emit("stage_change", {"stage": 2, "title": "Spectrum-Based Fault Localization (SBFL)", "status": "completed"})

            # Stage 3 & 4: Multi-Hypothesis Iterative Synthesis & Multi-Layer Verification Gate
            iteration = 1
            feedback: Optional[str] = None
            verifier = MultiLayerVerifier(sandbox, self.config)

            candidate: Optional[RepairCandidate] = None
            verification_matrix: Optional[VerificationMatrix] = None

            while iteration <= self.config.max_repair_iterations:
                print(f"\n--- Iteration {iteration}/{self.config.max_repair_iterations} ---")
                self._emit("stage_change", {"stage": 3, "title": f"Multi-Hypothesis Synthesis (Iteration {iteration}/{self.config.max_repair_iterations})", "status": "running"})
                self._emit("log", {"level": "info", "message": f"Starting synthesis iteration {iteration}/{self.config.max_repair_iterations} via {self.config.llm_provider.upper()}..."})

                # Synthesis
                print("  [Stage 3] Synthesizing hypotheses and candidate patch...")
                candidate = self.llm_client.generate_repair(
                    test_failure_log=baseline_run.combined_output,
                    suspicious_blocks=top_blocks,
                    iteration=iteration,
                    prior_verification_feedback=feedback,
                )

                print(f"    ✓ Formulated {len(candidate.hypotheses)} distinct root-cause hypotheses.")
                for idx, hyp in enumerate(candidate.hypotheses, 1):
                    print(f"      - Hyp {idx}: {hyp[:80]}...")
                print(f"    ✓ Selected Root Cause: {candidate.chosen_hypothesis[:80]}...")

                self._emit("synthesis_results", {
                    "iteration": iteration,
                    "hypotheses": candidate.hypotheses,
                    "chosen_hypothesis": candidate.chosen_hypothesis,
                    "explanation": candidate.explanation,
                    "unified_diff": candidate.unified_diff,
                })
                self._emit("stage_change", {"stage": 3, "title": "Multi-Hypothesis Synthesis", "status": "completed"})

                if not candidate.unified_diff:
                    print("    ✗ No valid unified diff generated.")
                    feedback = "Agent failed to generate a unified git diff block."
                    self._emit("log", {"level": "error", "message": "Synthesizer did not produce a valid unified diff block."})
                    iteration += 1
                    continue

                # Extract list of patched files
                patches = parse_unified_diff(candidate.unified_diff)
                patched_files = [p.new_path or p.old_path for p in patches]

                # Backup clean pre-patch file contents for instant, reliable rollback if verification fails
                pre_patch_snapshots = {}
                for rel_p in patched_files:
                    try:
                        pre_patch_snapshots[rel_p] = sandbox.read_file(rel_p)
                    except Exception:
                        pass

                # Apply patch to sandbox
                print("    ✓ Applying unified diff to sandbox...")
                patch_apply_res = sandbox.apply_patch(candidate.unified_diff)
                if not patch_apply_res.success:
                    print(f"    ✗ Patch failed to apply: {patch_apply_res.stderr}")
                    feedback = f"Unified diff failed to apply cleanly: {patch_apply_res.stderr}"
                    self._emit("log", {"level": "error", "message": f"Candidate patch failed to apply: {patch_apply_res.stderr}"})
                    iteration += 1
                    continue

                # Stage 4: Multi-Layer Verification
                self._emit("stage_change", {"stage": 4, "title": "Multi-Layer Verification Gates (Anti-Overfitting)", "status": "running"})
                print("  [Stage 4] Evaluating Multi-Layer Verification Gates (Anti-Overfitting)...")
                verification_matrix = verifier.verify_patch(
                    patched_files=patched_files,
                    baseline_test_cmd=sandbox.manifest_info.default_test_command,
                )

                gate1_pass = verification_matrix.regression.passed
                gate2_pass = verification_matrix.property_fuzz.passed if verification_matrix.property_fuzz else True
                gate3_pass = verification_matrix.mutation.passed if verification_matrix.mutation else True

                print(f"    - Gate 1 (Regression Check): {'PASSED' if gate1_pass else 'FAILED'}")
                if not gate1_pass:
                    print(f"    - Gate 1 Failures ({verification_matrix.regression.failed_tests}/{verification_matrix.regression.total_tests}):\n{verification_matrix.regression.failure_details}")
                    self._emit("log", {"level": "warning", "message": f"Gate 1 Failures: {verification_matrix.regression.failure_details}"})
                if verification_matrix.property_fuzz:
                    print(f"    - Gate 2 (Property Fuzzing): {'PASSED' if gate2_pass else 'FAILED'}")
                if verification_matrix.mutation:
                    print(f"    - Gate 3 (Mutation Testing): {'PASSED' if gate3_pass else 'FAILED'} (Score: {verification_matrix.mutation.mutation_score * 100:.1f}%)")

                self._emit("verification_results", {
                    "iteration": iteration,
                    "all_passed": verification_matrix.all_passed,
                    "gate1": {
                        "name": "Regression Tests",
                        "passed": gate1_pass,
                        "passed_count": verification_matrix.regression.passed_tests,
                        "total_count": verification_matrix.regression.total_tests,
                    },
                    "gate2": {
                        "name": "Generative Property Fuzzing (Hypothesis)",
                        "passed": gate2_pass,
                        "examples": verification_matrix.property_fuzz.examples_evaluated if verification_matrix.property_fuzz else 0,
                        "counterexample": verification_matrix.property_fuzz.shrunk_counterexample if verification_matrix.property_fuzz else None,
                    },
                    "gate3": {
                        "name": "Mutation Testing (AST Mutator)",
                        "passed": gate3_pass,
                        "score": round(verification_matrix.mutation.mutation_score * 100, 1) if verification_matrix.mutation else 100.0,
                        "killed": verification_matrix.mutation.killed_mutants if verification_matrix.mutation else 0,
                        "total": verification_matrix.mutation.total_mutants if verification_matrix.mutation else 0,
                    }
                })

                if verification_matrix.all_passed:
                    print("\n  🎉 All Verification Gates PASSED! Anti-overfitting criteria satisfied.")
                    self._emit("stage_change", {"stage": 4, "title": "Multi-Layer Verification Gates", "status": "completed"})
                    self._emit("log", {"level": "success", "message": "All verification gates PASSED! Anti-overfitting verified."})
                    break
                else:
                    print("    ✗ Candidate patch failed verification gates. Providing feedback for next iteration...")
                    feedback = verification_matrix.feedback_for_next_iteration
                    self._emit("log", {"level": "warning", "message": "Patch failed anti-overfitting gate. Re-feeding counterexample into synthesizer..."})
                    # Instantly roll back modified files to pre-patch state for next iteration
                    for rel_p, original_content in pre_patch_snapshots.items():
                        try:
                            sandbox.write_file(rel_p, original_content)
                        except Exception:
                            pass
                    iteration += 1

            if not verification_matrix or not verification_matrix.all_passed or not candidate:
                self._emit("pipeline_failed", {"error": "Exceeded max repair iterations."})
                return PipelineResult(
                    success=False,
                    iterations_used=iteration - 1,
                    ranked_lines=ranked_lines,
                    top_blocks=top_blocks,
                    selected_candidate=candidate,
                    verification_matrix=verification_matrix,
                    pr_package=None,
                    error_message=f"Exceeded max repair iterations ({self.config.max_repair_iterations}) without passing all verification gates.",
                    total_pipeline_duration_seconds=time.perf_counter() - start_time,
                )

            scenario_name = (
                f"Fix #{issue_ctx.issue_number}: {issue_ctx.title}"
                if issue_ctx and issue_ctx.issue_number
                else (issue_ctx.title if issue_ctx else "Autonomous Fault Resolution")
            )
            pr_package = self.pr_packager.package(
                candidate=candidate,
                matrix=verification_matrix,
                suspicious_lines=ranked_lines,
                bug_scenario_name=scenario_name,
            )
            print("  ✓ Pull request packaging complete.")
            self._emit("log", {"level": "success", "message": "Reviewer-ready PR generated. Awaiting human-in-the-loop approval before pushing to GitHub."})

            # Capture full content of all verified patched files
            patched_files = {}
            try:
                for patch in parse_unified_diff(candidate.unified_diff):
                    rel = patch.new_path or patch.old_path
                    if rel:
                        try:
                            patched_files[rel] = sandbox.read_file(rel)
                        except Exception:
                            pass
            except Exception:
                pass
            total_elapsed = time.perf_counter() - start_time

            # Emit ready for approval event with complete report package
            self._emit("ready_for_approval", {
                "title": pr_package.title,
                "branch": pr_package.branch_name,
                "diff": candidate.unified_diff,
                "markdown": pr_package.body_markdown,
                "explanation": candidate.explanation,
                "hypotheses": candidate.hypotheses,
                "chosen_hypothesis": candidate.chosen_hypothesis,
                "matrix_table": verification_matrix.summary_table(),
                "duration": round(total_elapsed, 2),
                "iterations": iteration,
                "patched_files": patched_files,
            })

            return PipelineResult(
                success=True,
                iterations_used=iteration,
                ranked_lines=ranked_lines,
                top_blocks=top_blocks,
                selected_candidate=candidate,
                verification_matrix=verification_matrix,
                pr_package=pr_package,
                error_message="",
                total_pipeline_duration_seconds=total_elapsed,
            )

        finally:
            if sandbox:
                sandbox.cleanup()
