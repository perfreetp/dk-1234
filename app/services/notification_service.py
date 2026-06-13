from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models import (
    Subscription, Alert, AlertStatus, Metric,
    NotificationRecord, NotificationType, TriggerSource,
    AlertLifecycle, AlertLifecycleStage
)
import asyncio

settings = get_settings()


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_subscribers(self, metric_id: int) -> List[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(and_(
                Subscription.metric_id == metric_id,
                Subscription.is_active == True
            ))
        )
        return list(result.scalars().all())

    async def notify_alert(self, alert: Alert, trigger_source: TriggerSource = TriggerSource.API_DETECTION) -> List[dict]:
        subscribers = await self.get_subscribers(alert.metric_id)
        notifications = []

        for sub in subscribers:
            if not sub.notify_on_alert:
                continue

            if self._is_in_silent_hours(sub):
                continue

            try:
                notification = await self._send_notification(
                    email=sub.subscriber_email,
                    subject=f"[{alert.level.value.upper()}] 指标告警: {alert.metric.name if alert.metric else 'Unknown'}",
                    content=self._format_alert_message(alert),
                    notification_type="alert",
                )
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.ALERT,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="sent" if notification else "failed",
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "sent",
                    "sent_at": record.sent_at.isoformat(),
                    "type": "alert",
                    "trigger_source": trigger_source.value,
                })
            except Exception as e:
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.ALERT,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="failed",
                    error_message=str(e),
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "alert",
                    "trigger_source": trigger_source.value,
                })

        return notifications

    async def notify_recovery(self, alert: Alert, trigger_source: TriggerSource = TriggerSource.API_DETECTION) -> List[dict]:
        subscribers = await self.get_subscribers(alert.metric_id)
        notifications = []

        for sub in subscribers:
            if not sub.notify_on_recovery:
                continue

            if self._is_in_silent_hours(sub):
                continue

            try:
                notification = await self._send_notification(
                    email=sub.subscriber_email,
                    subject=f"[RECOVERED] 指标恢复: {alert.metric.name if alert.metric else 'Unknown'}",
                    content=self._format_recovery_message(alert),
                    notification_type="recovery",
                )
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.RECOVERY,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="sent" if notification else "failed",
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "sent",
                    "sent_at": record.sent_at.isoformat(),
                    "type": "recovery",
                    "trigger_source": trigger_source.value,
                })
            except Exception as e:
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.RECOVERY,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="failed",
                    error_message=str(e),
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "recovery",
                    "trigger_source": trigger_source.value,
                })

        return notifications

    async def notify_acknowledge(self, alert: Alert, trigger_source: TriggerSource = TriggerSource.MANUAL_ACTION) -> List[dict]:
        subscribers = await self.get_subscribers(alert.metric_id)
        notifications = []

        for sub in subscribers:
            if not sub.notify_on_acknowledge:
                continue

            try:
                notification = await self._send_notification(
                    email=sub.subscriber_email,
                    subject=f"[ACKNOWLEDGED] 告警已确认: {alert.metric.name if alert.metric else 'Unknown'}",
                    content=self._format_acknowledge_message(alert),
                    notification_type="acknowledge",
                )
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.ACKNOWLEDGE,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="sent" if notification else "failed",
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "sent",
                    "sent_at": record.sent_at.isoformat(),
                    "type": "acknowledge",
                    "trigger_source": trigger_source.value,
                })
            except Exception as e:
                record = await self._create_notification_record(
                    alert_id=alert.id,
                    metric_id=alert.metric_id,
                    notification_type=NotificationType.ACKNOWLEDGE,
                    trigger_source=trigger_source,
                    subscriber=sub.subscriber,
                    subscriber_email=sub.subscriber_email,
                    status="failed",
                    error_message=str(e),
                )
                notifications.append({
                    "notification_id": record.id,
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "acknowledge",
                    "trigger_source": trigger_source.value,
                })

        return notifications

    async def _create_notification_record(
        self,
        alert_id: int,
        metric_id: int,
        notification_type: NotificationType,
        trigger_source: TriggerSource,
        subscriber: str,
        subscriber_email: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> NotificationRecord:
        record = NotificationRecord(
            alert_id=alert_id,
            metric_id=metric_id,
            notification_type=notification_type,
            trigger_source=trigger_source,
            subscriber=subscriber,
            subscriber_email=subscriber_email,
            status=status,
            error_message=error_message,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_notification_records(
        self,
        alert_id: Optional[int] = None,
        metric_id: Optional[int] = None,
        notification_type: Optional[NotificationType] = None,
        trigger_source: Optional[TriggerSource] = None,
        limit: int = 100,
    ) -> List[NotificationRecord]:
        query = select(NotificationRecord)
        conditions = []
        if alert_id:
            conditions.append(NotificationRecord.alert_id == alert_id)
        if metric_id:
            conditions.append(NotificationRecord.metric_id == metric_id)
        if notification_type:
            conditions.append(NotificationRecord.notification_type == notification_type)
        if trigger_source:
            conditions.append(NotificationRecord.trigger_source == trigger_source)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(desc(NotificationRecord.sent_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class AlertLifecycleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_lifecycle_record(
        self,
        alert_id: int,
        metric_id: int,
        rule_id: int,
        stage: AlertLifecycleStage,
        trigger_source: TriggerSource,
        previous_status: Optional[str],
        new_status: str,
        silenced_duration_minutes: Optional[int] = None,
        current_value: Optional[float] = None,
        expected_value: Optional[float] = None,
        deviation: Optional[float] = None,
        note: Optional[str] = None,
    ) -> AlertLifecycle:
        record = AlertLifecycle(
            alert_id=alert_id,
            metric_id=metric_id,
            rule_id=rule_id,
            stage=stage,
            trigger_source=trigger_source,
            previous_status=previous_status,
            new_status=new_status,
            silenced_duration_minutes=silenced_duration_minutes,
            current_value=current_value,
            expected_value=expected_value,
            deviation=deviation,
            note=note,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_lifecycle_by_alert(self, alert_id: int) -> List[AlertLifecycle]:
        result = await self.session.execute(
            select(AlertLifecycle)
            .where(AlertLifecycle.alert_id == alert_id)
            .order_by(AlertLifecycle.created_at)
        )
        return list(result.scalars().all())

    async def get_lifecycle_by_metric(self, metric_id: int, limit: int = 100) -> List[AlertLifecycle]:
        result = await self.session.execute(
            select(AlertLifecycle)
            .where(AlertLifecycle.metric_id == metric_id)
            .order_by(desc(AlertLifecycle.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class SubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_subscription(self, subscription_data) -> Subscription:
        subscription = Subscription(
            metric_id=subscription_data.metric_id,
            subscriber=subscription_data.subscriber,
            subscriber_email=subscription_data.subscriber_email,
            notify_on_alert=subscription_data.notify_on_alert,
            notify_on_recovery=subscription_data.notify_on_recovery,
            notify_on_acknowledge=subscription_data.notify_on_acknowledge,
            silent_hours_start=subscription_data.silent_hours_start,
            silent_hours_end=subscription_data.silent_hours_end,
        )
        self.session.add(subscription)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def get_subscription_by_id(self, subscription_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_subscriptions_by_metric(self, metric_id: int) -> List[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.metric_id == metric_id)
        )
        return list(result.scalars().all())

    async def update_subscription(self, subscription_id: int, subscription_data) -> Optional[Subscription]:
        subscription = await self.get_subscription_by_id(subscription_id)
        if not subscription:
            return None

        update_data = subscription_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(subscription, field, value)

        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def delete_subscription(self, subscription_id: int) -> bool:
        subscription = await self.get_subscription_by_id(subscription_id)
        if not subscription:
            return False

        await self.session.delete(subscription)
        await self.session.commit()
        return True