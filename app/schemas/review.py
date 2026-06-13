from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReviewBase(BaseModel):
    reviewer: str = Field(..., max_length=100, description="复盘人")
    root_cause: Optional[str] = Field(None, description="根本原因")
    impact_analysis: Optional[str] = Field(None, description="影响分析")
    action_taken: Optional[str] = Field(None, description="采取的措施")
    lessons_learned: Optional[str] = Field(None, description="经验教训")


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(BaseModel):
    root_cause: Optional[str] = None
    impact_analysis: Optional[str] = None
    action_taken: Optional[str] = None
    lessons_learned: Optional[str] = None


class ReviewResponse(ReviewBase):
    id: int
    alert_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WeeklyReportResponse(BaseModel):
    id: int
    business_line: str
    week_start: datetime
    week_end: datetime
    total_alerts: int
    critical_alerts: int
    warning_alerts: int
    resolved_alerts: int
    avg_resolution_time: Optional[float]
    summary: Optional[str]
    generated_at: datetime

    class Config:
        from_attributes = True


class WeeklyReportGenerate(BaseModel):
    business_line: str = Field(..., max_length=100, description="业务线")
    week_start: datetime = Field(..., description="周报开始日期")
    week_end: datetime = Field(..., description="周报结束日期")