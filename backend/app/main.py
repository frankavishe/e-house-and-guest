"""FastAPI entry point: `/api/v1` routers, error handlers and the health check."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import dispose_engine, get_session
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging

API_PREFIX = "/api/v1"


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "down"]


health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(Health(status="degraded", database="down").model_dump(), 503)
    return JSONResponse(Health(status="ok", database="ok").model_dump())


def api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)
    router.include_router(health_router)
    return router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Rental Marketplace API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(api_router())
    return app


app = create_app()
