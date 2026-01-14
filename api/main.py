"""
Minimal FastAPI test - no external dependencies
"""
from fastapi import FastAPI

app = FastAPI(title="Charm API Test")

@app.get("/")
async def root():
    return {"status": "running", "message": "minimal test"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
