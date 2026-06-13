from app.routers.metrics import router as metrics_router
from app.routers.rules import router as rules_router
from app.routers.alerts import router as alerts_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.reports import router as reports_router

__all__ = [
    "metrics_router",
    "rules_router",
    "alerts_router",
    "subscriptions_router",
    "reports_router",
]