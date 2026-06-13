from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SubscriptionBase(BaseModel):
    subscriber: str = Field(..., max_length=100, description="订阅者姓名")
    subscriber_email: str = Field(..., max_length=100, description="订阅者邮箱")
    notify_on_alert: bool = Field(default=True, description="告警时通知")
    notify_on_recovery: bool = Field(default=True, description="恢复时通知")
    notify_on_acknowledge: bool = Field(default=False, description="确认时通知")
    silent_hours_start: Optional[int] = Field(None, ge=0, le=23, description="静默时段开始（小时）")
    silent_hours_end: Optional[int] = Field(None, ge=0, le=23, description="静默时段结束（小时）")


class SubscriptionCreate(SubscriptionBase):
    metric_id: int


class SubscriptionUpdate(BaseModel):
    notify_on_alert: Optional[bool] = None
    notify_on_recovery: Optional[bool] = None
    notify_on_acknowledge: Optional[bool] = None
    silent_hours_start: Optional[int] = Field(None, ge=0, le=23)
    silent_hours_end: Optional[int] = Field(None, ge=0, le=23)
    is_active: Optional[bool] = None


class SubscriptionResponse(SubscriptionBase):
    id: int
    metric_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True