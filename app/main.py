from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import init_db
from app.scheduler import setup_scheduler, shutdown_scheduler
from app.routers import (
    metrics_router,
    rules_router,
    alerts_router,
    subscriptions_router,
    reports_router,
    notifications_router,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    setup_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 指标监控后端服务

为经营分析人员和业务负责人提供关键指标持续跟踪能力。

### 核心功能

- **指标管理**: 注册收入、转化、留存、库存等指标，定义口径说明
- **规则配置**: 支持日环比、周同比、固定上下限、连续异常等监控规则
- **异常检测**: 实时检测指标异常，返回异常级别、影响时间段
- **告警管理**: 告警确认、静默、恢复通知
- **订阅通知**: 负责人订阅、静默时段配置
- **复盘记录**: 原因备注、经验总结
- **周报生成**: 按业务线生成监控周报

### 指标类型

- `revenue`: 收入类指标
- `conversion`: 转化类指标
- `retention`: 留存类指标
- `inventory`: 库存类指标
- `custom`: 自定义指标

### 监控规则类型

- `day_over_day`: 日环比监控
- `week_over_week`: 周同比监控
- `fixed_upper_limit`: 固定上限监控
- `fixed_lower_limit`: 固定下限监控
- `consecutive_anomaly`: 连续异常监控
    """,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}