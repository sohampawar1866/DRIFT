# DRIFT: System Endpoints & Routes

This document outlines the API contracts / endpoints exposed by the **FastAPI Backend** and the navigational routes expected in the **React Frontend**. It serves as a unified reference for the whole team to integrate frontend UI elements with backend ML predictions.

---

## 🛠 Backend API Endpoints (FastAPI)

Base URL for local development: `http://localhost:8000`
All backend routes return `application/json` unless specified otherwise.

### 1. Metadata / Configuration
*   **`GET /api/v1/aois`**
    *   **Purpose:** Returns the pre-staged Areas of Interest (AOIs) available for the demo.
    *   **Payload:** List of objects containing `id`, `name`, `center` coordinates, and `bounds`.
    *   **Frontend Usage:** Use to populate the main region-selection dropdown and instantly set the bounding box of the map.

### 2. Detection & ML Core
*   **`GET /api/v1/detect?aoi_id={string}`**
    *   **Purpose:** Returns the sub-pixel plastic detection polygons for the selected region.
    *   *Note on Data Strategy:* This route implements a clever AWS STAC + Local Caching strategy. It dynamically queries the live Sentinel-2 cloud catalog (STAC) using a mapped Bounding Box (bbox) based on the `aoi_id`. 
        *   **Hit 1:** Downloads the newest bands straight from the AWS S3 URL bucket to the local drive (`backend/data/cache/` folder) and begins processing.
        *   **Hit 2/N:** Detects we already have the latest image ID cached locally, bypasses the web entirely, and instantly returns processing using the local copy.
        *   **Fallback:** If the internet dies mid-demo, it skips STAC and gracefully loads the most recent stored image chunk from `backend/data/cache/`.
    *   **Payload:** GeoJSON FeatureCollection of polygons with properties `id`, `confidence`, `area_sq_meters`, `age_days`.
    *   **Frontend Usage:** Add as a GeoJSON source to Mapbox/Leaflet to overlay the patches on top of the satellite tiles.

*   **`GET /api/v1/forecast?aoi_id={string}&hours={24|48|72}`**
    *   **Purpose:** Returns predicted adrift positions of the detected patches after 24, 48, or 72 hours using current/wind data.
    *   **Payload:** GeoJSON FeatureCollection of the drifted polygons.
    *   **Frontend Usage:** Render these points as a Mapbox **Heatmap layer** (`type: 'heatmap'`) and switch between them when the user scrubs the UI time slider.

### 3. Dashboard Metrics
*   **`GET /api/v1/dashboard/metrics?aoi_id={string}`**
    *   **Purpose:** Delivers aggregated figures for the dashboard side-panels.
    *   **Payload:** JSON object with `summary` (total area, patch count, average confidence) and `biofouling_chart_data`.
    *   **Frontend Usage:** Feed this data directly into Recharts/Chart.js to render the "Confidence vs Age" curve.

### 4. Cleanup Mission Planning
*   **`GET /api/v1/mission?aoi_id={string}`**
    *   **Purpose:** Calculates the optimal cleanup route (Traveling Salesperson Problem) connecting the densest patches.
    *   **Payload:** A GeoJSON `LineString` connecting target hotspots.
    *   **Frontend Usage:** Render as a solid line layer on the map to visualize the vessel's journey.

*   **`GET /api/v1/mission/export?aoi_id={string}&format=gpx`**
    *   **Purpose:** Generates a physical `.gpx` XML file of the mission waypoints.
    *   **Payload:** Raw `application/gpx+xml` string trigger.
    *   **Frontend Usage:** Bind to the "Export Mission" Coast Guard button to trigger an immediate browser file download.

---

## 💻 Frontend Client Routes (React)

These are the Browser URL paths the React application (e.g., using `react-router-dom`) should handle to provide different views to the user.

### 1. The Main Map Dashboard
*   **Path:** `/`
    *   **View:** The overarching global map. Prompts the user to select an Area of Interest (AOI) from the sidebar. No heavy data loading yet.

### 2. Region-Specific Ops Dashboard (The "Meat" of the app)
*   **Path:** `/aoi/:aoi_id` (e.g., `/aoi/mumbai`)
    *   **View:**
        *   Map automatically pans/zooms to the AOI bounds.
        *   Fires `GET /api/v1/detect` and displays detection overlays.
        *   Fires `GET /api/v1/dashboard/metrics` and populates the charts on the left sidebar.
        *   Bottom of the screen renders a Time Slider (0h ➔ 24h ➔ 48h ➔ 72h). Scrubbing the slider requests `GET /api/v1/forecast` and updates the Heatmap layer.

### 3. Mission Briefing View
*   **Path:** `/mission/:aoi_id`
    *   **View:** Focuses solely on the generated route from `GET /api/v1/mission`.
    *   Hides all complex chart clutter.
    *   Shows a clear panel with Waypoint distances, total estimated maritime journey time, and the large green "Export GPX to Vessel" button.

---

*This document ensures the Frontend developer and Backend data flow stay perfectly aligned.*