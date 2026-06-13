from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas import RuleCreate, RuleUpdate, RuleResponse
from app.services import RuleService, DetectionService, MetricService

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    rule_data: RuleCreate,
    session: AsyncSession = Depends(get_session),
):
    metric_service = MetricService(session)
    metric = await metric_service.get_metric_by_id(rule_data.metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    
    service = RuleService(session)
    rule = await service.create_rule(rule_data)
    return rule


@router.get("", response_model=List[RuleResponse])
async def list_rules(
    metric_id: int = Query(None, description="指标ID筛选"),
    session: AsyncSession = Depends(get_session),
):
    service = RuleService(session)
    if metric_id:
        rules = await service.get_rules_by_metric(metric_id)
    else:
        from sqlalchemy import select
        from app.models import Rule
        result = await session.execute(select(Rule))
        rules = list(result.scalars().all())
    return rules


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = RuleService(session)
    rule = await service.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    rule_data: RuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = RuleService(session)
    rule = await service.update_rule(rule_id, rule_data)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = RuleService(session)
    success = await service.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则不存在")


@router.post("/detect/{metric_id}")
async def detect_anomalies(
    metric_id: int,
    send_notifications: bool = Query(True, description="是否发送通知"),
    session: AsyncSession = Depends(get_session),
):
    metric_service = MetricService(session)
    metric = await metric_service.get_metric_by_id(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    
    from app.models import TriggerSource
    detection_service = DetectionService(session)
    result = await detection_service.detect_anomalies(
        metric_id,
        send_notifications=send_notifications,
        trigger_source=TriggerSource.API_DETECTION
    )
    
    return result