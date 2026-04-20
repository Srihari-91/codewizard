"""
TrivyScanner — scans requirements.txt / package.json for known CVEs.
Falls back gracefully if Trivy is not installed.
"""

import json
import os
import subprocess
import tempfile
import structlog

logger = structlog.get_logger(__name__)


class TrivyScanner:
    def scan_dependencies(self, repo_path: str = ".") -> list[dict]:
        """
        Scan for vulnerable dependencies. Returns list of vulnerability dicts.
        """
        if not self._trivy_available():
            logger.warning("trivy_not_available", msg="Skipping dependency scan")
            return []

        results = []
        for manifest in self._find_manifests(repo_path):
            findings = self._run_trivy(manifest)
            results.extend(findings)

        return results

    def _trivy_available(self) -> bool:
        try:
            subprocess.run(["trivy", "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _find_manifests(self, root: str) -> list[str]:
        targets = ["requirements.txt", "Pipfile", "pyproject.toml", "package.json"]
        found = []
        for t in targets:
            path = os.path.join(root, t)
            if os.path.exists(path):
                found.append(path)
        return found

    def _run_trivy(self, manifest_path: str) -> list[dict]:
        try:
            result = subprocess.run(
                ["trivy", "fs", "--format", "json", "--quiet", manifest_path],
                capture_output=True, text=True, timeout=60,
            )
            data = json.loads(result.stdout or "{}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.warning("trivy_scan_error", path=manifest_path, error=str(e))
            return []

        issues = []
        for target in data.get("Results", []):
            for vuln in target.get("Vulnerabilities", []) or []:
                severity = vuln.get("Severity", "UNKNOWN").upper()
                cw_severity = {
                    "CRITICAL": "CRITICAL", "HIGH": "HIGH",
                    "MEDIUM": "MEDIUM", "LOW": "LOW",
                }.get(severity, "MEDIUM")

                issues.append({
                    "file": manifest_path,
                    "severity": cw_severity,
                    "rule_id": f"trivy.{vuln.get('VulnerabilityID', 'CVE-UNKNOWN')}",
                    "description": (
                        f"{vuln.get('PkgName', '?')} {vuln.get('InstalledVersion', '?')} — "
                        f"{vuln.get('Title', vuln.get('VulnerabilityID', ''))}"
                    ),
                    "confidence": 95,
                    "fix_code": None,  # Trivy issues are informational only
                    "fix_available": bool(vuln.get("FixedVersion")),
                    "fixed_version": vuln.get("FixedVersion", ""),
                })

        return issues
