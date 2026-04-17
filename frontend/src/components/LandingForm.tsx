import React, { useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { LineLayer, PathLayer, PolygonLayer, ScatterplotLayer, GeoJsonLayer } from '@deck.gl/layers';
import * as turf from '@turf/turf';
import 'maplibre-gl/dist/maplibre-gl.css';
import api, { apiErrorMessage } from '../lib/api';

const INITIAL_VIEW_STATE = {
  longitude: 80.0,
  latitude: 18.0,
  zoom: 4.2,
  pitch: 0, // Flat 2D Map for clear tactical view
  bearing: 0
};

// Sentinel-2 Red and NIR bands are 10m resolution.
const SENTINEL2_PATCH_SIZE_METERS = 10;
const VISUAL_PREVIEW_PATCH_SIZE_METERS = 100;
const METERS_PER_DEG_LAT = 111320;

function buildSentinelPatchSquare(lng: number, lat: number, patchMeters: number): [number, number][] {
  const half = patchMeters / 2;
  const latDelta = half / METERS_PER_DEG_LAT;
  const lonScale = Math.max(Math.cos((lat * Math.PI) / 180), 1e-6);
  const lonDelta = half / (METERS_PER_DEG_LAT * lonScale);

  return [
    [lng - lonDelta, lat + latDelta],
    [lng + lonDelta, lat + latDelta],
    [lng + lonDelta, lat - latDelta],
    [lng - lonDelta, lat - latDelta],
  ];
}

export const LandingForm: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  React.useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  React.useEffect(() => {
    if (location.state && location.state.highlightedId) {
      setHighlightedId(location.state.highlightedId);
      const timer = setTimeout(() => {
        setHighlightedId(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [location.state]);

  // Single-point targeting; we auto-build a Sentinel-sized square patch.
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);
  const [currentSelection, setCurrentSelection] = useState<any>(null);
  const [processingSelection, setProcessingSelection] = useState<any>(null);

  const [coastalGeoJson, setCoastalGeoJson] = useState<any>({ type: 'FeatureCollection', features: [] });
  const [searchHistory, setSearchHistory] = useState<any[]>([]);
  const [hoverInfo, setHoverInfo] = useState<{ lng: number, lat: number, x: number, y: number, hasObject: boolean } | null>(null);

  const processingBbox = React.useMemo(() => {
    if (!processingSelection?.geometry?.coordinates?.[0]) return null;
    const ring = processingSelection.geometry.coordinates[0].slice(0, 4) as [number, number][];
    const lons = ring.map(([lon]) => lon);
    const lats = ring.map(([, lat]) => lat);
    return {
      minLon: Math.min(...lons),
      maxLon: Math.max(...lons),
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
    };
  }, [processingSelection]);

  React.useEffect(() => {
    // Fetch global history from the backend
    api.trackerSearch().then((res) => {
      setSearchHistory(res);
    }).catch((err) => console.error('tracker/search:', apiErrorMessage(err)));

    // Fetch dynamic coastline
    api.trackerCoastline().then((res) => {
      setCoastalGeoJson(res);
    }).catch((err) => console.error('tracker/coastline:', apiErrorMessage(err)));
  }, []);

  const getDensityColor = (density: number): [number, number, number, number] => {
    if (density > 0.7) return [245, 158, 11, 200]; // Gold/Amber
    if (density > 0.4) return [250, 204, 21, 200]; // Yellow gold
    return [16, 185, 129, 200]; // Emerald Green
  };

  const handleMapClick = useCallback((info: any) => {
    if (!info.coordinate) return;
    const [lng, lat] = info.coordinate;

    setDrawingPoints(() => {
      const nextPoints: [number, number][] = [[lng, lat]];
      const previewSquare = buildSentinelPatchSquare(lng, lat, VISUAL_PREVIEW_PATCH_SIZE_METERS);
      const processingSquare = buildSentinelPatchSquare(lng, lat, SENTINEL2_PATCH_SIZE_METERS);
      setCurrentSelection(turf.polygon([[...previewSquare, previewSquare[0]]]));
      setProcessingSelection(turf.polygon([[...processingSquare, processingSquare[0]]]));
      return nextPoints;
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
    // Draw the auto-generated Sentinel patch border.
    new PathLayer({
      id: 'drawing-border',
      data: currentSelection ? [{ path: currentSelection.geometry.coordinates[0] }] : [],
      getPath: (d: any) => d.path,
      getColor: [16, 185, 129, 255],
      getWidth: 150,
      widthMinPixels: 2
    }),

    // Draw the selected center point as a glowing node.
    new ScatterplotLayer({
      id: 'drawing-nodes',
      data: drawingPoints.map(p => ({ position: p })),
      getPosition: (d: any) => d.position,
      getFillColor: [16, 185, 129, 255],
      getRadius: 500,
      radiusMinPixels: 7
    }),

    // Fill the generated patch polygon.
    currentSelection && new PolygonLayer({
      id: 'drawing-fill',
      data: [currentSelection],
      getPolygon: (d: any) => d.geometry.coordinates[0],
      getFillColor: [16, 185, 129, 50],
      filled: true
    })
  ].filter(Boolean);

  const handleSubmit = async () => {
    if (processingSelection && drawingPoints.length === 1) {
      try {
        const patchCoordinates = processingSelection.geometry.coordinates[0].slice(0, 4);
        const record = await api.trackerSubmit(patchCoordinates as Array<[number, number]>);

        // Fetch globally updated search history instead of local hack
        const [histRes, coastRes] = await Promise.all([
          api.trackerSearch(),
          api.trackerCoastline(),
        ]);
        setSearchHistory(histRes);
        setCoastalGeoJson(coastRes);

        // Reset local selection drawing state so we can see the popups
        setDrawingPoints([]);
        setCurrentSelection(null);
        setProcessingSelection(null);

        const center = record.center ?? drawingPoints[0];
        const customAoiId = `custom_${center[0].toFixed(4)}_${center[1].toFixed(4)}`;
        navigate(`/drift/aoi/${customAoiId}`, { state: { highlightedId: record.id } });
      } catch (err: any) {
        console.error(err);
        const msg = apiErrorMessage(err);
        alert(msg.includes('ocean') || msg.includes('land')
          ? msg
          : 'Error deploying sector. Please try an oceanic location.');
        setDrawingPoints([]);
        setCurrentSelection(null);
        setProcessingSelection(null);
      }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', width: '100%', minHeight: '100vh', backgroundColor: '#1e2229', fontFamily: 'Inter, sans-serif' }}>

      {/* Sidebar Panel */}
      <div style={{ width: isMobile ? '100%' : '400px', minHeight: isMobile ? 'auto' : '100%', backgroundColor: '#272c35', borderRight: isMobile ? 'none' : '1px solid #38404d', borderBottom: isMobile ? '1px solid #38404d' : 'none', display: 'flex', flexDirection: 'column', zIndex: 10, boxShadow: isMobile ? '0 2px 10px rgba(0,0,0,0.2)' : '2px 0 10px rgba(0,0,0,0.2)' }}>

        {/* Main Control Section */}
        <div style={{ padding: isMobile ? '1rem' : '2rem', borderBottom: '1px solid #38404d' }}>
          <h1 style={{ margin: '0 0 1rem 0', fontSize: isMobile ? '1.2rem' : '1.8rem', color: '#e2e8f0', textTransform: 'uppercase', letterSpacing: isMobile ? '1px' : '2px' }}>D.R.I.F.T._OS v2.0</h1>

          <div style={{ marginBottom: '1.5rem', fontSize: '0.95rem', lineHeight: '1.6', color: '#94a3b8' }}>
            <strong style={{ color: '#f59e0b' }}>&gt; SECTOR DEPLOYMENT</strong><br />
            Click 1 ocean point. D.R.I.F.T. previews 100m x 100m for visibility, but processes a 10m x 10m Sentinel-2 patch.
            <br /><br />
            <strong>Points Logged:</strong> <span style={{ color: '#e2e8f0', fontWeight: 'bold' }}>{drawingPoints.length}/1</span>
          </div>

          {drawingPoints.length === 1 && (
            <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', borderLeft: '4px solid #10b981', marginBottom: '1.5rem', fontSize: '0.9rem', color: '#10b981' }}>
              <span style={{ fontWeight: 'bold' }}>[ PATCH LOCKED ]</span><br />
              Center locked. 100m preview + 10m processing AOI generated.
            </div>
          )}

          {processingBbox && (
            <div style={{ padding: '0.8rem', background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: '6px', marginBottom: '1.1rem', fontFamily: 'monospace', fontSize: isMobile ? '0.72rem' : '0.78rem', color: '#9ce7cc', lineHeight: '1.5', overflowX: 'auto' }}>
              <div style={{ color: '#10b981', fontWeight: 700, marginBottom: '0.25rem' }}>PROCESSING BBOX (10m)</div>
              <div>minLon: {processingBbox.minLon.toFixed(7)}</div>
              <div>minLat: {processingBbox.minLat.toFixed(7)}</div>
              <div>maxLon: {processingBbox.maxLon.toFixed(7)}</div>
              <div>maxLat: {processingBbox.maxLat.toFixed(7)}</div>
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={drawingPoints.length !== 1}
            style={{ width: '100%', padding: '1rem', background: drawingPoints.length === 1 ? '#10b981' : '#38404d', color: drawingPoints.length === 1 ? '#1e2229' : '#64748b', border: 'none', borderRadius: '6px', cursor: drawingPoints.length === 1 ? 'pointer' : 'not-allowed', fontWeight: 'bold', fontSize: '1rem', textTransform: 'uppercase', transition: 'all 0.3s ease', boxShadow: drawingPoints.length === 1 ? '0 4px 6px rgba(16, 185, 129, 0.2)' : 'none' }}>
            {drawingPoints.length === 1 ? 'Initialize AWS Deep Scan' : 'Awaiting Ocean Point...'}
          </button>

          <button
            onClick={() => navigate('/drift/history')}
            style={{ marginTop: '15px', width: '100%', background: '#2a2f38', border: '1px solid #475569', color: '#cbd5e1', padding: '10px', borderRadius: '4px', cursor: 'pointer', transition: 'background 0.3s ease', fontWeight: 'bold', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}
            onMouseOver={(e) => e.currentTarget.style.background = '#38404d'}
            onMouseOut={(e) => e.currentTarget.style.background = '#2a2f38'}
          >
            ACCESS DEPLOYMENT LOGS
          </button>

          <button
            onClick={() => navigate('/drift/dashboard')}
            style={{ marginTop: '10px', width: '100%', background: '#1f7a5d', border: '1px solid #279a74', color: '#eaf8f3', padding: '10px', borderRadius: '4px', cursor: 'pointer', transition: 'background 0.3s ease', fontWeight: 'bold', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}
            onMouseOver={(e) => e.currentTarget.style.background = '#24916d'}
            onMouseOut={(e) => e.currentTarget.style.background = '#1f7a5d'}
          >
            OPEN INTEL DASHBOARD
          </button>
        </div>

        {/* Threat Legend Section */}
        <div style={{ padding: isMobile ? '1rem' : '2rem', flexGrow: 1 }}>
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
      <div style={{ position: 'relative', flexGrow: 1, height: isMobile ? '62vh' : '100vh', minHeight: isMobile ? 420 : undefined }}>
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
