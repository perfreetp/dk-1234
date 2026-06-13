from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models import RuleType, AlertLevel


class RuleBase(BaseModel):
    name: str = Field(..., max_length=100, description="规则名称")
    rule_type: RuleType = Field(..., description="规则类型")
    threshold: float = Field(..., description="阈值")
    secondary_threshold: Optional[float] = Field(None, description="二级阈值")
    consecutive_count: int = Field(default=1, ge=1, description="连续异常次数")
    alert_level: AlertLevel = Field(default=AlertLevel.WARNING, description="告警级别")


class RuleCreate(RuleBase):
    metric_id: int


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    threshold: Optional[float] = None
    secondary_threshold: Optional[float] = None
    consecutive_count: Optional[int] = Field(None, ge=1)
    alert_level: Optional[AlertLevel] = None
    is_active: Optional[bool] = None


class RuleResponse(RuleBase):
    id: int
    metric_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True