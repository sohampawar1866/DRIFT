import React, { useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { LineLayer, PathLayer, PolygonLayer, ScatterplotLayer, GeoJsonLayer } from '@deck.gl/layers';
import * as turf from '@turf/turf';
import 'maplibre-gl/dist/maplibre-gl.css';
import axios from 'axios';

const INITIAL_VIEW_STATE = {
  longitude: 80.0,
  latitude: 18.0,
  zoom: 4.2,
  pitch: 0, // Flat 2D Map for clear tactical view
  bearing: 0
};

export const LandingForm: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  React.useEffect(() => {
    if (location.state && location.state.highlightedId) {
      setHighlightedId(location.state.highlightedId);
      const timer = setTimeout(() => {
        setHighlightedId(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [location.state]);

  // Custom Drawing State (Forcing 4-point Quadrilaterals/Trapezoids)
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);
  const [currentSelection, setCurrentSelection] = useState<any>(null);

  const [coastalGeoJson, setCoastalGeoJson] = useState<any>({ type: 'FeatureCollection', features: [] });
  const [searchHistory, setSearchHistory] = useState<any[]>([]);
  const [hoverInfo, setHoverInfo] = useState<{ lng: number, lat: number, x: number, y: number, hasObject: boolean } | null>(null);

  React.useEffect(() => {
    // Fetch global history from the backend
    axios.get('http://localhost:8000/api/v1/tracker/search').then(res => {
      setSearchHistory(res.data);
    }).catch(console.error);

    // Fetch dynamic coastline
    axios.get('http://localhost:8000/api/v1/tracker/coastline').then(res => {
      setCoastalGeoJson(res.data);
    }).catch(console.error);
  }, []);

  const getDensityColor = (density: number): [number, number, number, number] => {
    if (density > 0.7) return [245, 158, 11, 200]; // Gold/Amber
    if (density > 0.4) return [250, 204, 21, 200]; // Yellow gold
    return [16, 185, 129, 200]; // Emerald Green
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
  const activeHistory = searchHistory.slice(-5);

  const layers = [
    // --- COASTAL VULNERABILITY (JAGGED EXACT BORDERS) ---
    new GeoJsonLayer({
      id: 'coastal-risk',
      data: coastalGeoJson,
      stroked: true,
      filled: false,
      getLineColor: (f: any) => {
        const i = f.properties.intensity || 0;
        return i > 0.05 ? [245, 158, 11, 255] : [16, 185, 129, 255];
      },
      getLineWidth: (f: any) => Math.max(50, f.properties.intensity * 400),
      lineWidthMinPixels: 3,
      pickable: true,
      autoHighlight: true
    }),

    // --- PREDICTIVE DRIFT VECTOR (FLAT 2D LINE TO COAST) ---
    new LineLayer({
      id: 'drift-vectors',
      data: activeHistory,
      getSourcePosition: (d: any) => d.center,
      getTargetPosition: (d: any) => d.driftVector,
      getColor: (d: any) => getDensityColor(d.density), // Origin box color
      getWidth: 5,
      pickable: true
    }),

    // --- IMPACT ZONES (DOTS ON COAST) ---
    new ScatterplotLayer({
      id: 'impact-zones',
      data: activeHistory,
      getPosition: (d: any) => d.driftVector,
      getFillColor: [245, 158, 11, 255],
      getRadius: 6000, // 6 km radius hit marker
      radiusMinPixels: 4,
      pickable: true
    }),

    // --- HISTORICAL BOXES ---
    new PolygonLayer({
      id: 'historical-polygons',
      data: activeHistory,
      getPolygon: (d: any) => d.coordinates,
      getFillColor: (d: any) => {
        if (d.id === highlightedId) return [255, 255, 255, 200];
        return [...getDensityColor(d.density).slice(0, 3), 80] as [number, number, number, number];
      },
      getLineColor: (d: any) => {
        if (d.id === highlightedId) return [255, 255, 255, 255];
        return getDensityColor(d.density);
      },
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
      getColor: [16, 185, 129, 255],
      getWidth: 150,
      widthMinPixels: 2
    }),

    // Draw the corner nodes as glowing dots
    new ScatterplotLayer({
      id: 'drawing-nodes',
      data: drawingPoints.map(p => ({ position: p })),
      getPosition: (d: any) => d.position,
      getFillColor: [16, 185, 129, 255],
      getRadius: 300,
      radiusMinPixels: 5
    }),

    // Fill the polygon once closed
    currentSelection && new PolygonLayer({
      id: 'drawing-fill',
      data: [{ contour: [...drawingPoints, drawingPoints[0]] }],
      getPolygon: (d: any) => d.contour,
      getFillColor: [16, 185, 129, 50],
      filled: true
    })
  ].filter(Boolean);

  const handleSubmit = async () => {
    if (currentSelection) {
      try {
        await axios.post('http://localhost:8000/api/v1/tracker/search', {
          coordinates: drawingPoints
        });

        // Fetch globally updated search history instead of local hack
        const histRes = await axios.get('http://localhost:8000/api/v1/tracker/search');
        setSearchHistory(histRes.data);

        // Let's reload coastline intensity to respond instantly to the backend update
        const coastRes = await axios.get('http://localhost:8000/api/v1/tracker/coastline');
        setCoastalGeoJson(coastRes.data);

        // Reset local selection drawing state so we can see the popups
        setDrawingPoints([]);
        setCurrentSelection(null);
      } catch (err: any) {
        console.error(err);
        if (err.response && err.response.data && err.response.data.detail) {
          alert(err.response.data.detail);
        } else {
          alert("Error deploying sector. Please try an oceanic location.");
        }
        setDrawingPoints([]);
        setCurrentSelection(null);
      }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'row', width: '100%', height: '100vh', backgroundColor: '#1e2229', fontFamily: 'Inter, sans-serif' }}>

      {/* Sidebar Panel */}
      <div style={{ width: '400px', height: '100%', backgroundColor: '#272c35', borderRight: '1px solid #38404d', display: 'flex', flexDirection: 'column', zIndex: 10, boxShadow: '2px 0 10px rgba(0,0,0,0.2)' }}>

        {/* Main Control Section */}
        <div style={{ padding: '2rem', borderBottom: '1px solid #38404d' }}>
          <h1 style={{ margin: '0 0 1rem 0', fontSize: '1.8rem', color: '#e2e8f0', textTransform: 'uppercase', letterSpacing: '2px' }}>DRIFT_OS v2.0</h1>

          <div style={{ marginBottom: '1.5rem', fontSize: '0.95rem', lineHeight: '1.6', color: '#94a3b8' }}>
            <strong style={{ color: '#f59e0b' }}>&gt; SECTOR DEPLOYMENT</strong><br />
            Click 4 points onto the map surface to define a target trapezoid over the ocean.
            <br /><br />
            <strong>Points Logged:</strong> <span style={{ color: '#e2e8f0', fontWeight: 'bold' }}>{drawingPoints.length}/4</span>
          </div>

          {drawingPoints.length === 4 && (
            <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', borderLeft: '4px solid #10b981', marginBottom: '1.5rem', fontSize: '0.9rem', color: '#10b981' }}>
              <span style={{ fontWeight: 'bold' }}>[ SECTOR LOCKED ]</span><br />
              Coordinates captured. Ready for deployment.
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={drawingPoints.length !== 4}
            style={{ width: '100%', padding: '1rem', background: drawingPoints.length === 4 ? '#10b981' : '#38404d', color: drawingPoints.length === 4 ? '#1e2229' : '#64748b', border: 'none', borderRadius: '6px', cursor: drawingPoints.length === 4 ? 'pointer' : 'not-allowed', fontWeight: 'bold', fontSize: '1rem', textTransform: 'uppercase', transition: 'all 0.3s ease', boxShadow: drawingPoints.length === 4 ? '0 4px 6px rgba(16, 185, 129, 0.2)' : 'none' }}>
            {drawingPoints.length === 4 ? 'Initialize AWS Deep Scan' : 'Awaiting 4-Point Target...'}
          </button>

          <button
            onClick={() => navigate('/drift/history')}
            style={{ marginTop: '15px', width: '100%', background: '#2a2f38', border: '1px solid #475569', color: '#cbd5e1', padding: '10px', borderRadius: '4px', cursor: 'pointer', transition: 'background 0.3s ease', fontWeight: 'bold', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}
            onMouseOver={(e) => e.currentTarget.style.background = '#38404d'}
            onMouseOut={(e) => e.currentTarget.style.background = '#2a2f38'}
          >
            ACCESS DEPLOYMENT LOGS
          </button>
        </div>

        {/* Threat Legend Section */}
        <div style={{ padding: '2rem', flexGrow: 1 }}>
          <h4 style={{ margin: '0 0 1rem 0', color: '#94a3b8', textTransform: 'uppercase', fontSize: '0.85rem', fontWeight: 'bold', letterSpacing: '1px' }}>Threat Legend & Analytics</h4>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', fontSize: '0.9rem', color: '#cbd5e1' }}>
            <div style={{ width: '16px', height: '16px', background: '#f59e0b', borderRadius: '4px', boxShadow: '0 0 5px #f59e0b' }}></div>
            <span>Critical Coastline Accumulation</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', fontSize: '0.9rem', color: '#cbd5e1' }}>
            <div style={{ width: '20px', height: '3px', background: 'linear-gradient(90deg, #10b981, #f59e0b)' }}></div>
            <span>Flat Vector: Predictive Drift Path</span>
          </div>
        </div>
      </div>

      {/* Map Content Section */}
      <div style={{ position: 'relative', flexGrow: 1, height: '100%' }}>
        <DeckGL
          initialViewState={viewState}
          onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState as typeof INITIAL_VIEW_STATE)}
          controller={true}
          layers={layers}
          onClick={handleMapClick}
          onHover={(info) => {
            if (info.coordinate) {
              setHoverInfo({
                lng: info.coordinate[0],
                lat: info.coordinate[1],
                x: info.x,
                y: info.y,
                hasObject: Boolean(info.object)
              });
            } else {
              setHoverInfo(null);
            }
          }}
          getTooltip={({ object }) => {
            if (!object) return null;
            if (object.properties?.name) return object.properties.name;
            if (!object.density) return null;
            const risk = object.density > 0.7 ? "CRITICAL" : (object.density > 0.4 ? "ELEVATED" : "LOW");
            const color = risk === "CRITICAL" ? "#f59e0b" : risk === "ELEVATED" ? "#facc15" : "#10b981";
            return {
              html: `
                <div style="font-family: monospace; font-size: 13px;">
                  <h4 style="margin: 0 0 5px 0; color: #10b981; border-bottom: 1px solid #38404d; padding-bottom: 5px;">SECTOR: ${object.id}</h4>
                  <div style="margin-bottom: 3px; color: #cbd5e1;"><strong>Risk Level:</strong> <span style="color: ${color}; font-weight: bold;">${risk}</span></div>
                  <div style="margin-bottom: 3px; color: #cbd5e1;"><strong>Density:</strong> ${(object.density * 100).toFixed(1)}%</div>
                  <div style="margin-bottom: 3px; color: #cbd5e1;"><strong>Bearing/Target:</strong> ${object.driftVector[1].toFixed(2)}&deg;N, ${object.driftVector[0].toFixed(2)}&deg;E</div>
                  <div style="color: #94a3b8; margin-top: 5px; font-size: 11px;">Deployed: ${object.date}</div>
                </div>
              `,
              style: {
                backgroundColor: 'rgba(39, 44, 53, 0.95)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: '#e2e8f0',
                borderRadius: '6px',
                padding: '12px',
                boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
                zIndex: 10000,
                marginTop: '15px',
                left: '15px'
              }
            };
          }}
        >
          <Map mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
        </DeckGL>

        {hoverInfo && !hoverInfo.hasObject && (
          <div style={{
            position: 'absolute',
            left: hoverInfo.x + 15,
            top: hoverInfo.y + 15,
            background: 'rgba(39, 44, 53, 0.9)',
            color: '#10b981',
            padding: '6px 10px',
            borderRadius: '4px',
            fontSize: '12px',
            pointerEvents: 'none',
            zIndex: 1,
            fontFamily: 'monospace',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            boxShadow: '0 4px 10px rgba(0,0,0,0.5)'
          }}>
            {hoverInfo.lat.toFixed(4)}&deg;N<br />
            {hoverInfo.lng.toFixed(4)}&deg;E
          </div>
        )}
      </div>
    </div>
  );
};
