from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
)
from app.services import SubscriptionService, MetricService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    subscription_data: SubscriptionCreate,
    session: AsyncSession = Depends(get_session),
):
    metric_service = MetricService(session)
    metric = await metric_service.get_metric_by_id(subscription_data.metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    
    service = SubscriptionService(session)
    subscription = await service.create_subscription(subscription_data)
    return subscription


@router.get("", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    metric_id: int = Query(None, description="指标ID筛选"),
    session: AsyncSession = Depends(get_session),
):
    service = SubscriptionService(session)
    if metric_id:
        subscriptions = await service.get_subscriptions_by_metric(metric_id)
    else:
        from sqlalchemy import select
        from app.models import Subscription
        result = await session.execute(select(Subscription))
        subscriptions = list(result.scalars().all())
    return subscriptions


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = SubscriptionService(session)
    subscription = await service.get_subscription_by_id(subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return subscription


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    subscription_data: SubscriptionUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = SubscriptionService(session)
    subscription = await service.update_subscription(subscription_id, subscription_data)
    if not subscription:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return subscription


@router.delete("/{subscription_id}", status_code=204)
async def delete_subscription(
    subscription_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = SubscriptionService(session)
    success = await service.delete_subscription(subscription_id)
    if not success:
        raise HTTPException(status_code=404, detail="订阅不存在")