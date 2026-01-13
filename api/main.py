"""
Charm Email OS API - FastAPI Application

Main entry point for the API server.
Connects Charm Email OS frontend to OwnRBL PostgreSQL database.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from config import settings
import database

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    logger.info("Starting Charm Email OS API...")
    await database.create_pool()
    logger.info("Database pool initialized")

    yield

    # Shutdown
    logger.info("Shutting down Charm Email OS API...")
    await database.close_pool()
    logger.info("Database pool closed")


# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API for Charm Email OS - connects to OwnRBL database",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Import and include routers
from routes import workspaces, clients, domains, inboxes, campaigns, leads, health

app.include_router(workspaces.router, prefix=f"{settings.API_PREFIX}/workspaces", tags=["workspaces"])
app.include_router(clients.router, prefix=f"{settings.API_PREFIX}/clients", tags=["clients"])
app.include_router(domains.router, prefix=f"{settings.API_PREFIX}/domains", tags=["domains"])
app.include_router(inboxes.router, prefix=f"{settings.API_PREFIX}/inboxes", tags=["inboxes"])
app.include_router(campaigns.router, prefix=f"{settings.API_PREFIX}/campaigns", tags=["campaigns"])
app.include_router(leads.router, prefix=f"{settings.API_PREFIX}/leads", tags=["leads"])
app.include_router(health.router, prefix=f"{settings.API_PREFIX}/health", tags=["health"])


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_healthy = await database.health_check()
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "database": "connected" if db_healthy else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
