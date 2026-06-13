from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from sqlalchemy import select
from app.database import async_session
from app.models import Metric, TriggerSource
from app.services import DetectionService, ReportService


scheduler = AsyncIOScheduler()


async def detect_all_metrics():
    async with async_session() as session:
        result = await session.execute(select(Metric).where(Metric.is_active == True))
        metrics = list(result.scalars().all())
        
        detection_service = DetectionService(session)
        
        for metric in metrics:
            try:
                result = await detection_service.detect_anomalies(
                    metric.id,
                    send_notifications=True,
                    trigger_source=TriggerSource.SCHEDULED_TASK
                )
                print(f"[定时任务] 检测指标 {metric.code}: 新告警 {result.get('new_alerts_count', 0)}, 恢复 {result.get('restored_alerts_count', 0)}, 通知发送 {result.get('notifications_sent_count', 0)}")
            except Exception as e:
                print(f"[定时任务] 检测指标 {metric.code} 时出错: {e}")


async def generate_weekly_reports():
    async with async_session() as session:
        result = await session.execute(select(Metric.business_line).distinct())
        business_lines = [row[0] for row in result.all()]
        
        report_service = ReportService(session)
        
        today = datetime.utcnow()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        for business_line in business_lines:
            try:
                await report_service.generate_weekly_report(
                    business_line=business_line,
                    week_start=week_start,
                    week_end=week_end,
                )
            except Exception as e:
                print(f"生成业务线 {business_line} 周报时出错: {e}")


def setup_scheduler():
    scheduler.add_job(
        detect_all_metrics,
        IntervalTrigger(minutes=5),
        id="detect_anomalies",
        name="检测所有活跃指标异常",
        replace_existing=True,
    )
    
    scheduler.add_job(
        generate_weekly_reports,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="generate_weekly_reports",
        name="每周一生成周报",
        replace_existing=True,
    )
    
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown()