"""
Dashboard server — serves the single-page UI and proxies API calls to the backend.
"""

import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


@app.get("/api/{path:path}")
async def proxy_api(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BACKEND_URL}/api/{path}",
            params=dict(request.query_params),
        )
    return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_ui(full_path: str):
    with open("/app/index.html") as f:
        return f.read()
