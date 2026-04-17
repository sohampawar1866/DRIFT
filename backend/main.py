from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.routes import router
from api.tracker_routes import router as tracker_router

app = FastAPI(
    title="DRIFT API",
    description="Debris Recognition, Imaging & Forecast Trajectory API",
    version="1.0.0"
)

# Crucial to unblock the frontend React dev (allow all origins in dev mode)
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
