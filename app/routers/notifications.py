from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import NotificationType, TriggerSource
from app.services import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    alert_id: Optional[int] = Query(None, description="告警ID筛选"),
    metric_id: Optional[int] = Query(None, description="指标ID筛选"),
    notification_type: Optional[NotificationType] = Query(None, description="通知类型筛选"),
    trigger_source: Optional[TriggerSource] = Query(None, description="触发来源筛选"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    service = NotificationService(session)
    records = await service.get_notification_records(
        alert_id=alert_id,
        metric_id=metric_id,
        notification_type=notification_type,
        trigger_source=trigger_source,
        limit=limit,
    )
    return {
        "notifications": [{
            "id": r.id,
            "alert_id": r.alert_id,
            "metric_id": r.metric_id,
            "type": r.notification_type.value,
            "trigger_source": r.trigger_source.value,
            "subscriber": r.subscriber,
            "subscriber_email": r.subscriber_email,
            "status": r.status,
            "sent_at": r.sent_at.isoformat(),
            "error_message": r.error_message,
        } for r in records],
        "total": len(records),
    }


@router.get("/metric/{metric_id}")
async def get_metric_notifications(
    metric_id: int,
    notification_type: Optional[NotificationType] = Query(None, description="通知类型筛选"),
    trigger_source: Optional[TriggerSource] = Query(None, description="触发来源筛选"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    service = NotificationService(session)
    records = await service.get_notification_records(
        metric_id=metric_id,
        notification_type=notification_type,
        trigger_source=trigger_source,
        limit=limit,
    )
    return {
        "metric_id": metric_id,
        "notifications": [{
            "id": r.id,
            "alert_id": r.alert_id,
            "type": r.notification_type.value,
            "trigger_source": r.trigger_source.value,
            "subscriber": r.subscriber,
            "subscriber_email": r.subscriber_email,
            "status": r.status,
            "sent_at": r.sent_at.isoformat(),
        } for r in records],
        "total": len(records),
    }


@router.get("/alert/{alert_id}")
async def get_alert_notifications(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = NotificationService(session)
    records = await service.get_notification_records(alert_id=alert_id)
    return {
        "alert_id": alert_id,
        "notifications": [{
            "id": r.id,
            "type": r.notification_type.value,
            "trigger_source": r.trigger_source.value,
            "subscriber": r.subscriber,
            "subscriber_email": r.subscriber_email,
            "status": r.status,
            "sent_at": r.sent_at.isoformat(),
            "error_message": r.error_message,
        } for r in records],
        "total": len(records),
    }