"""Context extractor for top-k suspicious functions and blocks (Stage 2: SBFL)."""

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from autonomous_repair.localization.ochiai import LineSuspiciousness
from autonomous_repair.sandbox.base import AbstractSandbox


@dataclass
class SuspiciousBlock:
    """A localized block of suspicious source code with surrounding context."""
    file_path: str
    function_name: str
    start_line: int
    end_line: int
    primary_suspicious_line: int
    max_suspiciousness_score: float
    code_snippet: str
    lines_info: List[Tuple[int, float, str]]  # (line_no, score, content)


class ASTContextExtractor:
    """Parses source AST to isolate enclosing functions/blocks for suspicious lines."""

    def __init__(self, sandbox: AbstractSandbox, context_padding: int = 6):
        self.sandbox = sandbox
        self.context_padding = context_padding
        self._file_cache: Dict[str, List[str]] = {}
        self._ast_cache: Dict[str, Optional[ast.AST]] = {}

    def _get_file_lines(self, rel_path: str) -> List[str]:
        if rel_path not in self._file_cache:
            try:
                content = self.sandbox.read_file(rel_path)
                self._file_cache[rel_path] = content.splitlines()
            except Exception:
                self._file_cache[rel_path] = []
        return self._file_cache[rel_path]

    def _get_ast(self, rel_path: str) -> Optional[ast.AST]:
        if rel_path not in self._ast_cache:
            try:
                content = self.sandbox.read_file(rel_path)
                self._ast_cache[rel_path] = ast.parse(content, filename=rel_path)
            except Exception:
                self._ast_cache[rel_path] = None
        return self._ast_cache[rel_path]

    def find_enclosing_function(self, rel_path: str, line_no: int) -> Tuple[str, int, int]:
        """Returns (function_name, start_line, end_line) enclosing line_no, or fallback window."""
        tree = self._get_ast(rel_path)
        file_lines = self._get_file_lines(rel_path)
        total_lines = len(file_lines)

        if tree:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = getattr(node, "lineno", 1)
                    end = getattr(node, "end_lineno", total_lines)
                    if start <= line_no <= end:
                        return node.name, start, end

        # Fallback window if not in a function or if parsing failed
        start = max(1, line_no - self.context_padding)
        end = min(total_lines, line_no + self.context_padding)
        return "global_scope", start, end

    def extract_top_k_blocks(
        self,
        ranked_lines: List[LineSuspiciousness],
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> List[SuspiciousBlock]:
        """Group top suspicious lines into non-redundant enclosing blocks."""
        blocks: List[SuspiciousBlock] = []
        covered_regions: Dict[str, List[Tuple[int, int]]] = {}

        filtered_lines = [line for line in ranked_lines if line.score >= min_score]

        for s_line in filtered_lines:
            if len(blocks) >= top_k:
                break

            f_path = s_line.file_path
            line_no = s_line.line_number
            func_name, start_l, end_l = self.find_enclosing_function(f_path, line_no)

            # Check if this line is already covered in an existing block
            already_covered = False
            for c_start, c_end in covered_regions.get(f_path, []):
                if c_start <= line_no <= c_end:
                    already_covered = True
                    break

            if already_covered:
                continue

            # Record region
            if f_path not in covered_regions:
                covered_regions[f_path] = []
            covered_regions[f_path].append((start_l, end_l))

            # Build line content and snippet
            file_lines = self._get_file_lines(f_path)
            snippet_lines = []
            lines_info = []

            # Find suspicious scores in this block
            scores_in_block = {
                l.line_number: l.score for l in filtered_lines if l.file_path == f_path and start_l <= l.line_number <= end_l
            }

            for idx in range(start_l, end_l + 1):
                raw_code = file_lines[idx - 1] if idx <= len(file_lines) else ""
                score = scores_in_block.get(idx, 0.0)
                marker = f"[Ochiai={score:.3f}]" if score > 0 else "               "
                snippet_lines.append(f"{idx:4d} | {marker} {raw_code}")
                lines_info.append((idx, score, raw_code))

            block = SuspiciousBlock(
                file_path=f_path,
                function_name=func_name,
                start_line=start_l,
                end_line=end_l,
                primary_suspicious_line=line_no,
                max_suspiciousness_score=s_line.score,
                code_snippet="\n".join(snippet_lines),
                lines_info=lines_info,
            )
            blocks.append(block)

        return blocks
