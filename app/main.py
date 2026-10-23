"""Application entry point for export‑viewer‑service.
Provides a FastAPI app with a simple /health endpoint.
"""

from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

