import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { ArcLayer, PathLayer, PolygonLayer, ScatterplotLayer, GeoJsonLayer } from '@deck.gl/layers';
import * as turf from '@turf/turf';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW_STATE = {
  longitude: 72.8,
  latitude: 19.0,
  zoom: 10,
  pitch: 45, // 3D Pitch for Deck.GL
  bearing: -10
};

export const LandingForm: React.FC = () => {
  const navigate = useNavigate();
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  
  // Custom Drawing State (Forcing 4-point Quadrilaterals/Trapezoids)
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);
  const [currentSelection, setCurrentSelection] = useState<any>(null);

  // MOCK HIGH-RES COASTAL GEOJSON
  const coastalGeoJson = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { intensity: 0.9, name: "High Risk Area" },
        geometry: { type: 'LineString', coordinates: [[72.8, 18.9], [72.81, 18.95], [72.805, 19.0], [72.82, 19.05], [72.81, 19.1]] }
      },
      {
        type: 'Feature',
        properties: { intensity: 0.3, name: "Low Risk Area" },
        geometry: { type: 'LineString', coordinates: [[72.82, 19.05], [72.84, 19.1], [72.85, 19.15]] }
      }
    ]
  };

  const searchHistory = [
    { id: "S1", coordinates: [[72.75, 18.95], [72.78, 18.95], [72.78, 18.92], [72.75, 18.92]], center: [72.765, 18.935] as [number,number], driftVector: [72.80, 18.98] as [number,number], density: 0.85, date: "2026-04-16" },
    { id: "S2", coordinates: [[72.65, 18.85], [72.68, 18.85], [72.68, 18.82], [72.65, 18.82]], center: [72.665, 18.835] as [number,number], driftVector: [72.70, 18.87] as [number,number], density: 0.45, date: "2026-04-17" }
  ];

  const getDensityColor = (density: number): [number, number, number, number] => {
    if (density > 0.7) return [255, 23, 68, 200]; // Neon Pink/Red
    if (density > 0.4) return [255, 234, 0, 200]; // Neon Yellow
    return [0, 230, 118, 200]; // Neon Green
  };

  const handleMapClick = useCallback((info: any) => {
    if (!info.coordinate) return;
    const [lng, lat] = info.coordinate;
    
    setDrawingPoints(prev => {
      // If we already have a box, a new click resets the drawing board
      if (prev.length === 4) {
        setCurrentSelection(null);
        return [[lng, lat]];
      }
      
      const newPoints = [...prev, [lng, lat] as [number, number]];
      
      if (newPoints.length === 4) {
        // Build the valid GeoJSON polygon (closing the loop by repeating the first point)
        const polygon = turf.polygon([[...newPoints, newPoints[0]]]);
        setCurrentSelection(polygon);
      }
      
      return newPoints;
    });
  }, []);

  // Deck.GL Layers
  const layers = [
    // --- COASTAL VULNERABILITY (JAGGED EXACT BORDERS) ---
    new GeoJsonLayer({
      id: 'coastal-risk',
      data: coastalGeoJson,
      stroked: true,
      filled: false,
      getLineColor: (f: any) => getDensityColor(f.properties.intensity),
      getLineWidth: (f: any) => Math.max(50, f.properties.intensity * 400),
      lineWidthMinPixels: 3,
      pickable: true,
      autoHighlight: true
    }),

    // --- HISTORICAL DRIFT ARCS (3D SWEEPING ARROWS) ---
    new ArcLayer({
      id: 'drift-arcs',
      data: searchHistory,
      getSourcePosition: (d: any) => d.center,
      getTargetPosition: (d: any) => d.driftVector,
      getSourceColor: (d: any) => getDensityColor(d.density), // Origin box color
      getTargetColor: [255, 0, 0, 255],                       // Lands on red
      getWidth: 4,
      getHeight: 0.5, // The apex height of the 3D arc
      getTilt: 0,
      pickable: true
    }),

    // --- HISTORICAL BOXES ---
    new PolygonLayer({
      id: 'historical-polygons',
      data: searchHistory,
      getPolygon: (d: any) => d.coordinates,
      getFillColor: (d: any) => [...getDensityColor(d.density).slice(0,3), 80] as [number,number,number,number],
      getLineColor: (d: any) => getDensityColor(d.density),
      getLineWidth: 100,
      stroked: true,
      filled: true,
      wireframe: true,
      pickable: true
    }),

    // --- DRAWING STATE UI ---
    // Draw the borders of the shape dynamically as the user clicks
    new PathLayer({
      id: 'drawing-border',
      data: drawingPoints.length > 0 ? [{ path: currentSelection ? [...drawingPoints, drawingPoints[0]] : drawingPoints }] : [],
      getPath: (d: any) => d.path,
      getColor: [0, 229, 255, 255],
      getWidth: 150,
      widthMinPixels: 2
    }),
    
    // Draw the corner nodes as glowing dots
    new ScatterplotLayer({
      id: 'drawing-nodes',
      data: drawingPoints.map(p => ({ position: p })),
      getPosition: (d: any) => d.position,
      getFillColor: [0, 229, 255, 255],
      getRadius: 300,
      radiusMinPixels: 5
    }),
    
    // Fill the polygon once closed
    currentSelection && new PolygonLayer({
      id: 'drawing-fill',
      data: [{ contour: [...drawingPoints, drawingPoints[0]] }],
      getPolygon: (d: any) => d.contour,
      getFillColor: [0, 229, 255, 50],
      filled: true
    })
  ].filter(Boolean);

  const handleSubmit = () => {
    if (currentSelection) {
      const center = turf.centerOfMass(currentSelection).geometry.coordinates;
      const customAoiId = `custom_${center[0].toFixed(4)}_${center[1].toFixed(4)}`;
      navigate(`/aoi/${customAoiId}`);
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100vh', backgroundColor: '#0a0a0a' }}>
      <DeckGL
        initialViewState={viewState}
        onViewStateChange={({viewState}) => setViewState(viewState)}
        controller={true}
        layers={layers}
        onClick={handleMapClick}
        getTooltip={({object}) => object && (object.density ? `Density: ${(object.density * 100).toFixed(0)}%\nLogged: ${object.date}` : object.properties?.name)}
      >
        <Map mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
      </DeckGL>

      {/* Floating HUD Panel */}
      <div style={{ position: 'absolute', top: '2rem', right: '2rem', background: 'rgba(10, 15, 25, 0.85)', backdropFilter: 'blur(10px)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(0, 229, 255, 0.3)', boxShadow: '0 8px 32px rgba(0,229,255,0.2)', width: '380px', zIndex: 1000, color: '#e0f7fa' }}>
        <h1 style={{ margin: '0 0 1rem 0', fontSize: '1.8rem', color: '#00e5ff', textTransform: 'uppercase', letterSpacing: '2px', textShadow: '0 0 10px rgba(0,229,255,0.5)' }}>DRIFT_OS v2.0</h1>
        
        {/* Trajectory Guide for UX */}
        <div style={{ marginBottom: '1.5rem', fontSize: '0.95rem', lineHeight: '1.6' }}>
          <strong style={{ color: '#00e5ff' }}>&gt; SECTOR DEPLOYMENT</strong><br/>
          Click 4 points onto the map surface to define a target trapezoid over the ocean.
          <br/><br/>
          <strong>Points Logged:</strong> {drawingPoints.length}/4
        </div>
        
        {drawingPoints.length === 4 && (
          <div style={{ padding: '1rem', background: 'rgba(0, 229, 255, 0.1)', borderLeft: '4px solid #00e5ff', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
            <span style={{ color: '#00e5ff', fontWeight: 'bold' }}>[ SECTOR LOCKED ]</span><br/>
            Coordinates captured. Ready for deployment.
          </div>
        )}

        <button 
          onClick={handleSubmit} 
          disabled={drawingPoints.length !== 4}
          style={{ width: '100%', padding: '1rem', background: drawingPoints.length === 4 ? '#00e5ff' : 'rgba(255,255,255,0.1)', color: drawingPoints.length === 4 ? '#000' : '#666', border: 'none', borderRadius: '6px', cursor: drawingPoints.length === 4 ? 'pointer' : 'not-allowed', fontWeight: 'bold', fontSize: '1rem', textTransform: 'uppercase', transition: 'all 0.3s ease', boxShadow: drawingPoints.length === 4 ? '0 0 15px rgba(0,229,255,0.5)' : 'none' }}>
          {drawingPoints.length === 4 ? 'Initialize AWS Deep Scan' : 'Awaiting 4-Point Target...'}
        </button>
      </div>

      {/* Threat Legend */}
      <div style={{ position: 'absolute', bottom: '2rem', right: '2rem', background: 'rgba(10, 15, 25, 0.85)', border: '1px solid rgba(255,255,255,0.2)', padding: '1rem', borderRadius: '8px', zIndex: 1000, color: '#fff', fontSize: '0.85rem' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', color: '#aaa', textTransform: 'uppercase' }}>Threat Legend & Analytics</h4>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <div style={{ width: '16px', height: '16px', background: '#ff1744', borderRadius: '4px', boxShadow: '0 0 5px #ff1744' }}></div> Critical Coastline Accumulation
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <div style={{ width: '20px', height: '2px', background: 'linear-gradient(90deg, #ffea00, #ff1744)' }}></div> 3D Arc: Predictive Drift Path
        </div>
      </div>
    </div>
  );
};
