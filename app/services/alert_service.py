from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Alert, AlertStatus, AlertLevel, Metric, Review
from app.schemas import AlertAcknowledge, AlertResolve


class AlertService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_alert_by_id(self, alert_id: int) -> Optional[Alert]:
        result = await self.session.execute(
            select(Alert)
            .options(selectinload(Alert.metric), selectinload(Alert.reviews))
            .where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_alerts(
        self,
        metric_id: Optional[int] = None,
        status: Optional[AlertStatus] = None,
        level: Optional[AlertLevel] = None,
        business_line: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Alert], int]:
        query = select(Alert).options(selectinload(Alert.metric))
        count_query = select(func.count(Alert.id))

        conditions = []
        if metric_id:
            conditions.append(Alert.metric_id == metric_id)
        if status:
            conditions.append(Alert.status == status)
        if level:
            conditions.append(Alert.level == level)
        if start_time:
            conditions.append(Alert.started_at >= start_time)
        if end_time:
            conditions.append(Alert.started_at <= end_time)
        if business_line:
            query = query.join(Metric).where(Metric.business_line == business_line)
            count_query = count_query.join(Metric).where(Metric.business_line == business_line)

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        query = query.order_by(desc(Alert.started_at)).offset(skip).limit(limit)
        result = await self.session.execute(query)
        alerts = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar()

        return alerts, total

    async def acknowledge_alert(self, alert_id: int, data: AlertAcknowledge) -> Optional[Alert]:
        alert = await self.get_alert_by_id(alert_id)
        if not alert or alert.status != AlertStatus.ACTIVE:
            return None

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = data.acknowledged_by

        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def resolve_alert(self, alert_id: int, data: AlertResolve) -> Optional[Alert]:
        alert = await self.get_alert_by_id(alert_id)
        if not alert or alert.status == AlertStatus.RESOLVED:
            return None

        alert.status = AlertStatus.RESOLVED
        alert.ended_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def silence_alert(self, alert_id: int, duration_minutes: int = 60) -> Optional[Alert]:
        alert = await self.get_alert_by_id(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.SILENCED
        alert.silenced_at = datetime.utcnow()
        alert.silenced_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        alert.silenced_duration_minutes = duration_minutes

        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def is_alert_silenced(self, alert: Alert) -> bool:
        if alert.status != AlertStatus.SILENCED:
            return False
        if alert.silenced_until and datetime.utcnow() > alert.silenced_until:
            alert.status = AlertStatus.ACTIVE
            alert.silenced_at = None
            alert.silenced_until = None
            await self.session.commit()
            return False
        return True

    async def get_active_alerts_excluding_silenced(self, metric_id: int) -> List[Alert]:
        alerts = await self.get_active_alerts_by_metric(metric_id)
        return [a for a in alerts if not await self.is_alert_silenced(a)]

    async def get_active_alerts_by_metric(self, metric_id: int) -> List[Alert]:
        result = await self.session.execute(
            select(Alert)
            .where(and_(
                Alert.metric_id == metric_id,
                Alert.status == AlertStatus.ACTIVE
            ))
            .order_by(desc(Alert.started_at))
        )
        return list(result.scalars().all())

    async def get_alert_summary(self, alert_id: int) -> Optional[dict]:
        alert = await self.get_alert_by_id(alert_id)
        if not alert:
            return None

        impact_duration = None
        if alert.ended_at:
            impact_duration = int((alert.ended_at - alert.started_at).total_seconds() / 60)
        elif alert.status == AlertStatus.ACTIVE:
            impact_duration = int((datetime.utcnow() - alert.started_at).total_seconds() / 60)

        return {
            "metric_id": alert.metric_id,
            "metric_name": alert.metric.name if alert.metric else None,
            "metric_code": alert.metric.code if alert.metric else None,
            "business_line": alert.metric.business_line if alert.metric else None,
            "alert_id": alert.id,
            "level": alert.level,
            "status": alert.status,
            "current_value": alert.current_value,
            "expected_value": alert.expected_value,
            "deviation": alert.deviation,
            "started_at": alert.started_at,
            "ended_at": alert.ended_at,
            "impact_duration_minutes": impact_duration,
        }

    async def get_alerts_by_business_line(
        self,
        business_line: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Alert]:
        query = (
            select(Alert)
            .options(selectinload(Alert.metric))
            .join(Metric)
            .where(Metric.business_line == business_line)
        )

        if start_time:
            query = query.where(Alert.started_at >= start_time)
        if end_time:
            query = query.where(Alert.started_at <= end_time)

        query = query.order_by(desc(Alert.started_at))
        result = await self.session.execute(query)
        return list(result.scalars().all())


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_review(self, alert_id: int, reviewer: str, **kwargs) -> Review:
        review = Review(
            alert_id=alert_id,
            reviewer=reviewer,
            root_cause=kwargs.get("root_cause"),
            impact_analysis=kwargs.get("impact_analysis"),
            action_taken=kwargs.get("action_taken"),
            lessons_learned=kwargs.get("lessons_learned"),
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def get_review_by_id(self, review_id: int) -> Optional[Review]:
        result = await self.session.execute(
            select(Review).where(Review.id == review_id)
        )
        return result.scalar_one_or_none()

    async def get_reviews_by_alert(self, alert_id: int) -> List[Review]:
        result = await self.session.execute(
            select(Review)
            .where(Review.alert_id == alert_id)
            .order_by(desc(Review.created_at))
        )
        return list(result.scalars().all())

    async def update_review(self, review_id: int, **kwargs) -> Optional[Review]:
        review = await self.get_review_by_id(review_id)
        if not review:
            return None

        for field in ["root_cause", "impact_analysis", "action_taken", "lessons_learned"]:
            if field in kwargs:
                setattr(review, field, kwargs[field])

        await self.session.commit()
        await self.session.refresh(review)
        return review