from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Metric, MetricData, MetricStatus, MetricType
from app.schemas import MetricCreate, MetricUpdate, MetricDataCreate


class MetricService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_metric(self, metric_data: MetricCreate) -> Metric:
        metric = Metric(
            name=metric_data.name,
            code=metric_data.code,
            business_line=metric_data.business_line,
            metric_type=metric_data.metric_type,
            description=metric_data.description,
            definition=metric_data.definition,
            unit=metric_data.unit,
            owner=metric_data.owner,
            owner_email=metric_data.owner_email,
            related_metric_ids=metric_data.related_metric_ids or [],
            status=MetricStatus.UNKNOWN,
        )
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def get_metric_by_id(self, metric_id: int) -> Optional[Metric]:
        result = await self.session.execute(
            select(Metric)
            .options(selectinload(Metric.rules), selectinload(Metric.alerts))
            .where(Metric.id == metric_id)
        )
        return result.scalar_one_or_none()

    async def get_metric_by_code(self, code: str) -> Optional[Metric]:
        result = await self.session.execute(
            select(Metric).where(Metric.code == code)
        )
        return result.scalar_one_or_none()

    async def get_metrics(
        self,
        business_line: Optional[str] = None,
        metric_type: Optional[MetricType] = None,
        status: Optional[MetricStatus] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Metric], int]:
        query = select(Metric)
        count_query = select(Metric)

        conditions = []
        if business_line:
            conditions.append(Metric.business_line == business_line)
        if metric_type:
            conditions.append(Metric.metric_type == metric_type)
        if status:
            conditions.append(Metric.status == status)
        if is_active is not None:
            conditions.append(Metric.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        query = query.offset(skip).limit(limit).order_by(desc(Metric.updated_at))
        result = await self.session.execute(query)
        metrics = result.scalars().all()

        count_result = await self.session.execute(count_query)
        total = len(count_result.scalars().all())

        return list(metrics), total

    async def update_metric(self, metric_id: int, metric_data: MetricUpdate) -> Optional[Metric]:
        metric = await self.get_metric_by_id(metric_id)
        if not metric:
            return None

        update_data = metric_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(metric, field, value)

        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def delete_metric(self, metric_id: int) -> bool:
        metric = await self.get_metric_by_id(metric_id)
        if not metric:
            return False

        await self.session.delete(metric)
        await self.session.commit()
        return True

    async def add_metric_data(self, data: MetricDataCreate) -> Optional[MetricData]:
        metric = await self.get_metric_by_code(data.metric_code)
        if not metric:
            return None

        recorded_at = data.recorded_at or datetime.utcnow()
        metric_data = MetricData(
            metric_id=metric.id,
            value=data.value,
            recorded_at=recorded_at,
            dimensions=data.dimensions,
        )
        self.session.add(metric_data)
        await self.session.commit()
        await self.session.refresh(metric_data)
        return metric_data

    async def get_metric_data(
        self,
        metric_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MetricData]:
        query = select(MetricData).where(MetricData.metric_id == metric_id)

        if start_time:
            query = query.where(MetricData.recorded_at >= start_time)
        if end_time:
            query = query.where(MetricData.recorded_at <= end_time)

        query = query.order_by(desc(MetricData.recorded_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_data(self, metric_id: int) -> Optional[MetricData]:
        result = await self.session.execute(
            select(MetricData)
            .where(MetricData.metric_id == metric_id)
            .order_by(desc(MetricData.recorded_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_metric_status(self, metric_id: int, status: MetricStatus) -> bool:
        metric = await self.get_metric_by_id(metric_id)
        if not metric:
            return False

        metric.status = status
        await self.session.commit()
        return True

    async def get_related_metrics(self, metric_id: int) -> List[Metric]:
        metric = await self.get_metric_by_id(metric_id)
        if not metric or not metric.related_metric_ids:
            return []

        result = await self.session.execute(
            select(Metric).where(Metric.id.in_(metric.related_metric_ids))
        )
        return list(result.scalars().all())

    async def get_metric_summary(self, metric_id: int) -> dict:
        metric = await self.get_metric_by_id(metric_id)
        if not metric:
            return {}

        latest_data = await self.get_latest_data(metric_id)
        
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_data = await self.get_metric_data(metric_id, start_time=yesterday, limit=100)

        active_alerts = [a for a in metric.alerts if a.status == "active"] if metric.alerts else []

        trend = None
        if len(recent_data) >= 2:
            if recent_data[0].value > recent_data[-1].value:
                trend = "up"
            elif recent_data[0].value < recent_data[-1].value:
                trend = "down"
            else:
                trend = "stable"

        return {
            "id": metric.id,
            "name": metric.name,
            "code": metric.code,
            "business_line": metric.business_line,
            "status": metric.status,
            "current_value": latest_data.value if latest_data else None,
            "last_updated": latest_data.recorded_at if latest_data else None,
            "active_alerts_count": len(active_alerts),
            "trend": trend,
        }