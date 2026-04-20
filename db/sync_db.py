"""
Synchronous SQLite helper for use inside RQ jobs (non-async context).
"""

import os
import sqlite3
import structlog

logger = structlog.get_logger(__name__)

DB_PATH = os.getenv("SQLITE_DB_PATH", "/data/codewizard.db")


class SyncDB:
    def _conn(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)

    def update_pr_status(
        self,
        record_id: int,
        status: str,
        issues_found: int = 0,
        fixes_applied: int = 0,
    ):
        with self._conn() as conn:
            conn.execute(
                """UPDATE pr_records
                   SET status=?, issues_found=?, fixes_applied=?, updated_at=datetime('now')
                   WHERE id=?""",
                (status, issues_found, fixes_applied, record_id),
            )

    def insert_issue(
        self,
        pr_record_id: int,
        file_path: str,
        severity: str,
        issue_type: str,
        description: str,
        confidence: float,
        fix_applied: bool,
    ):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO issue_records
                   (pr_record_id, file_path, severity, issue_type, description, confidence, fix_applied)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pr_record_id, file_path, severity, issue_type, description, confidence, int(fix_applied)),
            )
