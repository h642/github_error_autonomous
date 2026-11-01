"""Gate 3: Mutation Testing Gate via AST mutant injection (Stage 4)."""

import ast
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from autonomous_repair.sandbox.base import AbstractSandbox


@dataclass
class Mutant:
    """Represents an injected AST mutant."""
    mutant_id: str
    file_path: str
    line_number: int
    original_op: str
    mutated_op: str
    description: str
    killed: bool = False
    killer_test_output: str = ""


@dataclass
class MutationGateResult:
    """Outcome of mutation testing."""
    passed: bool
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    mutation_score: float
    threshold: float
    mutants: List[Mutant]
    duration_seconds: float
    details: str


class ASTMutantGenerator(ast.NodeVisitor):
    """Generates synthetic mutants from Python AST."""

    # Operator replacement maps
    BIN_OP_MAP = {
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
        ast.Mult: ast.FloorDiv,
        ast.FloorDiv: ast.Mult,
        ast.Mod: ast.Add,
    }

    CMP_OP_MAP = {
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.Lt: ast.GtE,
        ast.LtE: ast.Gt,
        ast.Gt: ast.LtE,
        ast.GtE: ast.Lt,
    }

    BOOL_OP_MAP = {
        ast.And: ast.Or,
        ast.Or: ast.And,
    }

    def __init__(self, filename: str):
        self.filename = filename
        self.mutation_points: List[Tuple[int, str, str, str]] = []  # (lineno, type, orig, repl)

    def visit_BinOp(self, node: ast.BinOp):
        op_type = type(node.op)
        if op_type in self.BIN_OP_MAP:
            orig = op_type.__name__
            repl = self.BIN_OP_MAP[op_type].__name__
            self.mutation_points.append((node.lineno, "BinOp", orig, repl))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        for op in node.ops:
            op_type = type(op)
            if op_type in self.CMP_OP_MAP:
                orig = op_type.__name__
                repl = self.CMP_OP_MAP[op_type].__name__
                self.mutation_points.append((node.lineno, "Compare", orig, repl))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        op_type = type(node.op)
        if op_type in self.BOOL_OP_MAP:
            orig = op_type.__name__
            repl = self.BOOL_OP_MAP[op_type].__name__
            self.mutation_points.append((node.lineno, "BoolOp", orig, repl))
        self.generic_visit(node)


class ASTMutator(ast.NodeTransformer):
    """Applies a single specific mutation to an AST."""

    def __init__(self, target_line: int, target_type: str, repl_name: str):
        self.target_line = target_line
        self.target_type = target_type
        self.repl_name = repl_name
        self.applied = False

    def visit_BinOp(self, node: ast.BinOp):
        if not self.applied and node.lineno == self.target_line and self.target_type == "BinOp":
            repl_class = getattr(ast, self.repl_name)
            node.op = repl_class()
            self.applied = True
            return node
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        if not self.applied and node.lineno == self.target_line and self.target_type == "Compare":
            new_ops = []
            for op in node.ops:
                if not self.applied:
                    repl_class = getattr(ast, self.repl_name)
                    new_ops.append(repl_class())
                    self.applied = True
                else:
                    new_ops.append(op)
            node.ops = new_ops
            return node
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        if not self.applied and node.lineno == self.target_line and self.target_type == "BoolOp":
            repl_class = getattr(ast, self.repl_name)
            node.op = repl_class()
            self.applied = True
            return node
        return self.generic_visit(node)


class MutationGate:
    """Executes mutation testing by injecting AST mutants and running tests to calculate mutation score."""

    def __init__(self, sandbox: AbstractSandbox, threshold: float = 0.65, max_mutants: int = 3):
        self.sandbox = sandbox
        self.threshold = threshold
        self.max_mutants = max_mutants

    def evaluate(self, target_files: List[str], test_command: str = "python3 -m pytest -q -x --disable-warnings") -> MutationGateResult:
        start_time = time.perf_counter()
        all_mutants: List[Mutant] = []

        # Ensure fast-fail flag -x is included so pytest exits immediately on mutant failure
        if "-x" not in test_command:
            test_command = f"{test_command} -x --disable-warnings"

        for rel_file in target_files:
            if not rel_file.endswith(".py"):
                continue

            try:
                original_code = self.sandbox.read_file(rel_file)
                tree = ast.parse(original_code, filename=rel_file)
            except Exception:
                continue

            # Identify mutation opportunities
            generator = ASTMutantGenerator(rel_file)
            generator.visit(tree)

            # Limit mutants to configured maximum (default 3) for fast pipeline execution
            mutation_candidates = generator.mutation_points[:self.max_mutants]

            for idx, (lineno, op_cat, orig_op, repl_op) in enumerate(mutation_candidates):
                mutant_id = f"MUT_{Path(rel_file).stem}_{lineno}_{idx}"
                desc = f"Mutated {op_cat} on line {lineno}: {orig_op} -> {repl_op}"

                # Mutate AST
                try:
                    fresh_tree = ast.parse(original_code, filename=rel_file)
                    mutator = ASTMutator(lineno, op_cat, repl_op)
                    mutated_tree = mutator.visit(fresh_tree)
                    ast.fix_missing_locations(mutated_tree)
                    mutated_code = ast.unparse(mutated_tree)
                except Exception:
                    # Syntax or parse error means mutant is dead on arrival
                    all_mutants.append(Mutant(
                        mutant_id=mutant_id,
                        file_path=rel_file,
                        line_number=lineno,
                        original_op=orig_op,
                        mutated_op=repl_op,
                        description=desc,
                        killed=True,
                        killer_test_output="AST Mutator syntax error",
                    ))
                    continue

                # Write mutant into sandbox
                self.sandbox.write_file(rel_file, mutated_code)

                # Execute tests with fast 3s timeout
                res = self.sandbox.execute(test_command, timeout=3)

                # If tests fail (exit code != 0), the mutant was KILLED (desirable outcome)
                killed = (res.exit_code != 0)
                mutant = Mutant(
                    mutant_id=mutant_id,
                    file_path=rel_file,
                    line_number=lineno,
                    original_op=orig_op,
                    mutated_op=repl_op,
                    description=desc,
                    killed=killed,
                    killer_test_output=res.stdout if killed else "",
                )
                all_mutants.append(mutant)

                # Restore original patched code immediately
                self.sandbox.write_file(rel_file, original_code)

        # Compute mutation metrics
        total = len(all_mutants)
        killed_count = sum(1 for m in all_mutants if m.killed)
        survived_count = total - killed_count
        score = (killed_count / total) if total > 0 else 1.0
        passed = (score >= self.threshold)

        duration = time.perf_counter() - start_time
        details = (
            f"Injected {total} synthetic mutants: {killed_count} killed, {survived_count} survived. "
            f"Mutation Score: {score * 100:.1f}% (Threshold: {self.threshold * 100:.1f}%)."
        )

        return MutationGateResult(
            passed=passed,
            total_mutants=total,
            killed_mutants=killed_count,
            survived_mutants=survived_count,
            mutation_score=score,
            threshold=self.threshold,
            mutants=all_mutants,
            duration_seconds=duration,
            details=details,
        )
