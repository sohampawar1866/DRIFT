# Testing Patterns

**Analysis Date:** 2026-04-17

## Current State

**NO TESTS EXIST in the codebase.** No test files, no pytest configuration, no test fixtures. This is a critical gap flagged for Phase 3 implementation per the PRD roadmap.

## Test Framework (Planned)

**Runner:**
- Framework: `pytest` (not yet in `backend/requirements.txt`)
- Config file: `backend/pytest.ini` (not yet created)

**Assertion Library:**
- Standard: `pytest` built-in assertions + custom fixtures

**Run Commands (to be added):**
```bash
pytest                         # Run all tests
pytest -v                      # Verbose output
pytest --cov                   # Coverage report
pytest -k "test_feature"       # Run specific test subset
pytest -x                      # Stop on first failure
pytest --tb=short              # Shorter traceback
```

## Planned Test Structure (From PRD §15)

Per PRD.md (§15 "Verification Plan"), testing follows a 5-level hierarchy:

### 1. Unit-Level Tests

**Features module** (`backend/ml/features.py` — to be built in Phase 2):
- Test FDI computation against paper example
- Input: pixel spectrum from Biermann et al. 2020
- Output: FDI value matches known result
- Reason: FDI is critical discriminator for plastic vs. Sargassum

**Tracker module** (`backend/physics/tracker.py` — to be built in Phase 2):
- Test synthetic drift check
- Input: uniform eastward current field (0.5 m/s), 24-hour integration
- Expected output: particle displacement of 43.2 km (±1%)
- Reason: validates Euler integrator correctness

**Example structure (pseudo-code):**
```python
def test_fdi_computation():
    """Test FDI against Biermann et al. 2020 paper example."""
    # Known pixel spectrum from paper
    ρ_NIR = 0.15
    ρ_RE2 = 0.08
    ρ_SWIR1 = 0.05
    
    fdi = compute_fdi(ρ_NIR, ρ_RE2, ρ_SWIR1)
    
    assert abs(fdi - EXPECTED_FDI_FROM_PAPER) < 0.001

def test_tracker_drift_synthetic():
    """Test Lagrangian drift with synthetic eastward current."""
    particle = Particle(x=0.0, y=0.0)
    current_field = SyntheticField(u=0.5, v=0.0)  # 0.5 m/s east
    
    for hour in range(24):
        particle.step(current_field, dt_seconds=3600)
    
    # 0.5 m/s * 86400 sec = 43200 m = 43.2 km
    expected_displacement = 43.2e3  # meters
    actual = haversine(particle.x, particle.y, 0.0, 0.0)
    
    assert abs(actual - expected_displacement) / expected_displacement < 0.01
```

### 2. Model-Level Tests

**Detection model** (`backend/ml/model.py` and `backend/ml/train.py` — Phase 2):
- Held-out MARIDA validation split
- Metric: **IoU ≥ 0.45** (intersection over union on plastic detection)
- Metric: **Precision ≥ 0.75** at confidence threshold > 0.7
- Metric: **Sargassum FPR < 15%** (false positive rate on Sargassum confused as plastic)
- Reason: validates model discriminates plastic from natural matter

**Sub-pixel fraction regression head:**
- Metric: **MAE ≤ 0.15** (mean absolute error on fractional cover)
- Test against synthetic mixed-pixel labels
- Reason: ensures sub-pixel quantification is calibrated

**Example structure:**
```python
def test_model_iou_on_marida_val():
    """Model achieves IoU >= 0.45 on held-out MARIDA validation split."""
    model = load_trained_model("weights/best_model.pth")
    val_loader = MaridaValDataset(split="val")
    
    metrics = evaluate_model(model, val_loader)
    
    assert metrics["iou"] >= 0.45
    assert metrics["precision_at_07"] >= 0.75
    assert metrics["sargassum_fpr"] < 0.15
```

### 3. Pipeline-Level Tests (curl assertions)

**Detection endpoint** (`backend/api/routes.py` → `/api/v1/detect`):
```bash
curl http://localhost:8000/api/v1/detect?aoi=gulf_of_mannar
```
Assertions:
- HTTP 200 response
- Response is valid GeoJSON FeatureCollection
- Features array has ≥1 members
- Each feature has required properties: `conf_raw`, `conf_adj`, `fraction_plastic`, `area_m2`, `age_days_est`, `class`

**Forecast endpoint** (`backend/api/routes.py` → `/api/v1/forecast`):
```bash
curl http://localhost:8000/api/v1/forecast?aoi=gulf_of_mannar&hours=72
```
Assertions:
- HTTP 200 response
- Response contains 72 hourly frames (0h, 1h, 2h, ..., 72h)
- Particles bounded within basin (no teleportation)
- Latitude/longitude within valid ranges (-90 to 90, -180 to 180)

