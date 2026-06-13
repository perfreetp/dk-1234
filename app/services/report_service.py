from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Alert, Metric, Review, WeeklyReport, AlertStatus, AlertLevel
from collections import defaultdict


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_weekly_report(
        self,
        business_line: str,
        week_start: datetime,
        week_end: datetime,
    ) -> WeeklyReport:
        alerts = await self._get_alerts_in_period(business_line, week_start, week_end)

        total_alerts = len(alerts)
        critical_alerts = sum(1 for a in alerts if a.level == AlertLevel.CRITICAL)
        warning_alerts = sum(1 for a in alerts if a.level == AlertLevel.WARNING)
        resolved_alerts = sum(1 for a in alerts if a.status == AlertStatus.RESOLVED)

        avg_resolution_time = await self._calculate_avg_resolution_time(alerts)

        summary = await self._generate_summary(alerts, business_line, week_start, week_end)

        report = WeeklyReport(
            business_line=business_line,
            week_start=week_start,
            week_end=week_end,
            total_alerts=total_alerts,
            critical_alerts=critical_alerts,
            warning_alerts=warning_alerts,
            resolved_alerts=resolved_alerts,
            avg_resolution_time=avg_resolution_time,
            summary=summary,
        )

        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def _get_alerts_in_period(
        self,
        business_line: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Alert]:
        result = await self.session.execute(
            select(Alert)
            .options(selectinload(Alert.metric), selectinload(Alert.reviews))
            .join(Metric)
            .where(and_(
                Metric.business_line == business_line,
                Alert.started_at >= start_time,
                Alert.started_at <= end_time,
            ))
            .order_by(desc(Alert.started_at))
        )
        return list(result.scalars().all())

    async def _calculate_avg_resolution_time(self, alerts: List[Alert]) -> Optional[float]:
        resolved_alerts = [a for a in alerts if a.status == AlertStatus.RESOLVED and a.ended_at]
        if not resolved_alerts:
            return None

        total_minutes = 0
        for alert in resolved_alerts:
            if alert.ended_at and alert.started_at:
                delta = alert.ended_at - alert.started_at
                total_minutes += delta.total_seconds() / 60

        return total_minutes / len(resolved_alerts)

    async def _generate_summary(
        self,
        alerts: List[Alert],
        business_line: str,
        week_start: datetime,
        week_end: datetime,
    ) -> str:
        if not alerts:
            return f"{business_line} 在 {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')} 期间无告警。"

        metric_alerts = defaultdict(list)
        for alert in alerts:
            if alert.metric:
                metric_alerts[alert.metric.name].append(alert)

        critical_count = sum(1 for a in alerts if a.level == AlertLevel.CRITICAL)
        warning_count = sum(1 for a in alerts if a.level == AlertLevel.WARNING)
        resolved_count = sum(1 for a in alerts if a.status == AlertStatus.RESOLVED)

        top_metrics = sorted(metric_alerts.items(), key=lambda x: len(x[1]), reverse=True)[:5]

        summary_parts = [
            f"## {business_line} 监控周报",
            f"**统计周期**: {week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}",
            "",
            "### 告警概览",
            f"- 总告警数: {len(alerts)}",
            f"- 严重告警: {critical_count}",
            f"- 警告告警: {warning_count}",
            f"- 已恢复: {resolved_count}",
            "",
            "### 告警最多的指标",
        ]

        for metric_name, metric_alert_list in top_metrics:
            summary_parts.append(f"- {metric_name}: {len(metric_alert_list)} 次")

        reviewed_alerts = [a for a in alerts if a.reviews]
        if reviewed_alerts:
            summary_parts.append("")
            summary_parts.append("### 复盘记录")
            for alert in reviewed_alerts[:5]:
                for review in alert.reviews:
                    summary_parts.append(f"- **{alert.metric.name if alert.metric else 'Unknown'}**: {review.root_cause or '待分析'}")

        return "\n".join(summary_parts)

    async def get_weekly_report(self, report_id: int) -> Optional[WeeklyReport]:
        result = await self.session.execute(
            select(WeeklyReport).where(WeeklyReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def get_weekly_reports_by_business_line(
        self,
        business_line: str,
        limit: int = 10,
    ) -> List[WeeklyReport]:
        result = await self.session.execute(
            select(WeeklyReport)
            .where(WeeklyReport.business_line == business_line)
            .order_by(desc(WeeklyReport.week_start))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_business_line_stats(
        self,
        business_line: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not start_time:
            start_time = datetime.utcnow() - timedelta(days=7)
        if not end_time:
            end_time = datetime.utcnow()

        alerts = await self._get_alerts_in_period(business_line, start_time, end_time)

        metrics_result = await self.session.execute(
            select(func.count(Metric.id)).where(Metric.business_line == business_line)
        )
        total_metrics = metrics_result.scalar()

        active_alerts = [a for a in alerts if a.status == AlertStatus.ACTIVE]

        return {
            "business_line": business_line,
            "period": {
                "start": start_time,
                "end": end_time,
            },
            "total_metrics": total_metrics,
            "total_alerts": len(alerts),
            "active_alerts": len(active_alerts),
            "critical_alerts": sum(1 for a in alerts if a.level == AlertLevel.CRITICAL),
            "warning_alerts": sum(1 for a in alerts if a.level == AlertLevel.WARNING),
            "resolved_alerts": sum(1 for a in alerts if a.status == AlertStatus.RESOLVED),
        }