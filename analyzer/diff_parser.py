"""
DiffParser — extracts changed lines and code slices from GitHub PR file patches.
"""

import re


class DiffParser:
    def parse(self, gh_file: dict) -> dict:
        """
        Parse a GitHub PR file object into a structured representation.
        Returns dict with path, added_lines, removed_lines, content_slice.
        """
        path = gh_file.get("filename", "")
        patch = gh_file.get("patch", "") or ""
        status = gh_file.get("status", "modified")

        added_lines = []
        removed_lines = []
        current_line = 0

        for raw_line in patch.splitlines():
            # Parse hunk headers: @@ -a,b +c,d @@
            hunk = re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", raw_line)
            if hunk:
                current_line = int(hunk.group(1))
                continue

            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                added_lines.append((current_line, raw_line[1:]))
                current_line += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                removed_lines.append(raw_line[1:])
                # Removed lines don't advance new-file line counter
            else:
                current_line += 1

        # Build a slice of just the new code (added lines only, up to limit)
        content_slice = "\n".join(line for _, line in added_lines[:200])

        return {
            "path": path,
            "status": status,
            "patch": patch,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "content_slice": content_slice,
            "additions": gh_file.get("additions", 0),
            "deletions": gh_file.get("deletions", 0),
        }

    def extract_functions(self, content: str) -> list[str]:
        """Simple regex-based function name extractor for Python."""
        return re.findall(r"^def\s+(\w+)\s*\(", content, re.MULTILINE)

    def extract_imports(self, content: str) -> list[str]:
        """Extract imported module names from Python source."""
        imports = []
        for match in re.finditer(r"^(?:import|from)\s+([\w.]+)", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[0])
        return list(set(imports))

    def extract_calls(self, content: str) -> list[str]:
        """Extract function call names (simple heuristic)."""
        return re.findall(r"\b(\w+)\s*\(", content)