**Mission planner endpoint** (`backend/api/routes.py` → `/api/v1/mission`):
```bash
curl http://localhost:8000/api/v1/mission?aoi=gulf_of_mannar
```
Assertions:
- HTTP 200 response
- Response is valid GeoJSON FeatureCollection with 1 LineString feature
- Waypoints array has ≥3 members
- Waypoints are in TSP order (greedy nearest-neighbor, no backtracking)
- GPX export valid (can be parsed by `togpx`)

**Example pytest structure:**
```python
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_detect_endpoint_returns_valid_geojson():
    """GET /detect returns valid GeoJSON FeatureCollection."""
    response = client.get("/api/v1/detect?aoi=gulf_of_mannar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 1
    
    for feature in data["features"]:
        assert feature["type"] == "Feature"
        assert "properties" in feature
        assert "conf_raw" in feature["properties"]
        assert "class" in feature["properties"]

def test_forecast_endpoint_returns_72_frames():
    """GET /forecast returns >=72 hourly frames."""
    response = client.get("/api/v1/forecast?aoi=gulf_of_mannar&hours=72")
    assert response.status_code == 200
    
    data = response.json()
    assert "frames" in data
    assert len(data["frames"]) == 72
    
    for frame in data["frames"]:
        assert "t" in frame
        for particle in frame["particles"]:
            lat, lon = particle["y"], particle["x"]
            assert -90 <= lat <= 90
            assert -180 <= lon <= 180

def test_mission_endpoint_returns_valid_gps():
    """GET /mission returns valid waypoint TSP route."""
    response = client.get("/api/v1/mission?aoi=gulf_of_mannar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    
    feature = data["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    waypoints = feature["geometry"]["coordinates"]
    assert len(waypoints) >= 3
```

### 4. Frontend-Level Tests (Playwright/Cypress — Phase 3)

Dashboard tests (React):
- **FCP (First Contentful Paint):** < 2 seconds
- **Time-slider animation:** ≥ 30 FPS over 72h scrubbing
- **All 4 AOIs load within 3s** each
- **Mission export downloads valid GPX** that opens in Google Earth

### 5. Dress Rehearsal (End-to-End)

- Execute full 5-minute demo flow **3 times** without touching code
- Record final successful run as fallback screen capture
- Verify: landing → AOI select → detection overlay → forecast slider → mission planner → export

## Test Data & Fixtures

**MARIDA Dataset:**
- Source: Kikaki et al. 2022, Marine Debris Archive
- Location: `data/MARIDA/` (downloaded locally, not in repo)
- Split: train (1000 scenes), val (200 scenes), test (100 scenes)
- Labeled pixels: plastic / non-plastic
- Used by: `backend/ml/dataset.py` loader (to be implemented)

**Synthetic Mock Data (Current):**
- Location: `backend/services/mock_data.py`
- Purpose: serve GeoJSON for demo endpoints **during Phase 1–2 while model training**
- Replaced in Phase 3 with real model inference

**Fixture Example (to be added):**
```python
@pytest.fixture
def marida_sample_tile():
    """Load a single MARIDA example tile for unit tests."""
    return load_marida_scene(split="test", scene_id=0)

@pytest.fixture
def synthetic_current_field():
    """Create a synthetic 0.5 m/s eastward current field."""
    def _field(x, y, t):
        return (0.5, 0.0)  # u=0.5 m/s, v=0 m/s
    return _field
```

## Coverage

**Current requirement:** None enforced
**Future target** (Phase 3): ≥80% line coverage on critical modules:
- `backend/ml/model.py`, `backend/ml/features.py`, `backend/physics/tracker.py`
- Non-critical (lower target): UI components, mock data generators

**View Coverage (when pytest-cov added):**
```bash
pytest --cov=backend --cov-report=html
open htmlcov/index.html
```

## Missing Critical Tests

**Priority Gaps (Phase 3 deliverables per PRD §15):**

1. **No unit tests for FDI/physics** — validation of correctness
2. **No model evaluation** — IoU, precision, Sargassum FPR not measured
3. **No API schema tests** — GeoJSON structure not validated
4. **No frontend tests** — FCP, FPS not measured
5. **No integration tests** — end-to-end pipeline not validated

**Risk:** All 5 gaps could cause failures in demo if left untested. Plan to address all in Phase 3 before final rehearsal (PRD §13 H28–H40).

## Test Commands to Add (Phase 3)

```makefile
# Suggested additions to project Makefile or script
test-unit:
	pytest backend/ml/ backend/physics/ -v

test-api:
	pytest backend/api/ -v

test-coverage:
	pytest --cov=backend --cov-report=term-missing --cov-report=html

test-integration:
	pytest backend/tests/integration/ -v

test-all:
	pytest backend/ -v --cov=backend

test-watch:
	pytest-watch backend/ -- -v
```

---

*Testing analysis: 2026-04-17*
