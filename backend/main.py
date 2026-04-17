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


@app.on_event("startup")
async def startup_event():
    import logging
    import os
    from backend.core.config import Settings
    
    logger = logging.getLogger("backend.startup")
    cfg = Settings()
    
    logger.info("[SYSTEM] OCEANTRACE STARTUP INITIALIZED")
    
    # 1. Verify Environmental Data (Physics)
    if cfg.physics.cmems_path.exists():
        logger.info(f"[PHYSICS] CMEMS Data Found ({cfg.physics.cmems_path.name})")
    else:
        logger.warning(f"[PHYSICS] CMEMS Data Missing! ({cfg.physics.cmems_path})")
        
    if cfg.physics.era5_path.exists():
        logger.info(f"[PHYSICS] ERA5 Data Found ({cfg.physics.era5_path.name})")
    else:
        logger.warning(f"[PHYSICS] ERA5 Data Missing! ({cfg.physics.era5_path})")

    # 2. Verify Credentials (Masked)
    logger.info("[SECURITY] Credential Strings Verification:")
    for key, val in os.environ.items():
        if "API" in key or "SECRET" in key or "KEY" in key:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            logger.info(f"   - {key}: {masked}")

    logger.info("OceanTrace is mission-ready.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
