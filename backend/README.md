# DRIFT: Backend API Reference and Setup Guide

This document is dedicated to helping anyone on the team get the backend API running on their device, whether it is Mac, Windows, or Linux, without compilation headaches.

## 🛑 Critical Prerequisite: Python Version
The backend relies on `geopandas` and `shapely` for fast geospatial processing. These libraries require C-compilers to build from source **unless** you are on a stable, mainstream Python version.

**DO NOT USE Python 3.13 or 3.14+ yet.** Pre-built binary wheels are not yet stable for these alpha/beta versions for all geospatial packages, which will throw a "Failed to build shapely wheel" error.

*   ✅ **Recommended:** Python 3.10, 3.11, or 3.12 (e.g., Python 3.11.9)
*   ❌ **Don't use:** Python 3.9 (too old for some typing), Python 3.13/3.14 (too new, no precompiled wheels yet).

---

## 💻 1. Quick Setup for Mac / Linux Users

Open your terminal and run these step-by-step:

```bash
# 1. Navigate to the backend folder
cd path/to/DRIFT/backend

# 2. Create the virtual environment using a stable python version
python3.12 -m venv venv

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Install dependencies (pip will fetch pre-compiled wheels for shapely automatically)
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 5. Start the API server
uvicorn main:app --reload
```

---

## 🪟 2. Quick Setup for Windows Users

PowerShell or Command Prompt commands:

```powershell
# 1. Navigate to the backend folder
cd path\to\DRIFT\backend

# 2. Create the virtual environment using your stable python installation
python -m venv venv

# 3. Activate the virtual environment
# Note: If you get an ExecutionPolicy error, run: Set-ExecutionPolicy Unrestricted -Scope CurrentUser
.\venv\Scripts\activate

# 4. Install dependencies
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 5. Start the API server
uvicorn main:app --reload
```

---

### Alternative for Windows: Using Conda (If pip fails)
Windows can sometimes still struggle with geospatial dependencies like GDAL, Fiona (nested inside Geopandas) and Shapely. If `pip install -r requirements.txt` fails, **use Conda** (Miniconda or Anaconda):

```bash
# Creates an entirely isolated python 3.11 environment with conda
conda create -n drift_env python=3.11
conda activate drift_env

# Install geopandas through conda explicitly, allowing it to handle all C-dependencies
conda install -c conda-forge geopandas shapely

# Install the rest
pip install fastapi uvicorn pydantic pydantic-settings
```

---

## 🌐 3. Usage & Access

Once `uvicorn` claims the application startup is complete, open your browser and head to:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

This is the interactive Swagger UI where you can immediately test the endpoints:
*   `GET /api/v1/detect`
*   `GET /api/v1/forecast`
*   `GET /api/v1/mission`

**Troubleshooting**:
*   *React Frontend gets blocked by CORS?* Ensure the FastAPI settings in `main.py` explicitly allow all origins (`allow_origins=["*"]`) for local development, which is already configured in the skeleton.

---

## 🛰 4. Understanding How Live Satellite Ingestion Works

Our system uses **AWS Open Data (STAC API)** to fetch Sentinel-2 imagery. We've built an intelligent **Caching Strategy** to protect us on hackathon demo day:

1.  **Frontend Input:** The user clicks a region on the UI (e.g., "Gulf of Mannar"). The frontend simply sends an `aoi_id` via the URL (`/api/v1/detect?aoi_id=gulf_of_mannar`).
2.  **AOI to Bounding Box:** Our backend receives this string. It holds an internal dictionary mapping `gulf_of_mannar` to a hidden geographic coordinates box: `[78.6, 8.5, 79.5, 9.2]`. Essentially, `[Min_Longitude, Min_Latitude, Max_Longitude, Max_Latitude]`.
3.  **STAC API Query:** We send that invisible boundary box to the Earth Search STAC API and ask: *"Provide the metadata for the newest low-cloud image overlapping this box"*
4.  **The Cache Strategy**:
    *   **First Run (or new data available):** We look in `backend/data/cache/<aoi_id>`. If we don't have the files for the newest ID, we fetch the large raw `.tif` bands from AWS S3, save them in the cache folder, and hand them to the AI model.
    *   **Subsequent Runs:** We query STAC, but notice we already downloaded those specific images previously. We skip downloading entirely and feed the local files straight into the AI model, making the route incredibly fast.
    *   **No Internet Emergency:** If the STAC API times out (no Wi-Fi during pitching), our code drops into a **Fallback Mode**, silently grabs the newest files existing in the local cache, and runs the AI pipeline on those. Your demo won't crash!