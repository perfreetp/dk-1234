from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import MetricType, MetricStatus
from app.schemas import (
    MetricCreate,
    MetricUpdate,
    MetricResponse,
    MetricDataCreate,
    MetricSummary,
    MetricHistoryResponse,
    MetricDataPoint,
)
from app.services import MetricService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("", response_model=MetricResponse, status_code=201)
async def create_metric(
    metric_data: MetricCreate,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    existing = await service.get_metric_by_code(metric_data.code)
    if existing:
        raise HTTPException(status_code=400, detail="指标编码已存在")
    
    metric = await service.create_metric(metric_data)
    return metric


@router.get("", response_model=List[MetricResponse])
async def list_metrics(
    business_line: Optional[str] = Query(None, description="业务线筛选"),
    metric_type: Optional[MetricType] = Query(None, description="指标类型筛选"),
    status: Optional[MetricStatus] = Query(None, description="状态筛选"),
    is_active: Optional[bool] = Query(None, description="是否活跃"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metrics, _ = await service.get_metrics(
        business_line=business_line,
        metric_type=metric_type,
        status=status,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return metrics


@router.get("/summary", response_model=List[MetricSummary])
async def get_metrics_summary(
    business_line: Optional[str] = Query(None, description="业务线筛选"),
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metrics, _ = await service.get_metrics(business_line=business_line, limit=1000)
    
    summaries = []
    for metric in metrics:
        summary = await service.get_metric_summary(metric.id)
        summaries.append(MetricSummary(**summary))
    
    return summaries


@router.get("/{metric_id}", response_model=MetricResponse)
async def get_metric(
    metric_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metric = await service.get_metric_by_id(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    return metric


@router.put("/{metric_id}", response_model=MetricResponse)
async def update_metric(
    metric_id: int,
    metric_data: MetricUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metric = await service.update_metric(metric_id, metric_data)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    return metric


@router.delete("/{metric_id}", status_code=204)
async def delete_metric(
    metric_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    success = await service.delete_metric(metric_id)
    if not success:
        raise HTTPException(status_code=404, detail="指标不存在")


@router.post("/{metric_id}/data", status_code=201)
async def add_metric_data(
    metric_id: int,
    data: MetricDataCreate,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metric = await service.get_metric_by_id(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    
    data.metric_code = metric.code
    metric_data = await service.add_metric_data(data)
    return {"message": "数据添加成功", "data_id": metric_data.id}


@router.post("/data", status_code=201)
async def add_data_by_code(
    data: MetricDataCreate,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metric_data = await service.add_metric_data(data)
    if not metric_data:
        raise HTTPException(status_code=404, detail="指标编码不存在")
    return {"message": "数据添加成功", "data_id": metric_data.id}


@router.get("/{metric_id}/history", response_model=MetricHistoryResponse)
async def get_metric_history(
    metric_id: int,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    metric = await service.get_metric_by_id(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="指标不存在")
    
    if not start_time:
        start_time = datetime.utcnow() - timedelta(days=7)
    if not end_time:
        end_time = datetime.utcnow()
    
    data_points = await service.get_metric_data(
        metric_id, start_time=start_time, end_time=end_time, limit=limit
    )
    
    values = [dp.value for dp in data_points]
    summary = {
        "count": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "avg": sum(values) / len(values) if values else None,
    }
    
    return MetricHistoryResponse(
        metric_id=metric_id,
        metric_name=metric.name,
        data_points=[
            MetricDataPoint(
                value=dp.value,
                recorded_at=dp.recorded_at,
                dimensions=dp.dimensions,
            )
            for dp in data_points
        ],
        start_time=start_time,
        end_time=end_time,
        summary=summary,
    )


@router.get("/{metric_id}/related", response_model=List[MetricResponse])
async def get_related_metrics(
    metric_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = MetricService(session)
    related = await service.get_related_metrics(metric_id)
    return related