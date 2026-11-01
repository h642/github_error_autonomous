"""Comprehensive unit test suite for the Autonomous Software Repair Pipeline components."""

import ast
import pytest

from autonomous_repair.config import RepairConfig
from autonomous_repair.localization.ochiai import OchiaiCalculator
from autonomous_repair.localization.coverage_tracer import TestCoverageResult
from autonomous_repair.sandbox.base import ManifestDetector
from autonomous_repair.synthesis.diff_parser import parse_unified_diff, apply_patch_to_lines
from autonomous_repair.verification.mutation_gate import ASTMutantGenerator, ASTMutator
from autonomous_repair.pr_generator.pr_packager import PRPackager
from autonomous_repair.verification.regression_gate import RegressionGateResult
from autonomous_repair.verification.property_gate import PropertyGateResult
from autonomous_repair.verification.mutation_gate import MutationGateResult
from autonomous_repair.verification.verification_matrix import VerificationMatrix
from autonomous_repair.synthesis.llm_client import RepairCandidate


def test_manifest_detection(tmp_path):
    """Stage 1: Verify automatic manifest detection."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    info = ManifestDetector.detect(tmp_path)
    assert info.ecosystem == "python"
    assert info.test_framework == "pytest"
    assert len(info.manifest_files) == 1


def test_ochiai_formula_calculation():
    """Stage 2: Verify Ochiai statistical formula computation:
    Score(s) = Failed(s) / sqrt( TotalFailed * (Failed(s) + Passed(s)) )
    """
    # 2 tests: 1 failed, 1 passed
    # Line 10 executed only in failing test: ef=1, ep=0, tf=1, tp=1
    # Ochiai = 1 / sqrt(1 * (1 + 0)) = 1.0
    trace1 = TestCoverageResult(
        test_id="test_fail",
        passed=False,
        executed_lines={"mod.py": {10, 20}},
        duration_seconds=0.1,
    )
    trace2 = TestCoverageResult(
        test_id="test_pass",
        passed=True,
        executed_lines={"mod.py": {20, 30}},
        duration_seconds=0.1,
    )

    scored = OchiaiCalculator.calculate([trace1, trace2])
    scored_dict = {(s.file_path, s.line_number): s.score for s in scored}

    assert scored_dict[("mod.py", 10)] == pytest.approx(1.0)
    # Line 20: ef=1, ep=1, tf=1 -> 1 / sqrt(1 * 2) = 1 / 1.4142 = 0.7071
    assert scored_dict[("mod.py", 20)] == pytest.approx(1.0 / (2.0 ** 0.5))
    # Line 30: ef=0, ep=1 -> 0.0
    assert scored_dict[("mod.py", 30)] == pytest.approx(0.0)


def test_unified_diff_parser_and_applier():
    """Stage 3: Verify unified git diff parsing and line modification."""
    diff_text = """--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
 def compute(x):
-    return x + 10
+    return x - 10
"""
    patches = parse_unified_diff(diff_text)
    assert len(patches) == 1
    assert patches[0].new_path == "foo.py"
    assert len(patches[0].hunks) == 1

    orig_lines = ["def compute(x):", "    return x + 10", ""]
    success, new_lines, err = apply_patch_to_lines(orig_lines, patches[0].hunks)
    assert success
    assert "    return x - 10" in new_lines
    assert "    return x + 10" not in new_lines


def test_ast_mutant_generation_and_mutation():
    """Stage 4: Verify AST mutation engine detects and mutates operators."""
    sample_code = """def calc(a, b):
    if a < b and b > 0:
        return a + b
    return a * b
"""
    tree = ast.parse(sample_code)
    gen = ASTMutantGenerator("test.py")
    gen.visit(tree)

    # Should detect Compare (<, >), BoolOp (and), and BinOp (+, *)
    ops = [p[1] for p in gen.mutation_points]
    assert "Compare" in ops
    assert "BoolOp" in ops
    assert "BinOp" in ops

    # Test AST mutator replacing BinOp Add with Sub
    mutator = ASTMutator(3, "BinOp", "Sub")
    mutated_tree = mutator.visit(tree)
    ast.fix_missing_locations(mutated_tree)
    mutated_code = ast.unparse(mutated_tree)
    assert "a - b" in mutated_code


def test_pr_packager_markdown_structure():
    """Stage 5: Verify reviewer-ready PR packaging generates all required sections."""
    config = RepairConfig()
    packager = PRPackager(config)

    candidate = RepairCandidate(
        hypotheses=[
            "Hyp 1: Offset sign inversion.",
            "Hyp 2: Leap year rollover boundary.",
            "Hyp 3: Subsecond precision error.",
        ],
        chosen_hypothesis="Hyp 1: Offset sign inversion.",
        explanation="Mechanical reason: inverted sign operation on timedelta.",
        unified_diff="--- a/mod.py\n+++ b/mod.py\n@@ -1,1 +1,1 @@\n- x + 1\n+ x - 1\n",
        raw_response="",
    )

    matrix = VerificationMatrix(
        regression=RegressionGateResult(
            passed=True, total_tests=5, passed_tests=5, failed_tests=0, duration_seconds=0.2, output=""
        ),
        property_fuzz=PropertyGateResult(
            passed=True, examples_evaluated=100, shrunk_counterexample=None,
            falsified_property=None, duration_seconds=0.5, output="", details="Passed"
        ),
        mutation=MutationGateResult(
            passed=True, total_mutants=10, killed_mutants=9, survived_mutants=1,
            mutation_score=0.9, threshold=0.65, mutants=[], duration_seconds=0.4, details="Passed"
        ),
        all_passed=True,
        total_duration_seconds=1.1,
    )

    pkg = packager.package(candidate, matrix)
    assert "SDG 9" in pkg.body_markdown
    assert "SDG 16" in pkg.body_markdown
    assert "Identified Root Cause & Mechanical Explanation" in pkg.body_markdown
    assert "Line-by-Line Logic Patch Summary" in pkg.body_markdown
    assert "Multi-Layer Verification Matrix" in pkg.body_markdown
    assert "90.0%" in pkg.body_markdown
