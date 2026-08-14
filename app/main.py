from fastapi import FastAPI

from app.exception_handlers import register_exception_handlers
from app.routers import api_router

app = FastAPI(
    title="Research Paper API",
    version="0.1.0",
)
register_exception_handlers(app)
app.include_router(api_router)
