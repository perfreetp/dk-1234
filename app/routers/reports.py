from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas import WeeklyReportResponse, WeeklyReportGenerate
from app.services import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/weekly", response_model=WeeklyReportResponse, status_code=201)
async def generate_weekly_report(
    data: WeeklyReportGenerate,
    session: AsyncSession = Depends(get_session),
):
    service = ReportService(session)
    report = await service.generate_weekly_report(
        business_line=data.business_line,
        week_start=data.week_start,
        week_end=data.week_end,
    )
    return report


@router.get("/weekly/{report_id}", response_model=WeeklyReportResponse)
async def get_weekly_report(
    report_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = ReportService(session)
    report = await service.get_weekly_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="周报不存在")
    return report


@router.get("/weekly/business-line/{business_line}", response_model=List[WeeklyReportResponse])
async def get_weekly_reports_by_business_line(
    business_line: str,
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    service = ReportService(session)
    reports = await service.get_weekly_reports_by_business_line(business_line, limit)
    return reports


@router.get("/stats/{business_line}")
async def get_business_line_stats(
    business_line: str,
    session: AsyncSession = Depends(get_session),
):
    service = ReportService(session)
    stats = await service.get_business_line_stats(business_line)
    return stats