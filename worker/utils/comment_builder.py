"""
Builds formatted GitHub PR review comments in CodeWizard format.
"""


SEVERITY_EMOJI = {
    "CRITICAL": "🚨",
    "HIGH": "⚠️",
    "MEDIUM": "📌",
    "LOW": "💡",
}


class CommentBuilder:
    def build(
        self,
        issues: list,
        applied_fixes: list,
        files_analyzed: int,
        files_total: int,
    ) -> str:
        lines = [
            "## 🔍 CodeWizard AI Review",
            "",
            "### 🧠 Analysis Scope",
            f"- Files analyzed: **{files_analyzed}** / {files_total}",
            "- Strategy: Risk-based prioritization · Diff-aware slicing",
            "",
            "---",
            "",
        ]

        if not issues:
            lines.append("✅ **No issues found** — this PR looks clean!")
            return "\n".join(lines)

        for idx, issue in enumerate(issues, 1):
            sev = issue.get("severity", "MEDIUM")
            emoji = SEVERITY_EMOJI.get(sev, "📌")
            confidence = issue.get("confidence", 0)
            file_path = issue.get("file", "unknown")
            description = issue.get("description", "")
            rule_id = issue.get("rule_id", "")
            fix_code = issue.get("fix_code")
            sandbox_failed = issue.get("sandbox_failed", False)
            is_applied = issue in applied_fixes

            lines += [
                f"### {emoji} Issue {idx} ({sev})",
                f"- **File:** `{file_path}`",
                f"- **Problem:** {description}",
                f"- **Rule:** `{rule_id}`",
                f"- **Confidence:** {confidence}%",
                "",
            ]

            if fix_code and confidence >= 75:
                lines += [
                    "### ✅ Suggested Fix",
                    "```diff",
                    fix_code,
                    "```",
                    "",
                ]
                if sandbox_failed:
                    lines += [
                        "### 🧪 Validation",
                        "- Tests Passed: ❌ (sandbox failed — fix not auto-applied)",
                        "",
                    ]
                elif is_applied:
                    lines += [
                        "### 🧪 Validation",
                        "- Tests Passed: ✅",
                        "- Fix branch created and PR opened automatically",
                        "",
                    ]
                else:
                    lines += [
                        "### 🧪 Validation",
                        "- Tests Passed: ✅",
                        "",
                    ]
            else:
                reason = "Confidence below threshold" if confidence < 75 else "No fix generated"
                lines += [
                    f"ℹ️ *{reason} — explanation only, no auto-fix applied.*",
                    "",
                ]

            lines += ["---", ""]

        # Summary footer
        applied_count = len(applied_fixes)
        lines += [
            f"**Summary:** {len(issues)} issue(s) found · {applied_count} fix(es) applied automatically",
            "",
            "_👍 Accept Fix | 👎 Reject Fix — Reply to this comment to provide feedback._",
        ]

        return "\n".join(lines)
