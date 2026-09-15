from fastapi import APIRouter

from .deploy import DeployOpsRouter

ops_router = APIRouter(prefix="/ops")
ops_router.include_router(DeployOpsRouter)
