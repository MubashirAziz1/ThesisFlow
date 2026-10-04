import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI


from app.gateway.routers import run_thread
from packages.harness.thesisflow.config.app_config import get_app_config


# Default logging; lifespan overrides from config.yaml log_level.
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""

    # Startup
    logger.info("ThesisFlow- Material Scientist Assistant - Server Starting")
    try:
        application_config = get_app_config()
        app.state.app_config = application_config
        logger.info("Shared App Configuration loaded Successfully.")

    except Exception as e:
        error_msg = f"Failed to load shared app_configuration during startup: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e
    
    logger.info("Ready to accept requests")

    yield

    # Shutdown
    logger.info("Server shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """

    app = FastAPI(
        title="ThesisFlow API Gateway",
        description="""
        ## ThesisFlow API Gateway

        API Gateway for ThesisFlow - A LangGraph-based AI agent backend with capabilities to orchestrate among three subagents.

        - **Skills Management**: Query and manage skills and their enabled status
        - **Artifacts**: Access thread artifacts and generated files
        - **Health Monitoring**: System health check endpoints

        ### Architecture

        LangGraph-compatible requests are routed through nginx to this gateway.
        This gateway provides runtime endpoints for agent runs plus custom endpoints for models, MCP configuration, skills, and artifacts.
            """,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(run_thread.router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Service health status information.
        """
        return {"status": "healthy", "service": "thesis-flow-gateway"}

    return app

# Create app instance for uvicorn
app = create_app()