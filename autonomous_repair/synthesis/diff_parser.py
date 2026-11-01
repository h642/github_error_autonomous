"""Unified git diff parsing, validation, and pure-Python patch application (Stage 3)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class DiffHunk:
    """Represents an individual unified diff hunk (@@ -start,len +start,len @@)."""
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: List[str]


@dataclass
class FilePatch:
    """Represents a patch for a single file in a unified diff."""
    old_path: str
    new_path: str
    hunks: List[DiffHunk]


def parse_unified_diff(diff_text: str) -> List[FilePatch]:
    """Parse a unified git diff into structured FilePatch and DiffHunk objects."""
    lines = diff_text.strip().splitlines()
    patches: List[FilePatch] = []
    current_patch: Optional[FilePatch] = None
    current_hunk: Optional[DiffHunk] = None

    hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    for line in lines:
        if line.startswith("--- "):
            old_path = line[4:].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
            current_patch = FilePatch(old_path=old_path, new_path="", hunks=[])
            current_hunk = None
        elif line.startswith("+++ "):
            new_path = line[4:].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            if current_patch:
                current_patch.new_path = new_path
                patches.append(current_patch)
        elif line.startswith("@@ "):
            match = hunk_header_re.match(line)
            if match and current_patch:
                old_start = int(match.group(1))
                old_len = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_len = int(match.group(4)) if match.group(4) else 1

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_len=old_len,
                    new_start=new_start,
                    new_len=new_len,
                    lines=[],
                )
                current_patch.hunks.append(current_hunk)
        elif current_hunk is not None:
            if line.startswith(("+", "-", " ", "\\")):
                current_hunk.lines.append(line)

    return patches


def apply_patch_to_lines(original_lines: List[str], hunks: List[DiffHunk]) -> Tuple[bool, List[str], str]:
    """Apply hunks sequentially to original file lines."""
    result_lines = list(original_lines)
    # Apply hunks in reverse line order so offsets remain valid
    sorted_hunks = sorted(hunks, key=lambda h: h.old_start, reverse=True)

    for hunk in sorted_hunks:
        start_idx = hunk.old_start - 1  # 1-indexed to 0-indexed
        # Extract hunk context lines and modifications
        old_slice_len = hunk.old_len
        new_slice: List[str] = []

        # Validate context matching if possible
        expected_old = [l[1:] for l in hunk.lines if l.startswith((" ", "-"))]
        
        # Check if hunk fits at start_idx or nearby
        best_match_idx = start_idx
        found = False
        
        # Search in a small window (-5 to +5 lines) in case line numbers shifted slightly
        search_range = [start_idx] + [start_idx + o for o in [1, -1, 2, -2, 3, -3, 4, -4, 5, -5]]
        for candidate_idx in search_range:
            if candidate_idx < 0 or candidate_idx + len(expected_old) > len(result_lines) + 1:
                continue
            matches = True
            for i, exp in enumerate(expected_old):
                if candidate_idx + i < len(result_lines):
                    if result_lines[candidate_idx + i].rstrip() != exp.rstrip():
                        matches = False
                        break
            if matches:
                best_match_idx = candidate_idx
                found = True
                break

        # Construct replacement lines
        for l in hunk.lines:
            if l.startswith("+"):
                new_slice.append(l[1:])
            elif l.startswith(" "):
                new_slice.append(l[1:])
            # '-' lines are deleted

        target_idx = best_match_idx if found else max(0, start_idx)
        delete_count = len(expected_old) if found else old_slice_len
        result_lines[target_idx : target_idx + delete_count] = new_slice

    return True, result_lines, ""


def apply_unified_diff_to_dir(root_dir: Path, diff_text: str) -> Tuple[bool, str]:
    """Apply a unified diff directly to files in root_dir."""
    patches = parse_unified_diff(diff_text)
    if not patches:
        return False, "No valid unified diff hunks found."

    for file_patch in patches:
        rel_path = file_patch.new_path or file_patch.old_path
        target_file = (root_dir / rel_path).resolve()

        if not target_file.exists():
            # Robust fallback: Search for file in root_dir if relative path prefix differs
            matched_candidate = None
            clean_rel = rel_path.lstrip("./")
            for cand in root_dir.rglob(Path(rel_path).name):
                if str(cand).endswith(clean_rel) or cand.name == Path(rel_path).name:
                    matched_candidate = cand
                    break
            if matched_candidate and matched_candidate.exists():
                target_file = matched_candidate
            else:
                return False, f"Target file does not exist: {rel_path}"

        try:
            content = target_file.read_text(encoding="utf-8")
            orig_lines = content.splitlines()
            success, new_lines, err = apply_patch_to_lines(orig_lines, file_patch.hunks)
            if not success:
                return False, f"Failed applying patch to {rel_path}: {err}"

            target_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as exc:
            return False, f"Error modifying {rel_path}: {exc}"

    return True, "Successfully applied diff."
