"""FastAPI application setup and configuration."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from contact_energy_nz import AuthException
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.database import init_database
from app.routes import accounts, health, usage
from app.services.cache import clear_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    _LOGGER.info("Starting Contact Energy HA Integration API")

    # Initialize database
    await init_database()
    _LOGGER.info("Database initialized")

    # Clear cache on startup
    clear_cache()
    _LOGGER.info("Cache cleared")

    yield

    # Shutdown
    _LOGGER.info("Shutting down Contact Energy HA Integration API")


# Create FastAPI app
app = FastAPI(
    title="Contact Energy Home Assistant Integration",
    description="API for exposing Contact Energy usage data to Home Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(usage.router)


# Exception handlers
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> JSONResponse:
    """Handle Contact Energy authentication errors."""
    _LOGGER.error("Contact Energy authentication failed: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Contact Energy authentication failed. Check credentials."},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors."""
    _LOGGER.exception("Unexpected error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def run() -> None:
    """Run the application with uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
