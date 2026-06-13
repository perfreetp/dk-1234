from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import AlertStatus, AlertLevel
from app.schemas import (
    AlertResponse,
    AlertAcknowledge,
    AlertResolve,
    AlertListResponse,
    AlertSummary,
    ReviewCreate,
    ReviewResponse,
)
from app.services import AlertService, ReviewService, NotificationService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    metric_id: Optional[int] = Query(None, description="指标ID筛选"),
    status: Optional[AlertStatus] = Query(None, description="状态筛选"),
    level: Optional[AlertLevel] = Query(None, description="级别筛选"),
    business_line: Optional[str] = Query(None, description="业务线筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alerts, total = await service.get_alerts(
        metric_id=metric_id,
        status=status,
        level=level,
        business_line=business_line,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    return AlertListResponse(
        alerts=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        page=skip // limit + 1,
        page_size=limit,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert


@router.get("/{alert_id}/summary", response_model=AlertSummary)
async def get_alert_summary(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    summary = await service.get_alert_summary(alert_id)
    if not summary:
        raise HTTPException(status_code=404, detail="告警不存在")
    return AlertSummary(**summary)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    data: AlertAcknowledge,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.acknowledge_alert(alert_id, data)
    if not alert:
        raise HTTPException(status_code=400, detail="无法确认告警")
    
    notification_service = NotificationService(session)
    await notification_service.notify_acknowledge(alert)
    
    return alert


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    data: AlertResolve,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.resolve_alert(alert_id, data)
    if not alert:
        raise HTTPException(status_code=400, detail="无法解决告警")
    
    notification_service = NotificationService(session)
    await notification_service.notify_recovery(alert)
    
    return alert


@router.post("/{alert_id}/silence", response_model=AlertResponse)
async def silence_alert(
    alert_id: int,
    duration_minutes: int = Query(60, description="静默时长（分钟）"),
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.silence_alert(alert_id, duration_minutes)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert


@router.post("/{alert_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    alert_id: int,
    review_data: ReviewCreate,
    session: AsyncSession = Depends(get_session),
):
    alert_service = AlertService(session)
    alert = await alert_service.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    review_service = ReviewService(session)
    review = await review_service.create_review(
        alert_id=alert_id,
        reviewer=review_data.reviewer,
        root_cause=review_data.root_cause,
        impact_analysis=review_data.impact_analysis,
        action_taken=review_data.action_taken,
        lessons_learned=review_data.lessons_learned,
    )
    return review


@router.get("/{alert_id}/reviews", response_model=List[ReviewResponse])
async def get_alert_reviews(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = ReviewService(session)
    reviews = await service.get_reviews_by_alert(alert_id)
    return reviews