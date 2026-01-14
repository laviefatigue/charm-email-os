"""
Charm Email OS API - Minimal Working Version
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Charm Email OS API",
    version="1.0.0",
    description="API for Charm Email OS - minimal version"
)

# CORS - allow all origins for now
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": "Charm Email OS API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "not_configured",
    }


@app.get("/api/clients")
async def list_clients():
    """List clients - returns empty list for now"""
    return {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }


@app.get("/api/workspaces")
async def list_workspaces():
    """List workspaces - returns empty list for now"""
    return {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
