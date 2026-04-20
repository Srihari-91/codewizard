"""
RiskScorer — computes a composite risk score per changed file.

Risk Score = change_size + critical_path + security_sensitivity + graph_impact
"""

import re
import structlog

logger = structlog.get_logger(__name__)

# Patterns that indicate high security sensitivity
SECURITY_PATTERNS = [
    (r"password|passwd|secret|api_key|token|auth|oauth|jwt", 3.0),
    (r"sql|execute|cursor\.execute|raw\(|format_map", 4.0),
    (r"subprocess|os\.system|eval\(|exec\(|__import__", 4.0),
    (r"pickle\.loads|yaml\.load\b|marshal\.loads", 3.5),
    (r"open\(|file\(|read\(|write\(|shutil", 2.0),
    (r"request\.|flask|fastapi|django|aiohttp", 2.5),
    (r"hashlib|hmac|ssl|tls|cert", 2.0),
]

# Critical paths that suggest high-impact code
CRITICAL_PATH_PATTERNS = [
    r"auth", r"login", r"payment", r"billing", r"admin",
    r"security", r"crypto", r"token", r"session", r"user",
    r"database", r"db", r"migration", r"model",
]


class RiskScorer:
    def score(self, parsed_files: list[dict], graph_scores: dict) -> list[dict]:
        """
        Score and rank files. Returns sorted list (highest risk first).
        Adds 'risk_score' key to each parsed file dict.
        """
        results = []
        for pf in parsed_files:
            score = self._compute(pf, graph_scores.get(pf["path"], 0.0))
            results.append({**pf, "risk_score": score})

        results.sort(key=lambda x: x["risk_score"], reverse=True)
        return results

    def _compute(self, pf: dict, graph_impact: float) -> float:
        path = pf["path"]
        content = pf.get("content_slice", "") + pf.get("patch", "")
        additions = pf.get("additions", 0)
        deletions = pf.get("deletions", 0)

        # 1. Change size score (0–5)
        total_changes = additions + deletions
        if total_changes < 10:
            change_size = 1.0
        elif total_changes < 50:
            change_size = 2.0
        elif total_changes < 200:
            change_size = 3.5
        else:
            change_size = 5.0

        # 2. Critical path score (0–4)
        critical_path = 0.0
        path_lower = path.lower()
        for pattern in CRITICAL_PATH_PATTERNS:
            if re.search(pattern, path_lower):
                critical_path = 4.0
                break

        # 3. Security sensitivity score (0–10)
        security = 0.0
        content_lower = content.lower()
        for pattern, weight in SECURITY_PATTERNS:
            if re.search(pattern, content_lower):
                security += weight
        security = min(security, 10.0)

        # 4. Graph impact (already computed, normalize 0–5)
        graph = min(graph_impact / 10.0, 5.0)

        total = change_size + critical_path + security + graph
        logger.debug(
            "file_scored",
            path=path,
            change_size=change_size,
            critical_path=critical_path,
            security=security,
            graph=graph,
            total=total,
        )
        return round(total, 2)
