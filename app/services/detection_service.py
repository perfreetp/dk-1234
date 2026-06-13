from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Metric, MetricData, Rule, RuleType, Alert, AlertLevel, AlertStatus, MetricStatus
from app.schemas import RuleCreate, RuleUpdate


class DetectionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def detect_anomalies(self, metric_id: int, send_notifications: bool = False) -> dict:
        metric = await self._get_metric_with_rules(metric_id)
        if not metric or not metric.rules:
            return {
                "metric_id": metric_id,
                "status": "unknown",
                "alerts": [],
                "message": "指标或规则不存在"
            }

        alerts = []
        restored_alerts = []
        silenced_alerts = []
        new_alerts = []
        notifications_sent = []

        from app.services.notification_service import NotificationService
        notification_service = NotificationService(self.session)

        for rule in metric.rules:
            if not rule.is_active:
                continue

            anomaly_result = await self._check_rule(metric_id, rule)
            active_alert = await self._get_active_or_silenced_alert(metric_id, rule.id)

            if active_alert and active_alert.status == AlertStatus.SILENCED:
                if active_alert.silenced_until and datetime.utcnow() > active_alert.silenced_until:
                    active_alert.status = AlertStatus.ACTIVE
                    active_alert.silenced_at = None
                    active_alert.silenced_until = None
                    await self.session.commit()
                    await self.session.refresh(active_alert)
                    if anomaly_result:
                        active_alert.current_value = anomaly_result["current_value"]
                        active_alert.expected_value = anomaly_result["expected_value"]
                        active_alert.deviation = anomaly_result["deviation"]
                        await self.session.commit()
                        await self.session.refresh(active_alert)
                        alerts.append(active_alert)
                    else:
                        active_alert.status = AlertStatus.RESOLVED
                        active_alert.ended_at = datetime.utcnow()
                        await self.session.commit()
                        await self.session.refresh(active_alert)
                        restored_alerts.append(active_alert)
                        if send_notifications:
                            notify_result = await notification_service.notify_recovery(active_alert)
                            notifications_sent.extend(notify_result)
                else:
                    silenced_alerts.append({
                        "alert_id": active_alert.id,
                        "rule_name": next((r.name for r in metric.rules if r.id == active_alert.rule_id), None),
                        "silenced_at": active_alert.silenced_at.isoformat() if active_alert.silenced_at else None,
                        "silenced_until": active_alert.silenced_until.isoformat() if active_alert.silenced_until else None,
                        "silenced_duration_minutes": active_alert.silenced_duration_minutes,
                    })
                    continue

            if anomaly_result:
                if active_alert and active_alert.status == AlertStatus.ACTIVE:
                    active_alert.current_value = anomaly_result["current_value"]
                    active_alert.expected_value = anomaly_result["expected_value"]
                    active_alert.deviation = anomaly_result["deviation"]
                    await self.session.commit()
                    await self.session.refresh(active_alert)
                    alerts.append(active_alert)
                elif not active_alert:
                    alert = await self._create_or_update_alert(
                        metric_id=metric_id,
                        rule=rule,
                        current_value=anomaly_result["current_value"],
                        expected_value=anomaly_result["expected_value"],
                        deviation=anomaly_result["deviation"],
                    )
                    alerts.append(alert)
                    new_alerts.append(alert)
                    if send_notifications:
                        notify_result = await notification_service.notify_alert(alert)
                        notifications_sent.extend(notify_result)
            else:
                if active_alert and active_alert.status == AlertStatus.ACTIVE:
                    active_alert.status = AlertStatus.RESOLVED
                    active_alert.ended_at = datetime.utcnow()
                    await self.session.commit()
                    await self.session.refresh(active_alert)
                    restored_alerts.append(active_alert)
                    if send_notifications:
                        notify_result = await notification_service.notify_recovery(active_alert)
                        notifications_sent.extend(notify_result)

        await self._update_metric_status(metric_id, alerts)

        related_metrics = await self._get_related_metrics(metric_id)
        history_summary = await self._get_history_summary(metric_id)

        worst_level = AlertLevel.INFO
        if alerts:
            for alert in alerts:
                if alert.level == AlertLevel.CRITICAL:
                    worst_level = AlertLevel.CRITICAL
                    break
                elif alert.level == AlertLevel.WARNING:
                    worst_level = AlertLevel.WARNING

        impact_duration = None
        if alerts:
            oldest_start = min(a.started_at for a in alerts)
            impact_duration = int((datetime.utcnow() - oldest_start).total_seconds() / 60)

        return {
            "metric_id": metric_id,
            "metric_name": metric.name,
            "metric_code": metric.code,
            "status": worst_level if alerts else MetricStatus.NORMAL,
            "current_value": alerts[0].current_value if alerts else None,
            "alert_level": worst_level.value if alerts else None,
            "impact_duration_minutes": impact_duration,
            "active_alerts_count": len(alerts),
            "restored_alerts_count": len(restored_alerts),
            "silenced_alerts_count": len(silenced_alerts),
            "new_alerts_count": len(new_alerts),
            "notifications_sent_count": len(notifications_sent),
            "alerts": [{
                "alert_id": a.id,
                "rule_id": a.rule_id,
                "rule_name": next((r.name for r in metric.rules if r.id == a.rule_id), None),
                "level": a.level.value,
                "current_value": a.current_value,
                "expected_value": a.expected_value,
                "deviation": a.deviation,
                "started_at": a.started_at.isoformat(),
                "impact_duration_minutes": int((datetime.utcnow() - a.started_at).total_seconds() / 60),
            } for a in alerts],
            "restored_alerts": [{
                "alert_id": a.id,
                "rule_name": next((r.name for r in metric.rules if r.id == a.rule_id), None),
                "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            } for a in restored_alerts],
            "silenced_alerts": silenced_alerts,
            "notifications_sent": notifications_sent,
            "related_metrics": related_metrics,
            "history_summary": history_summary,
        }

    async def _update_metric_status(self, metric_id: int, active_alerts: List[Alert]):
        metric = await self.session.get(Metric, metric_id)
        if not metric:
            return

        if not active_alerts:
            metric.status = MetricStatus.NORMAL
        else:
            has_critical = any(a.level == AlertLevel.CRITICAL for a in active_alerts)
            metric.status = MetricStatus.CRITICAL if has_critical else MetricStatus.WARNING

        await self.session.commit()

    async def _get_related_metrics(self, metric_id: int) -> List[dict]:
        metric = await self.session.get(Metric, metric_id)
        if not metric or not metric.related_metric_ids:
            return []

        result = await self.session.execute(
            select(Metric).where(Metric.id.in_(metric.related_metric_ids))
        )
        related = list(result.scalars().all())
        return [{
            "id": m.id,
            "name": m.name,
            "code": m.code,
            "status": m.status.value,
            "business_line": m.business_line,
        } for m in related]

    async def _get_history_summary(self, metric_id: int) -> dict:
        yesterday = datetime.utcnow() - timedelta(days=1)
        data_points = await self._get_latest_data(metric_id, limit=100)

        values = [dp.value for dp in data_points if dp.recorded_at >= yesterday]

        if not values:
            return {"count": 0, "min": None, "max": None, "avg": None, "trend": None}

        min_val = min(values)
        max_val = max(values)
        avg_val = sum(values) / len(values)

        if len(values) >= 2:
            if values[0] > values[-1]:
                trend = "up"
            elif values[0] < values[-1]:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = None

        return {
            "count": len(values),
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "avg": round(avg_val, 2),
            "trend": trend,
        }

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

    async def _get_active_or_silenced_alert(self, metric_id: int, rule_id: int) -> Optional[Alert]:
        result = await self.session.execute(
            select(Alert).where(and_(
                Alert.metric_id == metric_id,
                Alert.rule_id == rule_id,
                Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.SILENCED])
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