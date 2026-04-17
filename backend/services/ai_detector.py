from typing import Dict, Any
from services.mock_data import get_mock_detection_geojson
from services.stac_service import get_live_or_cached_imagery

# A simple AOI bounding box local mapping
AOI_BBOX_MAP = {
    "mumbai": [72.7, 18.8, 73.0, 19.1],
    "gulf_of_mannar": [78.6, 8.5, 79.5, 9.2],
    "chennai": [80.2, 12.8, 80.5, 13.2],
    "andaman": [92.5, 11.5, 93.0, 12.0]
}

def detect_macroplastic(aoi_id: str, s2_tile_path: str = None) -> Dict[str, Any]:
    """
    AI TEAM CONTRACT:
    =================
    Input:
      - aoi_id: An identifier for the area of interest (e.g., 'mumbai').
      - s2_tile_path: An optional local path to a pre-staged Sentinel-2 imagery tile (.SAFE or .tif).
      
    Task:
      Load the U-Net / Segformer model, perform inference on the 9-channel Sentinel imagery, 
      extract the sub-pixel plastic fraction, and return polygons of detected plastic.
      
    Output format:
      Must return a valid GeoJSON 'FeatureCollection' dictionary. Every feature MUST have 
      properties: ['id', 'confidence', 'area_sq_meters', 'age_days', 'type'].
      
    -----------------
    This currently returns mock data to keep the frontend running.
    Remove the mock return and replace it with your PyTorch inference later.
    """
    
    # TODO (AI Team):
    # 1. We optionally pull real satellite links based on the specific AOI (AWS STAC Integration)
    if aoi_id in AOI_BBOX_MAP:
        try:
            bbox = AOI_BBOX_MAP[aoi_id]
            # This triggers our Caching Strategy: STAC Search -> Download -> Cache -> Fallback
            local_cache_result = get_live_or_cached_imagery(aoi_id, bbox)
            
            if "error" not in local_cache_result:
                print(f"[{aoi_id}] Using Image {local_cache_result['id']} from source: {local_cache_result['source']}")
                # NOW YOUR AI TEAM HAS LOCAL FILES TO OPEN IN RASTERIO!
                # e.g., rasterio.open(local_cache_result['local_paths']['nir'])
            else:
                print(f"[{aoi_id}] Data Unreachable: {local_cache_result['error']}")
                
        except Exception as e:
            print(f"STAC fetch failed for {aoi_id}: {e}")

    # 2. Extract specific bands + calculate FDI, NDVI indices
    # 3. Model inference: probs, fractions = model(features)
    # 4. Convert probabilty mask to GeoJSON polygons (using shapely / rasterio.features)
    
    # Fallback to mock data for MVP phase
    return get_mock_detection_geojson(aoi_id)
