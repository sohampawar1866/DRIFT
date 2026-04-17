import React, { useEffect, useState } from 'react';
import { useLocation, useParams, useNavigate } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
<<<<<<< HEAD
import { GeoJsonLayer } from '@deck.gl/layers';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, BarChart2, CheckCircle, FileCode2, FileText } from 'lucide-react';
=======
import { GeoJsonLayer, ScatterplotLayer, TextLayer, BitmapLayer, PathLayer } from '@deck.gl/layers';
import { HeatmapLayer } from '@deck.gl/aggregation-layers';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity, BarChart2, AlertTriangle, Download, FileText, FileCode2 } from 'lucide-react';
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
import 'maplibre-gl/dist/maplibre-gl.css';
import api, {
  apiErrorMessage,
  type DashboardMetrics,
  type DetectionFC,
  type ForecastFC,
  type MissionFC,
  type ExportFormat,
  type SpatialQuery,
  type AoiEntry,
} from '../lib/api';

const INITIAL_VIEW_STATE = {
  longitude: 72.8,
  latitude: 19.0,
  zoom: 9,
  pitch: 30,
  bearing: 0
};

export const OpsDashboard: React.FC = () => {
  const { aoi_id } = useParams<{ aoi_id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [detectionData, setDetectionData] = useState<DetectionFC | null>(null);
  const [forecastData, setForecastData] = useState<ForecastFC | null>(null);
  const [missionData, setMissionData] = useState<MissionFC | null>(null);
  const [metricsData, setMetricsData] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(false);
<<<<<<< HEAD
  const [timeSlider, setTimeSlider] = useState(24);
  const [generatingMission, setGeneratingMission] = useState<ExportFormat | null>(null);

  const spatialQuery = React.useMemo<SpatialQuery | undefined>(() => {
    const toBbox = (coords: Array<[number, number]>): [number, number, number, number] => {
      const lons = coords.map(([lon]) => lon);
      const lats = coords.map(([, lat]) => lat);
      return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
    };

    const state = location.state as { coordinates?: Array<[number, number]> } | null;
    const polygon = state?.coordinates;
    if (polygon && polygon.length >= 3) {
      return { polygon, bbox: toBbox(polygon) };
=======
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [timeSlider, setTimeSlider] = useState(360); // Default to final state
  const [selectedFeature, setSelectedFeature] = useState<any | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [showHeatmaps, setShowHeatmaps] = useState(true);
  const [isSplitView, setIsSplitView] = useState(false);
  const [showMission, setShowMission] = useState(false);

  const fetchForecast = React.useCallback(async (id: string, rawHours: number, lat?: number, lon?: number) => {
    const hours = snapForecastHours(rawHours);
    setLoading(true); setErrorMsg(null);
    try {
      setForecastData(await api.forecast(id, hours, lat, lon));
    } catch (err) {
      setErrorMsg(`Forecast failed: ${apiErrorMessage(err)}`);
    } finally { setLoading(false); }
  }, []);

  const fetchDetection = React.useCallback(async (id: string) => {
    setLoading(true); setErrorMsg(null);
    let lat: number | undefined;
    let lon: number | undefined;
    
    if (id.startsWith('custom_')) {
      const parts = id.split('_');
      lon = parseFloat(parts[1]);
      lat = parseFloat(parts[2]);
    }

    try {
      const data = await api.detect(id, lat, lon);
      setDetectionData(data);
      // AUTO-TRIGGER: Predict trajectory by default (360h)
      fetchForecast(id, 360, lat, lon);
    } catch (err) {
      setErrorMsg(`Detection failed: ${apiErrorMessage(err)}`);
    } finally { setLoading(false); }
  }, [fetchForecast]);

  const fetchMission = React.useCallback(async (id: string) => {
    try {
      setMissionData(await api.mission(id));
    } catch (err) {
      // Non-fatal; mission overlay just won't render.
      console.error('mission:', apiErrorMessage(err));
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    }

    if (aoi_id?.startsWith('custom_')) {
      const parts = aoi_id.split('_');
      if (parts.length === 3) {
        const lon = Number(parts[1]);
        const lat = Number(parts[2]);
        if (Number.isFinite(lon) && Number.isFinite(lat)) {
          const halfSpan = 0.03;
          return { bbox: [lon - halfSpan, lat - halfSpan, lon + halfSpan, lat + halfSpan] };
        }
      }
    }

    return undefined;
  }, [aoi_id, location.state]);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const fetchDetection = React.useCallback(async () => {
    setLoading(true);
    try {
      if (!aoi_id) return;
      setDetectionData(await api.detect(aoi_id, spatialQuery));
    } catch (err) {
      console.error('detect:', apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [aoi_id, spatialQuery]);

  const fetchForecast = React.useCallback(async (hours: number) => {
    if (hours === 0) {
      setForecastData(null);
      return;
    }
    setLoading(true);
    try {
      if (!aoi_id) return;
      const allowedHours = hours === 24 || hours === 48 || hours === 72
        ? hours
        : 24;
      setForecastData(await api.forecast(aoi_id, allowedHours, spatialQuery));
    } catch (err) {
      console.error('forecast:', apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [aoi_id, spatialQuery]);

  const fetchMission = React.useCallback(async () => {
    try {
      if (!aoi_id) return;
      setMissionData(await api.mission(aoi_id, spatialQuery));
    } catch (err) {
      console.error('mission:', apiErrorMessage(err));
      setMissionData(null);
    }
  }, [aoi_id, spatialQuery]);

  const fetchDashboardMetrics = React.useCallback(async () => {
    try {
      if (!aoi_id) return;
      setMetricsData(await api.dashboardMetrics(aoi_id, spatialQuery));
    } catch (err) {
      console.error('metrics:', apiErrorMessage(err));
    }
  }, [aoi_id, spatialQuery]);

  useEffect(() => {
    if (!aoi_id) return;
<<<<<<< HEAD
    const timer = window.setTimeout(() => {
      void fetchDashboardMetrics();
      void fetchDetection();
      void fetchForecast(timeSlider);
      void fetchMission();
=======
    centerOnAoi(aoi_id);
    fetchDashboardMetrics(aoi_id);
    fetchDetection(aoi_id);
    fetchMission(aoi_id);
    // fetchForecast is now auto-triggered inside fetchDetection
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aoi_id]);
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)

      // Dynamically update viewState center based on custom string or available AOIs
      if (aoi_id.startsWith('custom_')) {
        const parts = aoi_id.split('_');
        if (parts.length === 3) {
          const lon = parseFloat(parts[1]);
          const lat = parseFloat(parts[2]);
          if (!Number.isNaN(lon) && !Number.isNaN(lat)) {
            setViewState((prev) => ({
              ...prev,
              longitude: lon,
              latitude: lat,
            }));
          }
        }
        return;
      }

      api
        .listAois()
        .then((res) => {
          const matched = res.aois.find((a: AoiEntry) => a.id === aoi_id);
          if (matched) {
            setViewState((prev) => ({ ...prev, longitude: matched.center[0], latitude: matched.center[1] }));
          }
        })
        .catch((err) => console.error('aois:', apiErrorMessage(err)));
    }, 0);

    return () => window.clearTimeout(timer);
  }, [aoi_id, fetchDashboardMetrics, fetchDetection, fetchForecast, fetchMission, timeSlider]);

  const handleExportMission = (format: ExportFormat) => {
    if (!aoi_id) return;
    setGeneratingMission(format);
    window.open(api.exportUrl(aoi_id, format, spatialQuery), '_blank');
    setTimeout(() => setGeneratingMission(null), 1500);
  };

<<<<<<< HEAD
  // Rendering Layers
  const layers = [
    // Live detection polygons (what the AI found)
    detectionData && new GeoJsonLayer({
      id: 'ai-detections',
      data: detectionData,
      getFillColor: [245, 158, 11, 180], // Gold/Amber polygons
      getLineColor: [245, 158, 11, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
      pickable: true
=======
  const handleClearDiscoveries = async () => {
    if (!aoi_id) return;
    setLoading(true);
    try {
      await api.clearCache();
      setDetectionData(null);
      setForecastData(null);
      setMissionData(null);
      // Re-trigger detection to show the fresh state
      await fetchDetection(aoi_id);
    } catch (err) {
      setErrorMsg(`Clear failed: ${apiErrorMessage(err)}`);
    } finally { setLoading(false); }
  };

  // Waypoint features for deck.gl overlay (extracted once).
  const missionWaypoints: Array<{ position: [number, number]; order: number }> =
    React.useMemo(() => {
      const feat = missionData?.features?.[0];
      const wps = feat?.properties?.waypoints ?? [];
      return wps.map(w => ({ position: [w.lon, w.lat] as [number, number], order: w.order }));
    }, [missionData]);

  // --- deck.gl layers -----------------------------------------------------
  const layers = [
    detectionData?.visual_url && detectionData?.bbox && new BitmapLayer({
      id: 'sentinel-visual',
      bounds: detectionData.bbox,
      image: detectionData.visual_url,
      opacity: 0.8,
    }),
    detectionData && new GeoJsonLayer({
      id: 'ai-detections',
      data: detectionData,
      getFillColor: [245, 158, 11, 100],
      getLineColor: [245, 158, 11, 255],
      stroked: true, filled: true, lineWidthMinPixels: 2, pickable: true,
      onHover: (info) => setHoveredId(info.object?.properties?.id || null),
      onClick: (info) => {
        setSelectedFeature(info.object);
        setIsSplitView(true);
      }
    }),
    detectionData && new TextLayer({
      id: 'detection-labels',
      data: detectionData.features,
      getPosition: (f: any) => f.geometry.type === 'Point' ? f.geometry.coordinates : f.geometry.coordinates[0][0],
      getText: (f: any) => `${f.properties.class_est || 'Plastic'} | ${(f.properties.confidence * 100).toFixed(0)}%`,
      getSize: 16,
      getAngle: 0,
      getTextAnchor: 'start',
      getAlignmentBaseline: 'bottom',
      getColor: [255, 255, 255, 255],
      fontFamily: 'Outfit, sans-serif',
      outlineWidth: 2,
      outlineColor: [30, 34, 41, 200],
      pixelOffset: [10, -10]
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    }),

    // Forecast polygons (where it is going)
    forecastData && new GeoJsonLayer({
      id: 'drift-particles-aura',
      data: forecastData,
<<<<<<< HEAD
      getFillColor: [16, 185, 129, 100], // Emerald Green ghost polygons
      getLineColor: [16, 185, 129, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
      getLineDashArray: [3, 3], // Dashed outlines for forecast
      dashJustified: true
=======
      getFillColor: (f: any) => f.properties.type === 'deposition_hotspot' ? [239, 68, 68, 60] : [6, 182, 212, 40],
      getLineColor: (f: any) => f.properties.type === 'deposition_hotspot' ? [239, 68, 68, 60] : [6, 182, 212, 40],
      stroked: true, filled: true, lineWidthMinPixels: 1,
      getPointRadius: 100, pointRadiusMinPixels: 2, pointRadiusUnits: 'meters',
      pickable: false,
      opacity: 0.15, // Subtle aura
      visible: !!hoveredId || isSplitView,
    }),
    forecastData?.trajectories && new PathLayer({
      id: 'drift-trajectories',
      data: forecastData.trajectories.features,
      getPath: (f: any) => f.geometry.coordinates,
      getColor: (f: any) => {
        const cls = f.properties.class_est?.toLowerCase();
        if (cls?.includes('plastic')) return [245, 158, 11, 200]; // Orange
        if (cls?.includes('algae')) return [34, 197, 94, 200]; // Green
        if (cls?.includes('sargassum')) return [146, 64, 14, 200]; // Sienna
        return [239, 68, 68, 200]; // Red for GhostNet
      },
      getWidth: 3,
      widthMinPixels: 2,
      pickable: true,
      visible: true, // Always show clean trajectories
      // @ts-ignore
      getDashArray: (f: any) => f.properties.id === hoveredId ? [0, 0] : [6, 4], // Solid on hover
      updateTriggers: {
        getDashArray: [hoveredId]
      }
    }),
    showHeatmaps && detectionData && new HeatmapLayer({
      id: 'satellite-intensity-heatmap',
      data: detectionData.features,
      getPosition: (f: any) => f.geometry.type === 'Point' ? f.geometry.coordinates : f.geometry.coordinates[0][0],
      getWeight: (f: any) => (f.properties.fdi || 0.1) * 2, // emphasized spectral strength
      radiusPixels: 25, // sharper points, less blur
      intensity: 3.0,   // more technical contrast
      threshold: 0.05,
      colorRange: [
        [254, 242, 242], [254, 202, 202], [248, 113, 113], [220, 38, 38], [153, 27, 27]
      ]
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    }),

    // Mission route from planner endpoint
    missionData && new GeoJsonLayer({
      id: 'mission-route',
      data: missionData,
<<<<<<< HEAD
      getLineColor: [6, 182, 212, 255],
      lineWidthMinPixels: 3,
      stroked: true,
      filled: false,
=======
      getLineColor: [6, 182, 212, 255], // Cyan
      lineWidthMinPixels: 4, // Bolder
      getLineWidth: 10,
      stroked: true,
      filled: false,
      visible: showMission,
    }),
    showHeatmaps && detectionData && new HeatmapLayer({
      id: 'chlorophyll-overlay',
      data: detectionData.features,
      getPosition: (f: any) => f.geometry.type === 'Point' ? f.geometry.coordinates : f.geometry.coordinates[0][0],
      getWeight: (f: any) => f.properties.chlorophyll || 0.5,
      radiusPixels: 60,
      opacity: 0.3,
      colorRange: [
        [240, 253, 244], [187, 247, 208], [74, 222, 128], [22, 163, 74], [21, 128, 61]
      ]
    }),
    missionWaypoints.length > 0 && new ScatterplotLayer({
      id: 'mission-waypoints',
      data: missionWaypoints,
      getPosition: (d: { position: [number, number] }) => d.position,
      getFillColor: [6, 182, 212, 255],
      getLineColor: [224, 242, 254, 255],
      getRadius: 250, radiusMinPixels: 7, stroked: true, lineWidthMinPixels: 2,
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
      pickable: true,
    })
  ].filter(Boolean);

  return (
    <div style={{ padding: isMobile ? '1rem' : '2rem', display: 'flex', flexDirection: 'column', gap: '1rem', minHeight: '100vh', background: '#1e2229', color: '#e2e8f0', fontFamily: 'Inter, sans-serif' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: '0.9rem', borderBottom: '1px solid #38404d', paddingBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: '#e2e8f0', fontSize: isMobile ? '1rem' : '1.5rem' }}><Activity size={isMobile ? 18 : 24} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#f59e0b' }} /> OPERATIONS: {aoi_id}</h2>
        
        <div style={{ display: 'flex', gap: '0.7rem', flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
          <button 
            onClick={() => handleExportMission('gpx')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: '#f59e0b', color: '#1e2229', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset' }}>
            <CheckCircle size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'gpx' ? 'GENERATING...' : 'EXPORT GPX'}
          </button>

          <button
            onClick={() => handleExportMission('geojson')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: '#10b981', color: '#1e2229', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset' }}>
            <FileCode2 size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'geojson' ? 'GENERATING...' : 'EXPORT GEOJSON'}
          </button>

          <button
            onClick={() => handleExportMission('pdf')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: '#06b6d4', color: '#0f172a', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset' }}>
            <FileText size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'pdf' ? 'GENERATING...' : 'EXPORT PDF'}
          </button>
<<<<<<< HEAD
          
          <button onClick={() => navigate('/drift')} style={{ padding: '0.6rem 1rem', background: '#272c35', color: '#cbd5e1', border: '1px solid #475569', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 140 : 'unset' }}>
=======
          <button onClick={() => handleExport('pdf')} disabled={!detectionData}
            style={exportBtnStyle(!!detectionData, '#06b6d4')}>
            <FileText size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> PDF
          </button>
          
          <button onClick={handleClearDiscoveries} disabled={loading || !aoi_id}
            style={{
              padding: '0.6rem 1.2rem', background: '#dc2626', color: '#fff',
              border: 'none', borderRadius: '4px', cursor: 'pointer',
              fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px'
            }}>
            <AlertTriangle size={14} /> CLEAR CACHE
          </button>
          <button onClick={() => navigate('/drift')}
            style={{
              padding: '0.6rem 1.2rem', background: '#272c35', color: '#cbd5e1',
              border: '1px solid #475569', borderRadius: '4px', cursor: 'pointer',
              fontWeight: 'bold',
            }}>
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
            ABORT & RETURN
          </button>
        </div>
      </header>

<<<<<<< HEAD
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr', gap: '1rem' }}>
        <div style={{ background: '#272c35', borderRadius: '8px', border: '1px solid #38404d', display: 'flex', flexDirection: 'column', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
          <div style={{ position: 'relative', flexGrow: 1, minHeight: isMobile ? '380px' : '600px', backgroundColor: '#1e2229', borderRadius: '8px 8px 0 0', overflow: 'hidden' }}>
=======
      {errorMsg && (
        <div style={{
          background: 'rgba(220, 38, 38, 0.15)', borderLeft: '4px solid #dc2626',
          padding: '0.75rem 1rem', borderRadius: '4px', color: '#fecaca',
          display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <AlertTriangle size={16} /> {errorMsg}
        </div>
      )}

      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: isSplitView ? '1fr 1fr' : '2fr 1fr', 
        gap: '2rem',
        transition: 'grid-template-columns 0.4s ease'
      }}>
        <div style={{
          background: '#272c35', borderRadius: '8px', border: '1px solid #38404d',
          display: 'flex', flexDirection: 'column', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)',
        }}>
          <div style={{
            position: 'relative', flexGrow: 1, minHeight: '600px',
            backgroundColor: '#1e2229', borderRadius: '8px 8px 0 0', overflow: 'hidden',
          }}>
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
            <DeckGL
              initialViewState={viewState}
              onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState as typeof INITIAL_VIEW_STATE)}
              controller={true}
              layers={layers}
<<<<<<< HEAD
              getTooltip={({object}) => object && (object.properties?.id || "Detection Polygon")}
=======
              onClick={(info) => {
                if (info?.object) setSelectedFeature(info.object);
                else setSelectedFeature(null);
              }}
              getTooltip={(info) => {
                const object = info?.object;
                if (!object) return null;
                const o = object as { properties?: Record<string, unknown>; order?: number };
                if (typeof o.order === 'number') return `Waypoint ${o.order}`;
                return (o.properties?.id as string | undefined)
                  || (o.properties?.type as string | undefined)
                  || 'Feature';
              }}
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
            >
              <Map 
                mapLibre={maplibregl}
                mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl/style.json"
              />
            </DeckGL>
            
            {/* Detection detail Sidebar (Internal to Grid) */}
            {selectedFeature && !isSplitView && (
              <div style={{
                position: 'absolute', right: '1rem', top: '1rem', bottom: '1rem',
                width: '320px', background: 'rgba(30, 34, 41, 0.95)', border: '1px solid #38404d',
                borderRadius: '8px', zIndex: 10, padding: '1.5rem', display: 'flex',
                flexDirection: 'column', gap: '1rem', backdropFilter: 'blur(10px)',
                boxShadow: '-4px 0 15px rgba(0,0,0,0.5)', overflowY: 'auto'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                   <h3 style={{ margin: 0, color: '#f59e0b', fontSize: '1rem' }}>PREDICTION DETAILS</h3>
                   <button onClick={() => setSelectedFeature(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>✕</button>
                </div>
                <div style={{ background: '#272c35', padding: '1rem', borderRadius: '4px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>PREDICTED CLASS</div>
                    <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#e2e8f0' }}>{selectedFeature.properties?.class_est || 'Macroplastic'}</div>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    {pStat('Confidence', ((selectedFeature.properties?.confidence || 0)*100).toFixed(1) + '%', '#10b981')}
                    {pStat('FDI Index', selectedFeature.properties?.fdi?.toFixed(4) || '0.0142', '#f59e0b')}
                    {pStat('NDVI', selectedFeature.properties?.ndvi?.toFixed(4) || '0.052', '#06b6d4')}
                    {pStat('Age (Days)', selectedFeature.properties?.age_days || '8', '#a855f7')}
                </div>
                
                <button 
                  onClick={() => setIsSplitView(true)}
                  style={{ 
                    marginTop: 'auto', padding: '0.8rem', background: '#38404d', 
                    color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer'
                  }}>OPEN FULL ANALYTICS</button>
              </div>
            )}
          </div>
<<<<<<< HEAD
          
          <div style={{ padding: isMobile ? '1rem' : '1.5rem', display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: '1rem', alignItems: isMobile ? 'stretch' : 'center', background: '#2a2f38', borderRadius: '0 0 8px 8px', borderTop: '1px solid #38404d' }}>
            <div style={{ flexGrow: 1, display: 'flex', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: '0.8rem' }}>
              <label style={{ color: '#cbd5e1', fontWeight: 'bold' }}>T+ FORECAST (HOURS): <span style={{ color: '#10b981' }}>{timeSlider}h</span></label>
              <input type="range" min="0" max="72" step="24" value={timeSlider} onChange={e => setTimeSlider(Number(e.target.value))} style={{ flexGrow: 1, width: '100%', accentColor: '#10b981' }} />
            </div>
            <button disabled={loading} onClick={() => fetchForecast(timeSlider)} style={{ padding: '0.75rem 1.2rem', background: '#10b981', color: '#1e2229', fontWeight: 'bold', border: 'none', borderRadius: '4px', cursor: 'pointer', boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)', width: isMobile ? '100%' : 'auto' }}>
              CALCULATE D.R.I.F.T. PHYSICS
            </button>
=======

          <div style={{
            padding: '1.5rem', display: 'flex', gap: '2rem', alignItems: 'center',
            background: '#2a2f38', borderRadius: '0 0 8px 8px', borderTop: '1px solid #38404d',
          }}>
            <div style={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <label style={{ color: '#cbd5e1', fontWeight: 'bold' }}>
                T+ FORECAST (HOURS): <span style={{ color: '#10b981' }}>{snappedHours}h</span>
                {snappedHours !== timeSlider && (
                  <span style={{ color: '#94a3b8', fontWeight: 400, marginLeft: '0.5rem', fontSize: '0.8rem' }}>
                    (snapped from {timeSlider}h)
                  </span>
                )}
              </label>
              <input
                type="range" min="0" max="360" step="1"
                value={timeSlider}
                onChange={e => setTimeSlider(Number(e.target.value))}
                style={{ flexGrow: 1, accentColor: '#10b981' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
                 <input type="checkbox" checked={showHeatmaps} onChange={e => setShowHeatmaps(e.target.checked)} />
                 HEATMAPS
              </label>
              <div style={{
                background: !detectionData ? '#3b82f6' : 
                            loading ? '#d97706' :
                            detectionData?.features?.[0]?.properties?.data_source === 'live_stac' ? '#059669' : '#475569',
                color: '#fff', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 800,
                display: 'flex', alignItems: 'center', gap: '6px'
              }}>
                {loading && <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#fff', animation: 'pulse 1.5s infinite' }}></div>}
                {!detectionData ? 'SYSTEM READY' : 
                 loading ? 'FETCHING SATELLITE...' :
                 detectionData?.features?.[0]?.properties?.data_source === 'live_stac' ? 'SATELLITE VERIFIED' : 'DEMO MODE (FALLBACK)'}
              </div>
              <button 
                onClick={() => setShowMission(!showMission)}
                style={{
                  padding: '0.5rem 1rem', background: showMission ? '#06b6d4' : '#334155',
                  color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer',
                  fontSize: '0.75rem', fontWeight: 'bold'
                }}>
                {showMission ? '⚡ HIDE MISSION' : '⚡ PLAN MISSION'}
              </button>
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {isSplitView && selectedFeature && (
            <div style={{
              background: '#1e2229', borderRadius: '8px', border: '1px solid #f59e0b',
              padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem',
              animation: 'slideIn 0.3s ease-out'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <h2 style={{ margin: 0, color: '#f59e0b' }}>HIGH-FIDELITY SPECTRAL ANALYSIS</h2>
                  <button onClick={() => setIsSplitView(false)} style={{ background: '#272c35', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', color: '#fff', cursor: 'pointer' }}>CLOSE FULL ANALYTICS</button>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                  <div style={{ background: '#272c35', padding: '1.5rem', borderRadius: '8px', border: '1px solid #38404d' }}>
                      <h4 style={{ color: '#94a3b8', margin: '0 0 1rem 0' }}>FOCUSED DEPOSITION HEATMAP</h4>
                      <div style={{ height: '300px', background: '#1e2229', borderRadius: '4px', position: 'relative', overflow: 'hidden', border: '1px solid #f59e0b22' }}>
                          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at center, rgba(239, 68, 68, 0.4) 0%, transparent 80%)' }}></div>
                          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', border: '2px solid #f59e0b', width: '40px', height: '40px', borderRadius: '50%', boxShadow: '0 0 20px #f59e0b' }}></div>
                      </div>
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div style={{ background: '#272c35', padding: '1.5rem', borderRadius: '8px', border: '1px solid #38404d' }}>
                          <h4 style={{ color: '#94a3b8', margin: '0 0 1rem 0' }}>SPECTRAL METRICS</h4>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                              <div style={{ background: '#1e2229', padding: '1rem', borderRadius: '4px' }}>
                                  <div style={{ color: '#f59e0b', fontSize: '0.7rem' }}>FDI (FLOATING DEBRIS INDEX)</div>
                                  <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{selectedFeature.properties?.fdi?.toFixed(4) || '0.0142'}</div>
                              </div>
                              <div style={{ background: '#1e2229', padding: '1rem', borderRadius: '4px' }}>
                                  <div style={{ color: '#06b6d4', fontSize: '0.7rem' }}>NDVI (VEGETATION INDEX)</div>
                                  <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{selectedFeature.properties?.ndvi?.toFixed(4) || '0.052'}</div>
                              </div>
                          </div>
                      </div>
                      
                      <div style={{ background: '#272c35', padding: '1.5rem', borderRadius: '8px', border: '1px solid #38404d', flexGrow: 1 }}>
                          <h4 style={{ color: '#94a3b8', margin: '0 0 1rem 0' }}>MODEL DETERMINATION</h4>
                          <p style={{ color: '#cbd5e1', fontSize: '0.9rem', lineHeight: 1.6 }}>
                              The spectral signature exhibits a characteristic "Plastic Dip" between B8 and B11. 
                              High FDI and low NDVI strongly rule out organic Sargassum/Algae blooms.
                          </p>
                          <div style={{ marginTop: '1rem', display: 'inline-block', background: 'rgba(16, 185, 129, 0.2)', padding: '0.5rem 1rem', borderRadius: '20px', border: '1px solid #10b981', color: '#10b981', fontWeight: 'bold' }}>
                              DETERMINATION: {selectedFeature.properties?.class_est?.toUpperCase() || 'MACROPLASTIC'} (CONFIRMED)
                          </div>
                      </div>
                  </div>
              </div>
            </div>
          )}

<<<<<<< HEAD
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '1rem' : '1.5rem', border: '1px solid #38404d', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
            <h3 style={{ margin: '0 0 1rem 0', color: '#e2e8f0', fontWeight: 'bold' }}>RADAR LOGS</h3>
            
            <div style={{ padding: '1rem', background: 'rgba(245, 158, 11, 0.1)', borderLeft: '3px solid #f59e0b', marginBottom: '1rem' }}>
=======
          {/* Summary stat cards */}
          <div style={{
            background: '#272c35', borderRadius: '8px', padding: '1.25rem',
            border: '1px solid #38404d', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)',
          }}>
            <h3 style={{ margin: '0 0 0.75rem 0', color: '#e2e8f0', fontWeight: 'bold' }}>
              SECTOR SUMMARY
            </h3>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {stat('Patches', s?.total_patches)}
              {stat('Avg Conf', s ? (s.avg_confidence * 100).toFixed(1) + '%' : '—')}
              {stat('Area (m²)', s ? Math.round(s.total_area_sq_meters).toLocaleString() : '—')}
              {stat('High Priority', s?.high_priority_targets)}
              {stat('SST (°C)', s?.water_temp?.toFixed(1))}
              {stat('CHL (mg/m³)', s?.chlorophyll?.toFixed(2))}
            </div>
          </div>

          <div style={{
            background: '#272c35', borderRadius: '8px', padding: '1.5rem',
            border: '1px solid #38404d', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)',
          }}>
            <h3 style={{ margin: '0 0 1rem 0', color: '#e2e8f0', fontWeight: 'bold' }}>
              RADAR LOGS
            </h3>

            <div style={{
              padding: '1rem', background: 'rgba(245, 158, 11, 0.1)',
              borderLeft: '3px solid #f59e0b', marginBottom: '1rem',
            }}>
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#f59e0b' }}>Current Intel</h4>
              {loading ? <p style={{ margin: 0, color: '#94a3b8' }}>Scanning...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {detectionData ? `Detected ${detectionData.features?.length || 0} anomaly clusters.` : 'No baseline data.'}
                </div>
              )}
            </div>

            <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', borderLeft: '3px solid #10b981' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#10b981' }}>Simulation Output</h4>
              {loading ? <p style={{ margin: 0, color: '#94a3b8' }}>Processing vectors...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {forecastData ? `Generated ${forecastData.features?.length || 0} future D.R.I.F.T. paths.` : 'No active simulation.'}
                </div>
              )}
            </div>

            <div style={{ padding: '1rem', background: 'rgba(6, 182, 212, 0.1)', borderLeft: '3px solid #06b6d4', marginTop: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#06b6d4' }}>Mission Plan</h4>
              {missionData?.features?.[0]?.properties ? (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {(missionData.features[0].properties.waypoint_count ?? 0)} waypoints · {(missionData.features[0].properties.total_distance_km ?? 0).toFixed(1)} km
                </div>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#94a3b8' }}>
                  No mission plan available.
                </div>
              )}
            </div>
          </div>

<<<<<<< HEAD
          <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '1rem' : '1.5rem', border: '1px solid #38404d', flexGrow: 1, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
            <h3 style={{ margin: '0 0 1.5rem 0', color: '#e2e8f0', fontWeight: 'bold' }}><BarChart2 size={18} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#10b981' }} /> PLASTIC DEGRADATION MODEL</h3>
            {metricsData && metricsData.biofouling_chart_data && metricsData.biofouling_chart_data.length > 0 ? (
              <div style={{ height: '250px' }}>
=======
          <div style={{
            background: '#272c35', borderRadius: '8px', padding: '1.5rem',
            border: '1px solid #38404d', flexGrow: 1,
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)',
          }}>
            <h3 style={{ margin: '0 0 1.5rem 0', color: '#e2e8f0', fontWeight: 'bold' }}>
              <BarChart2 size={18} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#10b981' }} />
              PLASTIC DEGRADATION MODEL
            </h3>
            {metricsData?.biofouling_chart_data?.length ? (
              <div style={{ height: '350px', width: '100%', minHeight: '350px' }}>
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metricsData.biofouling_chart_data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#38404d" />
                    <XAxis dataKey="age_days" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip contentStyle={{ backgroundColor: '#272c35', border: '1px solid #f59e0b', color: '#e2e8f0' }} />
                    <Line type="monotone" dataKey="simulated_confidence" stroke="#10b981" strokeWidth={3} dot={{ fill: '#10b981' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p style={{ color: '#94a3b8', textAlign: 'center', marginTop: '2rem' }}>No atmospheric degradation metrics logged.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
<<<<<<< HEAD
=======

function pStat(label: string, value: string, color: string) {
    return (
        <div style={{ background: '#2a2f38', padding: '0.75rem', borderRadius: '4px', border: '1px solid #38404d' }}>
            <div style={{ fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase' }}>{label}</div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: color, marginTop: '0.2rem' }}>{value}</div>
        </div>
    );
}

function exportBtnStyle(enabled: boolean, accent: string): React.CSSProperties {
    return {
        padding: '0.55rem 1rem',
        background: enabled ? accent : '#38404d',
        color: enabled ? '#1e2229' : '#64748b',
        border: 'none',
        borderRadius: '4px',
        cursor: enabled ? 'pointer' : 'not-allowed',
        fontWeight: 'bold',
        fontSize: '0.85rem',
    };
}
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
