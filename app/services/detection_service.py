from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Metric, MetricData, Rule, RuleType, Alert, AlertLevel, AlertStatus
from app.schemas import RuleCreate, RuleUpdate


class DetectionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def detect_anomalies(self, metric_id: int) -> List[Alert]:
        metric = await self._get_metric_with_rules(metric_id)
        if not metric or not metric.rules:
            return []

        alerts = []
        for rule in metric.rules:
            if not rule.is_active:
                continue

            anomaly_result = await self._check_rule(metric_id, rule)
            if anomaly_result:
                alert = await self._create_or_update_alert(
                    metric_id=metric_id,
                    rule=rule,
                    current_value=anomaly_result["current_value"],
                    expected_value=anomaly_result["expected_value"],
                    deviation=anomaly_result["deviation"],
                )
                alerts.append(alert)

        return alerts

    async def _get_metric_with_rules(self, metric_id: int) -> Optional[Metric]:
        result = await self.session.execute(
            select(Metric)
            .where(Metric.id == metric_id)
        )
        metric = result.scalar_one_or_none()
        if metric:
            rules_result = await self.session.execute(
                select(Rule).where(and_(Rule.metric_id == metric_id, Rule.is_active == True))
            )
            metric.rules = list(rules_result.scalars().all())
        return metric

    async def _check_rule(self, metric_id: int, rule: Rule) -> Optional[dict]:
        if rule.rule_type == RuleType.DAY_OVER_DAY:
            return await self._check_day_over_day(metric_id, rule)
        elif rule.rule_type == RuleType.WEEK_OVER_WEEK:
            return await self._check_week_over_week(metric_id, rule)
        elif rule.rule_type == RuleType.FIXED_UPPER_LIMIT:
            return await self._check_fixed_upper_limit(metric_id, rule)
        elif rule.rule_type == RuleType.FIXED_LOWER_LIMIT:
            return await self._check_fixed_lower_limit(metric_id, rule)
        elif rule.rule_type == RuleType.CONSECUTIVE_ANOMALY:
            return await self._check_consecutive_anomaly(metric_id, rule)
        return None

    async def _get_data_at_time(self, metric_id: int, target_time: datetime) -> Optional[MetricData]:
        start = target_time - timedelta(hours=1)
        end = target_time + timedelta(hours=1)
        
        result = await self.session.execute(
            select(MetricData)
            .where(and_(
                MetricData.metric_id == metric_id,
                MetricData.recorded_at >= start,
                MetricData.recorded_at <= end
            ))
            .order_by(desc(MetricData.recorded_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_data(self, metric_id: int, limit: int = 10) -> List[MetricData]:
        result = await self.session.execute(
            select(MetricData)
            .where(MetricData.metric_id == metric_id)
            .order_by(desc(MetricData.recorded_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _check_day_over_day(self, metric_id: int, rule: Rule) -> Optional[dict]:
        latest_data = await self._get_latest_data(metric_id, 1)
        if not latest_data:
            return None

        current = latest_data[0]
        yesterday = current.recorded_at - timedelta(days=1)
        previous = await self._get_data_at_time(metric_id, yesterday)

        if not previous:
            return None

        change_rate = abs((current.value - previous.value) / previous.value) if previous.value != 0 else 0

        if change_rate >= rule.threshold:
            return {
                "current_value": current.value,
                "expected_value": previous.value,
                "deviation": change_rate,
            }
        return None

    async def _check_week_over_week(self, metric_id: int, rule: Rule) -> Optional[dict]:
        latest_data = await self._get_latest_data(metric_id, 1)
        if not latest_data:
            return None

        current = latest_data[0]
        last_week = current.recorded_at - timedelta(weeks=1)
        previous = await self._get_data_at_time(metric_id, last_week)

        if not previous:
            return None

        change_rate = abs((current.value - previous.value) / previous.value) if previous.value != 0 else 0

        if change_rate >= rule.threshold:
            return {
                "current_value": current.value,
                "expected_value": previous.value,
                "deviation": change_rate,
            }
        return None

    async def _check_fixed_upper_limit(self, metric_id: int, rule: Rule) -> Optional[dict]:
        latest_data = await self._get_latest_data(metric_id, 1)
        if not latest_data:
            return None

        current = latest_data[0]
        if current.value > rule.threshold:
            return {
                "current_value": current.value,
                "expected_value": rule.threshold,
                "deviation": current.value - rule.threshold,
            }
        return None

    async def _check_fixed_lower_limit(self, metric_id: int, rule: Rule) -> Optional[dict]:
        latest_data = await self._get_latest_data(metric_id, 1)
        if not latest_data:
            return None

        current = latest_data[0]
        if current.value < rule.threshold:
            return {
                "current_value": current.value,
                "expected_value": rule.threshold,
                "deviation": rule.threshold - current.value,
            }
        return None

    async def _check_consecutive_anomaly(self, metric_id: int, rule: Rule) -> Optional[dict]:
        data_points = await self._get_latest_data(metric_id, rule.consecutive_count)
        if len(data_points) < rule.consecutive_count:
            return None

        anomaly_count = 0
        total_deviation = 0
        for data in data_points:
            if rule.secondary_threshold is not None:
                if abs(data.value) > rule.secondary_threshold:
                    anomaly_count += 1
                    total_deviation += abs(data.value - rule.secondary_threshold)
            else:
                if abs(data.value) > rule.threshold:
                    anomaly_count += 1
                    total_deviation += abs(data.value - rule.threshold)

        if anomaly_count >= rule.consecutive_count:
            avg_deviation = total_deviation / anomaly_count
            return {
                "current_value": data_points[0].value,
                "expected_value": rule.threshold,
                "deviation": avg_deviation,
            }
        return None

    async def _create_or_update_alert(
        self,
        metric_id: int,
        rule: Rule,
        current_value: float,
        expected_value: Optional[float],
        deviation: Optional[float],
    ) -> Alert:
        existing_alert = await self._get_active_alert(metric_id, rule.id)
        
        if existing_alert:
            existing_alert.current_value = current_value
            existing_alert.expected_value = expected_value
            existing_alert.deviation = deviation
            await self.session.commit()
            await self.session.refresh(existing_alert)
            return existing_alert

        alert = Alert(
            metric_id=metric_id,
            rule_id=rule.id,
            level=rule.alert_level,
            status=AlertStatus.ACTIVE,
            current_value=current_value,
            expected_value=expected_value,
            deviation=deviation,
            started_at=datetime.utcnow(),
        )
        self.session.add(alert)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def _get_active_alert(self, metric_id: int, rule_id: int) -> Optional[Alert]:
        result = await self.session.execute(
            select(Alert).where(and_(
                Alert.metric_id == metric_id,
                Alert.rule_id == rule_id,
                Alert.status == AlertStatus.ACTIVE
            ))
        )
        return result.scalar_one_or_none()


class RuleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_rule(self, rule_data: RuleCreate) -> Rule:
        rule = Rule(
            metric_id=rule_data.metric_id,
            name=rule_data.name,
            rule_type=rule_data.rule_type,
            threshold=rule_data.threshold,
            secondary_threshold=rule_data.secondary_threshold,
            consecutive_count=rule_data.consecutive_count,
            alert_level=rule_data.alert_level,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def get_rule_by_id(self, rule_id: int) -> Optional[Rule]:
        result = await self.session.execute(
            select(Rule).where(Rule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def get_rules_by_metric(self, metric_id: int) -> List[Rule]:
        result = await self.session.execute(
            select(Rule).where(Rule.metric_id == metric_id)
        )
        return list(result.scalars().all())

    async def update_rule(self, rule_id: int, rule_data: RuleUpdate) -> Optional[Rule]:
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return None

        update_data = rule_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rule, field, value)

        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        await self.session.commit()
        return True