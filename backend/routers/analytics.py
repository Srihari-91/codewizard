"""
Analytics API — dashboard stats.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db, PRRecord, IssueRecord

router = APIRouter()


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    total_prs = (await db.execute(select(func.count(PRRecord.id)))).scalar()
    completed = (await db.execute(
        select(func.count(PRRecord.id)).where(PRRecord.status == "completed")
    )).scalar()
    total_issues = (await db.execute(select(func.count(IssueRecord.id)))).scalar()
    total_fixes = (await db.execute(
        select(func.count(IssueRecord.id)).where(IssueRecord.fix_applied == True)
    )).scalar()

    by_severity = {}
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = (await db.execute(
            select(func.count(IssueRecord.id)).where(IssueRecord.severity == sev)
        )).scalar()
        by_severity[sev] = count

    return {
        "total_prs_analyzed": total_prs,
        "completed": completed,
        "total_issues_found": total_issues,
        "total_fixes_applied": total_fixes,
        "by_severity": by_severity,
    }


@router.get("/recent")
async def recent_activity(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import desc
    result = await db.execute(
        select(PRRecord).order_by(desc(PRRecord.created_at)).limit(10)
    )
    records = result.scalars().all()
    return {"recent": [
        {
            "repo": r.repo_full_name,
            "pr_number": r.pr_number,
            "title": r.pr_title,
            "status": r.status,
            "issues_found": r.issues_found,
            "fixes_applied": r.fixes_applied,
            "created_at": str(r.created_at),
        }
        for r in records
    ]}
