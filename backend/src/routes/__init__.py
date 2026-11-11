"""路由总装配。"""
from fastapi import APIRouter

from src.routes import audit, auth, event, health, meta, rejected, run, schema, stream

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(meta.router)
api_router.include_router(stream.router)
api_router.include_router(event.router)
api_router.include_router(run.router)
api_router.include_router(schema.router)
api_router.include_router(rejected.router)
api_router.include_router(audit.router)

__all__ = ["api_router"]
