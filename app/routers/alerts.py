from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import AlertStatus, AlertLevel, TriggerSource, AlertLifecycleStage
from app.schemas import (
    AlertResponse,
    AlertAcknowledge,
    AlertResolve,
    AlertListResponse,
    AlertSummary,
    ReviewCreate,
    ReviewResponse,
)
from app.services import AlertService, ReviewService, NotificationService, AlertLifecycleService

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


@router.get("/{alert_id}/silence-status")
async def get_silence_status(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    if alert.status != AlertStatus.SILENCED:
        return {
            "alert_id": alert_id,
            "is_silenced": False,
            "status": alert.status.value,
        }

    remaining_seconds = 0
    if alert.silenced_until:
        remaining = alert.silenced_until - datetime.utcnow()
        remaining_seconds = max(0, int(remaining.total_seconds()))

    return {
        "alert_id": alert_id,
        "is_silenced": True,
        "status": alert.status.value,
        "silenced_at": alert.silenced_at.isoformat() if alert.silenced_at else None,
        "silenced_until": alert.silenced_until.isoformat() if alert.silenced_until else None,
        "silenced_duration_minutes": alert.silenced_duration_minutes,
        "remaining_minutes": remaining_seconds // 60,
        "remaining_seconds": remaining_seconds,
    }


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
    await notification_service.notify_acknowledge(alert, TriggerSource.MANUAL_ACTION)

    lifecycle_service = AlertLifecycleService(session)
    await lifecycle_service.create_lifecycle_record(
        alert_id=alert_id,
        metric_id=alert.metric_id,
        rule_id=alert.rule_id,
        stage=AlertLifecycleStage.ACKNOWLEDGED,
        trigger_source=TriggerSource.MANUAL_ACTION,
        previous_status=AlertStatus.ACTIVE.value,
        new_status=AlertStatus.ACKNOWLEDGED.value,
    )

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
    await notification_service.notify_recovery(alert, TriggerSource.MANUAL_ACTION)

    lifecycle_service = AlertLifecycleService(session)
    await lifecycle_service.create_lifecycle_record(
        alert_id=alert_id,
        metric_id=alert.metric_id,
        rule_id=alert.rule_id,
        stage=AlertLifecycleStage.RECOVERED,
        trigger_source=TriggerSource.MANUAL_ACTION,
        previous_status=AlertStatus.ACKNOWLEDGED.value if alert.acknowledged_by else AlertStatus.ACTIVE.value,
        new_status=AlertStatus.RESOLVED.value,
    )

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

    lifecycle_service = AlertLifecycleService(session)
    await lifecycle_service.create_lifecycle_record(
        alert_id=alert_id,
        metric_id=alert.metric_id,
        rule_id=alert.rule_id,
        stage=AlertLifecycleStage.SILENCED,
        trigger_source=TriggerSource.MANUAL_ACTION,
        previous_status=AlertStatus.ACTIVE.value,
        new_status=AlertStatus.SILENCED.value,
        silenced_duration_minutes=duration_minutes,
        note=f"静默{duration_minutes}分钟",
    )

    return alert


@router.post("/{alert_id}/cancel-silence", response_model=AlertResponse)
async def cancel_silence(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.cancel_silence(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    lifecycle_service = AlertLifecycleService(session)
    await lifecycle_service.create_lifecycle_record(
        alert_id=alert_id,
        metric_id=alert.metric_id,
        rule_id=alert.rule_id,
        stage=AlertLifecycleStage.RESUMED_FROM_SILENCE,
        trigger_source=TriggerSource.MANUAL_ACTION,
        previous_status=AlertStatus.SILENCED.value,
        new_status=AlertStatus.ACTIVE.value,
        note="取消静默，立即恢复检测",
    )

    return alert


@router.post("/{alert_id}/extend-silence", response_model=AlertResponse)
async def extend_silence(
    alert_id: int,
    additional_minutes: int = Query(..., description="追加静默时长（分钟）"),
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.extend_silence(alert_id, additional_minutes)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    lifecycle_service = AlertLifecycleService(session)
    await lifecycle_service.create_lifecycle_record(
        alert_id=alert_id,
        metric_id=alert.metric_id,
        rule_id=alert.rule_id,
        stage=AlertLifecycleStage.SILENCED,
        trigger_source=TriggerSource.MANUAL_ACTION,
        previous_status=AlertStatus.SILENCED.value,
        new_status=AlertStatus.SILENCED.value,
        silenced_duration_minutes=additional_minutes,
        note=f"延长静默{additional_minutes}分钟",
    )

    return alert


@router.get("/{alert_id}/lifecycle")
async def get_alert_lifecycle(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = AlertService(session)
    alert = await service.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    lifecycle_service = AlertLifecycleService(session)
    lifecycle_records = await lifecycle_service.get_lifecycle_by_alert(alert_id)

    return {
        "alert_id": alert_id,
        "current_status": alert.status.value,
        "lifecycle": [{
            "id": r.id,
            "stage": r.stage.value,
            "trigger_source": r.trigger_source.value,
            "previous_status": r.previous_status,
            "new_status": r.new_status,
            "silenced_duration_minutes": r.silenced_duration_minutes,
            "current_value": r.current_value,
            "expected_value": r.expected_value,
            "deviation": r.deviation,
            "note": r.note,
            "created_at": r.created_at.isoformat(),
        } for r in lifecycle_records],
    }


@router.get("/{alert_id}/reviews", response_model=List[ReviewResponse])
async def get_alert_reviews(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = ReviewService(session)
    reviews = await service.get_reviews_by_alert(alert_id)
    return reviews


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