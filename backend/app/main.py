"""FastAPI entry point. Placeholder until T014 builds the real app (routers, errors, health)."""

from fastapi import FastAPI

app = FastAPI(
    title="Rental Marketplace API",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)
