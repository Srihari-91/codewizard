"""
Pull Request API endpoints — query PR analysis results.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db, PRRecord, IssueRecord

router = APIRouter()


@router.get("/")
async def list_prs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PRRecord).order_by(desc(PRRecord.created_at)).limit(limit).offset(offset)
    )
    records = result.scalars().all()
    return {"prs": [_pr_to_dict(r) for r in records], "total": len(records)}


@router.get("/{pr_id}")
async def get_pr(pr_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PRRecord).where(PRRecord.id == pr_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="PR not found")

    issues_result = await db.execute(
        select(IssueRecord).where(IssueRecord.pr_record_id == pr_id)
    )
    issues = issues_result.scalars().all()

    return {
        **_pr_to_dict(record),
        "issues": [_issue_to_dict(i) for i in issues],
    }


def _pr_to_dict(r: PRRecord) -> dict:
    return {
        "id": r.id,
        "repo": r.repo_full_name,
        "pr_number": r.pr_number,
        "title": r.pr_title,
        "status": r.status,
        "issues_found": r.issues_found,
        "fixes_applied": r.fixes_applied,
        "created_at": str(r.created_at),
    }


def _issue_to_dict(i: IssueRecord) -> dict:
    return {
        "id": i.id,
        "file": i.file_path,
        "severity": i.severity,
        "type": i.issue_type,
        "description": i.description,
        "confidence": i.confidence,
        "fix_applied": i.fix_applied,
    }
