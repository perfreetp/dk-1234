from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models import Subscription, Alert, AlertStatus, Metric, NotificationRecord, NotificationType
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

    async def notify_alert(self, alert: Alert) -> List[dict]:
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
                })
            except Exception as e:
                notifications.append({
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "alert",
                })

        return notifications

    async def notify_recovery(self, alert: Alert) -> List[dict]:
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
                })
            except Exception as e:
                notifications.append({
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "recovery",
                })

        return notifications

    async def notify_acknowledge(self, alert: Alert) -> List[dict]:
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
                })
            except Exception as e:
                notifications.append({
                    "subscriber": sub.subscriber,
                    "email": sub.subscriber_email,
                    "status": "failed",
                    "error": str(e),
                    "type": "acknowledge",
                })

        return notifications

    async def _create_notification_record(
        self,
        alert_id: int,
        metric_id: int,
        notification_type: NotificationType,
        subscriber: str,
        subscriber_email: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> NotificationRecord:
        record = NotificationRecord(
            alert_id=alert_id,
            metric_id=metric_id,
            notification_type=notification_type,
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
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(desc(NotificationRecord.sent_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _is_in_silent_hours(self, subscription: Subscription) -> bool:
        if subscription.silent_hours_start is None or subscription.silent_hours_end is None:
            return False

        current_hour = datetime.utcnow().hour
        start = subscription.silent_hours_start
        end = subscription.silent_hours_end

        if start <= end:
            return start <= current_hour < end
        else:
            return current_hour >= start or current_hour < end

    async def _send_notification(
        self,
        email: str,
        subject: str,
        content: str,
        notification_type: str,
    ) -> bool:
        if settings.NOTIFICATION_EMAIL_ENABLED:
            return await self._send_email(email, subject, content)
        
        if settings.NOTIFICATION_WEBHOOK_ENABLED:
            return await self._send_webhook(email, subject, content, notification_type)

        return True

    async def _send_email(self, to_email: str, subject: str, content: str) -> bool:
        return True

    async def _send_webhook(
        self,
        email: str,
        subject: str,
        content: str,
        notification_type: str,
    ) -> bool:
        return True

    def _format_alert_message(self, alert: Alert) -> str:
        metric_name = alert.metric.name if alert.metric else "Unknown"
        metric_code = alert.metric.code if alert.metric else "Unknown"
        business_line = alert.metric.business_line if alert.metric else "Unknown"

        return f"""
指标告警通知

告警级别: {alert.level.value.upper()}
指标名称: {metric_name}
指标编码: {metric_code}
业务线: {business_line}

当前值: {alert.current_value}
预期值: {alert.expected_value or 'N/A'}
偏差: {alert.deviation or 'N/A'}

开始时间: {alert.started_at.strftime('%Y-%m-%d %H:%M:%S')}

请及时处理。
        """.strip()

    def _format_recovery_message(self, alert: Alert) -> str:
        metric_name = alert.metric.name if alert.metric else "Unknown"

        return f"""
指标恢复通知

指标名称: {metric_name}
告警级别: {alert.level.value.upper()}

开始时间: {alert.started_at.strftime('%Y-%m-%d %H:%M:%S')}
恢复时间: {alert.ended_at.strftime('%Y-%m-%d %H:%M:%S') if alert.ended_at else 'N/A'}

指标已恢复正常。
        """.strip()

    def _format_acknowledge_message(self, alert: Alert) -> str:
        metric_name = alert.metric.name if alert.metric else "Unknown"

        return f"""
告警确认通知

指标名称: {metric_name}
告警级别: {alert.level.value.upper()}

确认人: {alert.acknowledged_by or 'Unknown'}
确认时间: {alert.acknowledged_at.strftime('%Y-%m-%d %H:%M:%S') if alert.acknowledged_at else 'N/A'}

告警已被确认，正在处理中。
        """.strip()


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