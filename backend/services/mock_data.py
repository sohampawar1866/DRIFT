import random

def get_mock_aois():
    """
    Returns a list of available pre-staged regions for the frontend dropdown.
    """
    return {
        "aois": [
            {
                "id": "mumbai",
                "name": "Mumbai Offshore",
                "center": [72.85, 18.95],
                "bounds": [[72.7, 18.8], [73.0, 19.1]]
            },
            {
                "id": "gulf_of_mannar",
                "name": "Gulf of Mannar",
                "center": [79.05, 8.85],
                "bounds": [[78.6, 8.5], [79.5, 9.2]]
            },
            {
                "id": "chennai",
                "name": "Chennai Coast",
                "center": [80.35, 13.0],
                "bounds": [[80.2, 12.8], [80.5, 13.2]]
            },
            {
                "id": "andaman",
                "name": "Andaman Islands",
                "center": [92.75, 11.75],
                "bounds": [[92.5, 11.5], [93.0, 12.0]]
            }
        ]
    }

def get_mock_detection_geojson(aoi_id: str):
    """
    Returns mock sub-pixel plastic detection polygons.
    """
    # Coordinates for Mumbai offshore area
    base_lon, base_lat = 72.85, 18.95
    
    if aoi_id and aoi_id.startswith("custom_"):
        parts = aoi_id.split("_")
        if len(parts) == 3:
            try:
                base_lon, base_lat = float(parts[1]), float(parts[2])
            except ValueError:
                pass
    else:
        # Match with get_mock_aois
        aois = get_mock_aois()["aois"]
        for aoi in aois:
            if aoi["id"] == aoi_id:
                base_lon, base_lat = aoi["center"]
                break
    
    features = []
    # Generate 5 random "plastic clusters"
    for i in range(5):
        lon = base_lon - random.uniform(-0.1, 0.1)
        lat = base_lat + random.uniform(-0.1, 0.1)
        # Small polygon representing some macroplastic
        polygon = [
            [lon, lat],
            [lon + 0.005, lat + 0.002],
            [lon + 0.004, lat - 0.003],
            [lon - 0.001, lat - 0.004],
            [lon, lat]
        ]
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon]
            },
            "properties": {
                "id": f"patch_{i}",
                "confidence": round(random.uniform(0.5, 0.95), 2),
                "area_sq_meters": round(random.uniform(15, 100), 2),
                "age_days": random.randint(1, 40),
                "type": "macroplastic",
                "water_temp": round(random.uniform(24.0, 31.0), 1),
                "chlorophyll": round(random.uniform(0.1, 1.5), 2),
                "k": round(random.uniform(0.01, 0.05), 3)
            }
        }
        features.append(feature)
        
    return {
        "type": "FeatureCollection",
        "features": features
    }


def get_mock_forecast_geojson(aoi_id: str, hours: int):
    """
    Simulates where the plastic has drifted based on a time delta.
    """
    detect_base = get_mock_detection_geojson(aoi_id)
    
    # Simple fake drift: move east & south slightly based on hours
    drift_lon_per_hour = -0.001
    drift_lat_per_hour = -0.0005
    
    for f in detect_base["features"]:
        coords = f["geometry"]["coordinates"][0]
        drifted_coords = [
            [c[0] + (drift_lon_per_hour * hours), c[1] + (drift_lat_per_hour * hours)]
            for c in coords
        ]
        f["geometry"]["coordinates"] = [drifted_coords]
        f["properties"]["forecast_hour"] = hours
        
    return detect_base


def get_mock_mission_geojson(aoi_id: str):
    """
    Returns an optimal route connecting the top patches.
    """
    detect_base = get_mock_detection_geojson(aoi_id)
    
    # Just take the first coordinate of each feature to make a path
    waypoints = []
    for f in detect_base["features"][:4]:  # Top 4 targets
        center = f["geometry"]["coordinates"][0][0] # rough center
        waypoints.append(center)
        
    line_feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": waypoints
        },
        "properties": {
            "mission_id": "OP_CLEAN_ALPHA",
            "estimated_vessel_time_hours": round(random.uniform(2, 6), 1),
            "priority": "HIGH"
        }
    }
    
    return {
        "type": "FeatureCollection",
        "features": [line_feature]
    }


def get_mock_dashboard_metrics(aoi_id: str):
    """
    Returns aggregated stats and chart data for the UI side panels.
    Specifically powering the Biofouling Confidence vs Age chart described in PRD.
    """
    return {
        "summary": {
            "total_area_sq_meters": random.randint(150, 500),
            "total_patches": random.randint(5, 12),
            "avg_confidence": round(random.uniform(0.70, 0.88), 2),
            "high_priority_targets": random.randint(2, 4)
        },
        "biofouling_chart_data": [
            {"age_days": 1, "simulated_confidence": 0.95},
            {"age_days": 5, "simulated_confidence": 0.88},
            {"age_days": 15, "simulated_confidence": 0.70},
            {"age_days": 30, "simulated_confidence": 0.50},
            {"age_days": 40, "simulated_confidence": 0.40}
        ]
    }
