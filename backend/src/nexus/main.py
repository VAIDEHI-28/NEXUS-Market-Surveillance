
from fastapi import FastAPI

app = FastAPI(
    title="NEXUS Market Surveillance Engine",
    description="An explainable engine for detecting market anomalies.",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "nexus-backend",
        "version": "0.1.0",
    }
