from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.database import Base


class MetricType(str, enum.Enum):
    REVENUE = "revenue"
    CONVERSION = "conversion"
    RETENTION = "retention"
    INVENTORY = "inventory"
    CUSTOM = "custom"


class MetricStatus(str, enum.Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class RuleType(str, enum.Enum):
    DAY_OVER_DAY = "day_over_day"
    WEEK_OVER_WEEK = "week_over_week"
    FIXED_UPPER_LIMIT = "fixed_upper_limit"
    FIXED_LOWER_LIMIT = "fixed_lower_limit"
    CONSECUTIVE_ANOMALY = "consecutive_anomaly"


class AlertLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SILENCED = "silenced"


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    business_line: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_type: Mapped[MetricType] = mapped_column(SQLEnum(MetricType), default=MetricType.CUSTOM)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[MetricStatus] = mapped_column(SQLEnum(MetricStatus), default=MetricStatus.UNKNOWN)
    related_metric_ids: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rules: Mapped[List["Rule"]] = relationship("Rule", back_populates="metric", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="metric", cascade="all, delete-orphan")
    subscriptions: Mapped[List["Subscription"]] = relationship("Subscription", back_populates="metric", cascade="all, delete-orphan")
    data_points: Mapped[List["MetricData"]] = relationship("MetricData", back_populates="metric", cascade="all, delete-orphan")


class MetricData(Base):
    __tablename__ = "metric_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    metric: Mapped["Metric"] = relationship("Metric", back_populates="data_points")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(SQLEnum(RuleType), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    secondary_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    consecutive_count: Mapped[int] = mapped_column(Integer, default=1)
    alert_level: Mapped[AlertLevel] = mapped_column(SQLEnum(AlertLevel), default=AlertLevel.WARNING)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    metric: Mapped["Metric"] = relationship("Metric", back_populates="rules")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("rules.id"), nullable=False)
    level: Mapped[AlertLevel] = mapped_column(SQLEnum(AlertLevel), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    expected_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    deviation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    metric: Mapped["Metric"] = relationship("Metric", back_populates="alerts")
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="alert", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    subscriber: Mapped[str] = mapped_column(String(100), nullable=False)
    subscriber_email: Mapped[str] = mapped_column(String(100), nullable=False)
    notify_on_alert: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_recovery: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_acknowledge: Mapped[bool] = mapped_column(Boolean, default=False)
    silent_hours_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    silent_hours_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    metric: Mapped["Metric"] = relationship("Metric", back_populates="subscriptions")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    impact_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    alert: Mapped["Alert"] = relationship("Alert", back_populates="reviews")


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_line: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    week_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_alerts: Mapped[int] = mapped_column(Integer, default=0)
    critical_alerts: Mapped[int] = mapped_column(Integer, default=0)
    warning_alerts: Mapped[int] = mapped_column(Integer, default=0)
    resolved_alerts: Mapped[int] = mapped_column(Integer, default=0)
    avg_resolution_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)