from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models import AlertLevel, AlertStatus


class AlertBase(BaseModel):
    metric_id: int
    rule_id: int
    level: AlertLevel
    current_value: float
    expected_value: Optional[float] = None
    deviation: Optional[float] = None
    started_at: datetime


class AlertResponse(AlertBase):
    id: int
    status: AlertStatus
    ended_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    acknowledged_by: str = Field(..., max_length=100, description="确认人")


class AlertResolve(BaseModel):
    resolved_by: str = Field(..., max_length=100, description="解决人")


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertSummary(BaseModel):
    metric_id: int
    metric_name: str
    metric_code: str
    business_line: str
    alert_id: int
    level: AlertLevel
    status: AlertStatus
    current_value: float
    expected_value: Optional[float]
    deviation: Optional[float]
    started_at: datetime
    ended_at: Optional[datetime]
    impact_duration_minutes: Optional[int] = None