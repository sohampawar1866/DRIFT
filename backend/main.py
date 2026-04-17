"""FastAPI app entrypoint.

Launch from repo root:

    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

OR:

    python -m backend.main
"""
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Allow `uvicorn main:app` when launched from the `backend` directory.
if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from backend.api.routes import router
from backend.api.tracker_routes import router as tracker_router

app = FastAPI(
    title="DRIFT API",
    description="Debris Recognition, Imaging & Forecast Trajectory API",
    version="1.0.0",
)

# CORS fully permissive for React dev; tighten before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(tracker_router)


@app.get("/")
async def root():
    return {"status": "ok", "app": "DRIFT"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
