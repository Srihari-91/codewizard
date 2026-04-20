"""
CodeWizard AI — Unit Tests
Run with: pytest tests/ -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── DiffParser tests ──────────────────────────────────────────────────────────
class TestDiffParser:
    def setup_method(self):
        from analyzer.diff_parser import DiffParser
        self.parser = DiffParser()

    def test_parse_basic_diff(self):
        gh_file = {
            "filename": "app/auth.py",
            "status": "modified",
            "additions": 5,
            "deletions": 2,
            "patch": "@@ -10,4 +10,5 @@\n def login():\n+    password = 'secret123'\n+    cursor.execute('SELECT * FROM users WHERE id=%s' % user_id)\n     return True\n-    pass",
        }
        result = self.parser.parse(gh_file)
        assert result["path"] == "app/auth.py"
        assert len(result["added_lines"]) == 2
        assert "password" in result["content_slice"]

    def test_extract_functions(self):
        content = "def foo():\n    pass\ndef bar(x, y):\n    return x"
        fns = self.parser.extract_functions(content)
        assert "foo" in fns
        assert "bar" in fns

    def test_extract_imports(self):
        content = "import os\nfrom fastapi import FastAPI\nimport json"
        imports = self.parser.extract_imports(content)
        assert "os" in imports
        assert "fastapi" in imports
        assert "json" in imports

    def test_empty_patch(self):
        gh_file = {"filename": "readme.py", "status": "added", "additions": 0, "deletions": 0, "patch": ""}
        result = self.parser.parse(gh_file)
        assert result["content_slice"] == ""
        assert result["added_lines"] == []


# ── RiskScorer tests ──────────────────────────────────────────────────────────
class TestRiskScorer:
    def setup_method(self):
        from analyzer.scoring.risk_scorer import RiskScorer
        self.scorer = RiskScorer()

    def test_scores_sql_injection_high(self):
        pf = {
            "path": "db/queries.py",
            "content_slice": "cursor.execute('SELECT * FROM users WHERE id=%s' % user_id)",
            "patch": "",
            "additions": 10,
            "deletions": 0,
        }
        results = self.scorer.score([pf], {})
        assert results[0]["risk_score"] > 5.0

    def test_scores_auth_file_higher(self):
        pf_auth = {
            "path": "auth/login.py",
            "content_slice": "def login(): pass",
            "patch": "", "additions": 5, "deletions": 0,
        }
        pf_util = {
            "path": "utils/helpers.py",
            "content_slice": "def helper(): pass",
            "patch": "", "additions": 5, "deletions": 0,
        }
        results = self.scorer.score([pf_util, pf_auth], {})
        auth_score = next(r["risk_score"] for r in results if "auth" in r["path"])
        util_score = next(r["risk_score"] for r in results if "utils" in r["path"])
        assert auth_score > util_score

    def test_graph_impact_adds_to_score(self):
        pf = {
            "path": "core.py",
            "content_slice": "def core(): pass",
            "patch": "", "additions": 5, "deletions": 0,
        }
        results_no_graph = self.scorer.score([pf], {})
        results_with_graph = self.scorer.score([pf], {"core.py": 50.0})
        assert results_with_graph[0]["risk_score"] > results_no_graph[0]["risk_score"]

    def test_sorted_by_risk(self):
        files = [
            {"path": "utils.py", "content_slice": "pass", "patch": "", "additions": 1, "deletions": 0},
            {"path": "auth/password.py", "content_slice": "eval(user_input)", "patch": "", "additions": 100, "deletions": 50},
        ]
        results = self.scorer.score(files, {})
        assert "auth" in results[0]["path"]


# ── SemgrepRunner fallback tests ──────────────────────────────────────────────
class TestSemgrepFallback:
    def setup_method(self):
        from analyzer.static.semgrep_runner import SemgrepRunner
        self.runner = SemgrepRunner()

    def test_detects_sql_injection(self):
        files = [{
            "path": "db.py",
            "content_slice": 'cursor.execute("SELECT * FROM users WHERE id=%s" % uid)',
            "patch": "", "risk_score": 8.0,
        }]
        issues = self.runner._fallback_analysis(files)
        assert any("sql" in i["rule_id"].lower() for i in issues)
        assert any(i["severity"] == "CRITICAL" for i in issues)

    def test_detects_eval(self):
        files = [{"path": "runner.py", "content_slice": "eval(user_code)", "patch": "", "risk_score": 5.0}]
        issues = self.runner._fallback_analysis(files)
        assert any("eval" in i["rule_id"] for i in issues)

    def test_detects_hardcoded_password(self):
        files = [{"path": "config.py", "content_slice": "password = 'SuperSecret123'", "patch": "", "risk_score": 3.0}]
        issues = self.runner._fallback_analysis(files)
        assert any("password" in i["rule_id"] for i in issues)

    def test_no_false_positives_on_clean_code(self):
        files = [{"path": "utils.py", "content_slice": "def add(a, b): return a + b", "patch": "", "risk_score": 1.0}]
        issues = self.runner._fallback_analysis(files)
        assert len(issues) == 0


# ── CommentBuilder tests ──────────────────────────────────────────────────────
class TestCommentBuilder:
    def setup_method(self):
        from worker.utils.comment_builder import CommentBuilder
        self.builder = CommentBuilder()

    def test_builds_comment_header(self):
        comment = self.builder.build([], applied_fixes=[], files_analyzed=3, files_total=10)
        assert "CodeWizard AI Review" in comment
        assert "3" in comment

    def test_includes_issue_severity(self):
        issues = [{
            "file": "auth.py",
            "severity": "CRITICAL",
            "rule_id": "sql-injection",
            "description": "SQL injection risk",
            "confidence": 90,
            "fix_code": "- cursor.execute(q % id)\n+ cursor.execute(q, (id,))",
        }]
        comment = self.builder.build(issues, applied_fixes=[], files_analyzed=1, files_total=1)
        assert "CRITICAL" in comment
        assert "auth.py" in comment
        assert "SQL injection" in comment

    def test_low_confidence_no_fix(self):
        issues = [{
            "file": "utils.py",
            "severity": "MEDIUM",
            "rule_id": "bare-except",
            "description": "Bare except",
            "confidence": 60,
            "fix_code": "some code",
        }]
        comment = self.builder.build(issues, applied_fixes=[], files_analyzed=1, files_total=1)
        assert "Confidence below threshold" in comment

    def test_sandbox_failed_message(self):
        issues = [{
            "file": "app.py",
            "severity": "HIGH",
            "rule_id": "eval",
            "description": "eval usage",
            "confidence": 80,
            "fix_code": "fixed",
            "sandbox_failed": True,
        }]
        comment = self.builder.build(issues, applied_fixes=[], files_analyzed=1, files_total=1)
        assert "sandbox failed" in comment.lower()


# ── File filter tests (inline, no Docker deps needed) ─────────────────────────
# Replicated here to avoid importing neo4j/redis in a unit-test context.
import os as _os

_IGNORE_PATHS = {
    "node_modules/", "dist/", "build/", "out/", "coverage/",
    ".mypy_cache/", ".pytest_cache/", "__pycache__/", ".next/",
    ".nuxt/", "target/", "venv/", ".env/", ".idea/", ".vscode/",
    ".git/", ".github/", "migrations/", "logs/", "tmp/", "temp/", ".cache/"
}
_IGNORE_EXTENSIONS = {
    ".lock", ".min.js", ".min.css", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar",
    ".gz", ".rar", ".map", ".bundle.js", ".csv", ".jsonl",
}
_ALLOWED_EXTENSIONS = {".py"}


def _filter_files_local(pr_files):
    result = []
    for f in pr_files:
        path = f.get("filename", "")
        ext = _os.path.splitext(path)[1].lower()
        if any(path.startswith(p) or f"/{p}" in path for p in _IGNORE_PATHS):
            continue
        if ext in _IGNORE_EXTENSIONS:
            continue
        if ext not in _ALLOWED_EXTENSIONS:
            continue
        result.append(f)
    return result


class TestFileFilter:
    def _filter(self, files):
        return _filter_files_local(files)

    def test_allows_python_files(self):
        files = [{"filename": "app/main.py", "patch": ""}]
        assert len(self._filter(files)) == 1

    def test_rejects_js_files(self):
        files = [{"filename": "src/app.js", "patch": ""}]
        assert len(self._filter(files)) == 0

    def test_rejects_node_modules(self):
        files = [{"filename": "node_modules/lodash/index.py", "patch": ""}]
        assert len(self._filter(files)) == 0

    def test_rejects_lock_files(self):
        files = [{"filename": "requirements.lock", "patch": ""}]
        assert len(self._filter(files)) == 0

    def test_rejects_binaries(self):
        for ext in [".png", ".zip", ".pdf"]:
            files = [{"filename": f"assets/file{ext}", "patch": ""}]
            assert len(self._filter(files)) == 0

    def test_rejects_venv(self):
        files = [{"filename": "venv/lib/site.py", "patch": ""}]
        assert len(self._filter(files)) == 0
