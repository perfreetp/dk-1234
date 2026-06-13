from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models import MetricType, MetricStatus


class MetricBase(BaseModel):
    name: str = Field(..., max_length=100, description="指标名称")
    code: str = Field(..., max_length=50, description="指标编码，唯一标识")
    business_line: str = Field(..., max_length=100, description="业务线")
    metric_type: MetricType = Field(default=MetricType.CUSTOM, description="指标类型")
    description: Optional[str] = Field(None, description="指标描述")
    definition: Optional[str] = Field(None, description="口径说明，指标的计算方式和定义")
    unit: Optional[str] = Field(None, max_length=20, description="单位")
    owner: str = Field(..., max_length=100, description="负责人")
    owner_email: Optional[str] = Field(None, max_length=100, description="负责人邮箱")
    related_metric_ids: Optional[List[int]] = Field(default=[], description="关联指标ID列表")


class MetricCreate(MetricBase):
    pass


class MetricUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    definition: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=20)
    owner: Optional[str] = Field(None, max_length=100)
    owner_email: Optional[str] = Field(None, max_length=100)
    related_metric_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class MetricResponse(MetricBase):
    id: int
    status: MetricStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MetricDataPoint(BaseModel):
    value: float
    recorded_at: datetime
    dimensions: Optional[dict] = None


class MetricDataCreate(BaseModel):
    metric_code: str
    value: float
    recorded_at: Optional[datetime] = None
    dimensions: Optional[dict] = None


class MetricSummary(BaseModel):
    id: int
    name: str
    code: str
    business_line: str
    status: MetricStatus
    current_value: Optional[float] = None
    last_updated: Optional[datetime] = None
    active_alerts_count: int = 0
    trend: Optional[str] = None


class MetricHistoryResponse(BaseModel):
    metric_id: int
    metric_name: str
    data_points: List[MetricDataPoint]
    start_time: datetime
    end_time: datetime
    summary: dict