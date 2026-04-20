"""
SemgrepRunner — runs Semgrep on the changed files and maps results
to CodeWizard severity levels.
"""

import json
import os
import re
import subprocess
import tempfile
import structlog
from config import settings

logger = structlog.get_logger(__name__)

SEVERITY_MAP = {
    "ERROR": "CRITICAL",
    "WARNING": "HIGH",
    "INFO": "MEDIUM",
}

# Ruleset to use — auto for broad coverage
SEMGREP_CONFIG = "auto"


class SemgrepRunner:
    def analyze(self, scored_files: list[dict]) -> list[dict]:
        """
        Write file content slices to temp files, run Semgrep, return issues.
        Returns list of issue dicts with severity, file, description, etc.
        """
        if not scored_files:
            return []

        issues = []
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write files to temp dir
            file_map = {}
            for pf in scored_files:
                path = pf["path"]
                content = pf.get("content_slice", "")
                if not content.strip():
                    continue
                # Preserve relative path structure
                dest = os.path.join(tmpdir, path.replace("/", "_"))
                with open(dest, "w") as f:
                    f.write(content)
                file_map[dest] = pf

            if not file_map:
                return []

            # Run semgrep
            cmd = [
                "semgrep",
                "--config", SEMGREP_CONFIG,
                "--json",
                "--timeout", "30",
                "--max-lines-per-finding", "10",
                tmpdir,
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout or "{}"
            except subprocess.TimeoutExpired:
                logger.warning("semgrep_timeout")
                return self._fallback_analysis(scored_files)
            except FileNotFoundError:
                logger.warning("semgrep_not_found", msg="falling back to pattern analysis")
                return self._fallback_analysis(scored_files)

            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                logger.warning("semgrep_parse_error", output=output[:200])
                return self._fallback_analysis(scored_files)

            for finding in data.get("results", []):
                sev_raw = finding.get("extra", {}).get("severity", "INFO")
                severity = SEVERITY_MAP.get(sev_raw.upper(), "MEDIUM")
                check_id = finding.get("check_id", "unknown")
                message = finding.get("extra", {}).get("message", "")
                file_dest = finding.get("path", "")

                # Map back to original path
                original_pf = file_map.get(file_dest, {})
                original_path = original_pf.get("path", file_dest)

                issues.append({
                    "file": original_path,
                    "severity": severity,
                    "rule_id": check_id,
                    "description": message,
                    "confidence": self._confidence_from_severity(severity),
                    "content_slice": original_pf.get("content_slice", ""),
                    "patch": original_pf.get("patch", ""),
                    "risk_score": original_pf.get("risk_score", 0),
                })

        # Sort by severity priority
        priority = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        issues.sort(key=lambda x: (priority.get(x["severity"], 4), -x.get("risk_score", 0)))
        return issues

    def _confidence_from_severity(self, severity: str) -> int:
        return {"CRITICAL": 90, "HIGH": 82, "MEDIUM": 75, "LOW": 65}.get(severity, 70)

    def _fallback_analysis(self, scored_files: list[dict]) -> list[dict]:
        """
        Basic regex pattern matching when Semgrep is unavailable.
        """
        issues = []
        patterns = [
            (r"cursor\.execute\s*\(\s*['\"].*%s", "CRITICAL",
             "python.lang.security.audit.formatted-sql-query",
             "Potential SQL injection via string formatting"),
            (r"eval\s*\(", "CRITICAL",
             "python.lang.security.audit.eval-detected",
             "Use of eval() is dangerous and can lead to RCE"),
            (r"subprocess\.call\s*\(\s*['\"]", "HIGH",
             "python.lang.security.audit.subprocess-shell-true",
             "subprocess call with string argument — prefer list form"),
            (r"os\.system\s*\(", "HIGH",
             "python.lang.security.audit.os-system",
             "os.system() is a shell injection risk"),
            (r"password\s*=\s*['\"][^'\"]{4,}['\"]", "CRITICAL",
             "python.lang.security.hardcoded-password",
             "Hardcoded password or secret detected"),
            (r"pickle\.loads\s*\(", "HIGH",
             "python.lang.security.audit.pickle",
             "pickle.loads is unsafe on untrusted data"),
            (r"yaml\.load\s*\([^,)]+\)", "HIGH",
             "python.lang.security.audit.yaml-load",
             "yaml.load without Loader is unsafe — use yaml.safe_load"),
            (r"except\s*:\s*$|except\s+Exception\s*:\s*$", "MEDIUM",
             "python.lang.best-practice.bare-except",
             "Bare except clause swallows all errors"),
            (r"TODO|FIXME|HACK|XXX", "LOW",
             "python.lang.maintainability.todo",
             "Unresolved TODO/FIXME comment"),
        ]

        for pf in scored_files:
            content = pf.get("content_slice", "")
            for pattern, severity, rule_id, description in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append({
                        "file": pf["path"],
                        "severity": severity,
                        "rule_id": rule_id,
                        "description": description,
                        "confidence": self._confidence_from_severity(severity),
                        "content_slice": content,
                        "patch": pf.get("patch", ""),
                        "risk_score": pf.get("risk_score", 0),
                    })
                    break  # one issue per file in fallback mode

        return issues
