import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router
from app.api.v1.streaming import router as streaming_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())


app = FastAPI(
    title="CausalStream Backend Service",
    version="0.1.0",
    description="Public REST API for CausalStream sessions, caption history, and AI service status.",
)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(streaming_router)
