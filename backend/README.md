# DRIFT Backend Setup and Operations

This guide is for the backend intelligence layer only: ML detection, drift forecast, mission planning, and mission export.

## 1) Requirements

- Python available as `python`
# DRIFT Backend Setup and Operations

This guide is for the backend intelligence layer only: ML detection, drift forecast, mission planning, and mission export.

## 1) Requirements

- Python available as `python`
- `pip` available as `python -m pip`

Repo constraint: backend targets Python `>=3.11,<3.13`.

## 2) Setup on Mac

Run from repo root:

```bash
cd /path/to/DRIFT
python -m venv backend/venv
source backend/venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r backend/requirements.txt
```

Note for Mac only:
- if geospatial wheels fail during install, use a Python 3.11/3.12 interpreter and recreate the venv.

## 3) Setup on Windows

Run from repo root in PowerShell:

```powershell
cd C:\path\to\DRIFT
python -m venv backend\venv
.\backend\venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r backend\requirements.txt
```

## 4) Run backend API

From repo root:

```bash
source backend/venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
.\backend\venv\Scripts\activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: `http://localhost:8000/docs`
- Health endpoint: `GET /`

## 5) Runtime modes

Default mode is demo-safe and allows mock fallback when real data/ML is unavailable.

- Force mock: `DRIFT_FORCE_MOCK=1`
- Strict mode (disable silent fallback):
  - `DRIFT_STRICT_MODE=1`
  - or `DRIFT_DISABLE_FALLBACKS=1`

Example strict run:

```bash
DRIFT_STRICT_MODE=1 uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 6) Data prerequisites for real chain

For true non-mock behavior:

- model checkpoint for real weights:
  - place the file inside `backend/ml/checkpoints/`
  - accepted filenames: `our_real.pt` or `our_real.pth` or `our_real.pkl`
  - set `ml.weights_source: our_real` in `backend/config.yaml`
- expected save format: `torch.save(model.state_dict(), path)`
- MARIDA dataset under `DRIFT/MARIDA` (patches and splits)
- optional physics NetCDF files:
  - `data/env/cmems_currents_72h.nc`
  - `data/env/era5_winds_72h.nc`

If env files are missing, forecast uses synthetic currents (schema-valid, less realistic).

## 7) Validation

Run from repo root with backend venv active:

```bash
python -m pytest -q backend/e2e_test.py
python -m pytest -q backend/tests
```

Targeted suites:

```bash
python -m pytest -q backend/tests/integration/test_inference_dummy.py
python -m pytest -q backend/tests/integration/test_tracker_synth.py
python -m pytest -q backend/tests/integration/test_planner_synth.py
```

Some tests are skipped when required data (for example MARIDA patches) is unavailable.

## 8) Chain runners

Dummy chain:

```bash
python scripts/run_full_chain_dummy.py --use-synth-env
```

Real chain (strict, no fallback):

```bash
python scripts/run_full_chain_real.py \
  --tile /absolute/path/to/tile.tif \
  --aoi gulf_of_mannar \
  --origin 78.9 9.2 \
  --no-fallback
```
Dummy chain:

```bash
python scripts/run_full_chain_dummy.py --use-synth-env
```

Real chain (strict, no fallback):

```bash
python scripts/run_full_chain_real.py \
  --tile /absolute/path/to/tile.tif \
  --aoi gulf_of_mannar \
  --origin 78.9 9.2 \
  --no-fallback
```
