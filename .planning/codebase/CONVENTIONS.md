# Coding Conventions

**Analysis Date:** 2026-04-17

## Naming Patterns

**Files:**
- Modules: lowercase with underscores (`main.py`, `mock_data.py`, `routes.py`)
- Packages: lowercase directories (`api/`, `services/`)

**Functions:**
- lowercase with underscores: `get_mock_detection_geojson()`, `get_mock_forecast_geojson()`, `get_mock_mission_geojson()`
- Async handlers: `async def detect_plastic()`, `async def forecast_drift()`, `async def plan_mission()`

**Variables:**
- lowercase snake_case: `aoi_id`, `hours`, `base_lon`, `base_lat`, `drift_lon_per_hour`
- Constants in capitalized patterns where needed (not yet observed in codebase)

**Types & Classes:**
- Not yet used in current codebase (minimal scope); will follow PascalCase when introduced (standard Python convention)

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `black.toml`, or `setup.cfg`)
- Follows PEP 8 conventions informally (indentation, spacing)
- 4-space indentation observed

**Linting:**
- No linting tools configured (no `.pylintrc`, `.flake8`)
- No lint checks enforced in CI/CD

## Import Organization

**Order:**
1. Standard library imports (`import random`)
2. Third-party imports (`from fastapi import ...`, `import uvicorn`, `from fastapi.middleware.cors import CORSMiddleware`)
3. Local imports (`from api.routes import router`, `from services.mock_data import ...`)

**Style:**
- Explicit imports from modules (not `import *`)
- Blank line between stdlib and third-party groups
- Relative imports within package (e.g., `from services.mock_data import ...` in `backend/api/routes.py`)
- Example from `backend/api/routes.py` (lines 1–6):
  ```python
  from fastapi import APIRouter
  from services.mock_data import (
      get_mock_detection_geojson,
      get_mock_forecast_geojson,
      get_mock_mission_geojson
  )
  ```

**Path Aliases:**
- Not used yet; all imports are relative to package root

## Error Handling

**Current Pattern (Non-idiomatic):**
- Inline dict-based error returns: `return {"error": "Invalid forecast step. Allowed values are [24, 48, 72]."}`
  - Location: `backend/api/routes.py` line 23
  - Problem: FastAPI best practice is to use `HTTPException` with proper status codes
  - Should be flagged as quality concern for later refactor

**Recommended Pattern (when refactoring):**
```python
from fastapi import HTTPException

@router.get("/forecast")
async def forecast_drift(aoi_id: str = "mumbai", hours: int = 24):
    if hours not in [24, 48, 72]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid forecast step. Allowed values are [24, 48, 72]."
        )
    return get_mock_forecast_geojson(aoi_id, hours)
```

## Logging

**Framework:** Not yet implemented; no logging observed
- Default: standard library `logging` module would be idiomatic
- Current approach: silent operation (GeoJSON returned directly)

## Comments

**When to Comment:**
- Docstrings on all endpoint handlers (observed pattern):
  - Triple-quoted strings immediately inside async handler
  - Example from `backend/api/routes.py` (lines 10–14):
    ```python
    @router.get("/detect")
    async def detect_plastic(aoi_id: str = "mumbai"):
        """
        Returns the sub-pixel plastic detection polygons for a pre-staged Area of Interest (AOI).
        """
        return get_mock_detection_geojson(aoi_id)
    ```
  - Service functions include docstrings explaining their purpose
  - Inline comments for non-obvious logic (e.g., "Small polygon representing some macroplastic" in `backend/services/mock_data.py` line 15)

**JSDoc/TSDoc:**
- Not applicable (Python codebase, not TypeScript)

## Function Design

**Size:**
- Functions are small and focused
- Example: `get_mock_detection_geojson()` (43 lines) — generates feature collection
- Example: `get_mock_forecast_geojson()` (19 lines) — applies drift transformation
- Example: `get_mock_mission_geojson()` (29 lines) — computes route

**Parameters:**
- Explicit, named parameters with defaults
- Example: `async def forecast_drift(aoi_id: str = "mumbai", hours: int = 24)`
- Type hints used (str, int)

**Return Values:**
- GeoJSON dict structure (FeatureCollection):
  ```python
  {
      "type": "FeatureCollection",
      "features": [...]
  }
  ```
- Error responses: dict with "error" key (to be refactored to HTTPException)

## Module Design

**Exports:**
- Explicit function exports from `backend/services/mock_data.py`
- Router pattern in `backend/api/routes.py`:
  ```python
  router = APIRouter(prefix="/api/v1")
  ```
  - All route handlers attached to router object
  - Router imported and included in main app: `app.include_router(router)`

**Barrel Files:**
- Not used; codebase is minimal (no index.py or `__init__.py` exports observed)

## Architecture Patterns

**Layering:**
1. **Entry point** — `backend/main.py`: FastAPI app setup, CORS middleware, router inclusion
2. **Routes layer** — `backend/api/routes.py`: endpoint handlers (async, with docstrings, validation)
3. **Services layer** — `backend/services/mock_data.py`: business logic (mock data generators)

**Key Convention:**
- **Endpoint handlers do NO business logic** — they call service functions
- Example: `async def detect_plastic()` calls `get_mock_detection_geojson(aoi_id)` and returns result directly
- This separates concerns and makes testing easier (when tests are added)

## Middleware & Infrastructure

**CORS Configuration:**
- Middleware pattern in `backend/main.py` (lines 14–20):
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
- Rationale: "Crucial to unblock the frontend React dev" (inline comment, line 13)
- Note: Permissive for local dev; should be restricted for production

**App Configuration:**
- FastAPI metadata: title, description, version (lines 7–11 in `backend/main.py`)
  ```python
  app = FastAPI(
      title="DRIFT API",
      description="Debris Recognition, Imaging & Forecast Trajectory API",
      version="1.0.0"
  )
  ```

---

*Convention analysis: 2026-04-17*
