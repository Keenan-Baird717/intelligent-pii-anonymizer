from fastapi import APIRouter

from app.api.v1 import analyze, anonymize, documents, health, jobs

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(analyze.router, tags=["analyze"])
api_v1_router.include_router(anonymize.router, tags=["anonymize"])
api_v1_router.include_router(documents.router, tags=["documents"])
api_v1_router.include_router(jobs.router, tags=["jobs"])
