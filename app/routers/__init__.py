"""Presentation layer: HTTP routers."""

from fastapi import APIRouter

from app.routers.hello import router as hello_router
from app.routers.papers import router as papers_router

api_router = APIRouter()
api_router.include_router(hello_router)
api_router.include_router(papers_router)
