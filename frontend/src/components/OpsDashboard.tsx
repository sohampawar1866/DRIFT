import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useParams, useNavigate } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, BarChart2, CheckCircle, FileCode2, FileText } from 'lucide-react';
import gsap from 'gsap';
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
  const dashboardRef = useRef<HTMLDivElement>(null);

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [detectionData, setDetectionData] = useState<DetectionFC | null>(null);
  const [forecastData, setForecastData] = useState<ForecastFC | null>(null);
  const [missionData, setMissionData] = useState<MissionFC | null>(null);
  const [metricsData, setMetricsData] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [timeSlider, setTimeSlider] = useState(24);
  const [generatingMission, setGeneratingMission] = useState<ExportFormat | null>(null);

  useEffect(() => {
    if (dashboardRef.current) {
      gsap.fromTo(
        dashboardRef.current.children,
        { opacity: 0, y: 15 },
        { opacity: 1, y: 0, duration: 0.6, stagger: 0.1, ease: 'power2.out' }
      );
    }
  }, []);

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

  const customCenter = React.useMemo(() => {
    if (aoi_id?.startsWith('custom_')) {
      const parts = aoi_id.split('_');
      if (parts.length === 3) {
        const lon = parseFloat(parts[1]);
        const lat = parseFloat(parts[2]);
        if (!Number.isNaN(lon) && !Number.isNaN(lat)) {
          return [lon, lat] as [number, number];
        }
      }
    }
    return null;
  }, [aoi_id]);

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
    const timer = window.setTimeout(() => {
      void fetchDashboardMetrics();
      void fetchDetection();
      void fetchForecast(timeSlider);
      void fetchMission();

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
    }),

    // Forecast polygons (where it is going)
    forecastData && new GeoJsonLayer({
      id: 'drift-forecast',
      data: forecastData,
      getFillColor: [16, 185, 129, 100], // Emerald Green ghost polygons
      getLineColor: [16, 185, 129, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
      getLineDashArray: [3, 3], // Dashed outlines for forecast
      dashJustified: true
    }),

    // Mission route from planner endpoint
    missionData && new GeoJsonLayer({
      id: 'mission-route',
      data: missionData,
      getLineColor: [6, 182, 212, 255],
      lineWidthMinPixels: 3,
      stroked: true,
      filled: false,
      pickable: true,
    }),

    // The target origin marker
    customCenter && new ScatterplotLayer({
      id: 'target-origin',
      data: [{ position: customCenter }],
      getPosition: (d: { position: [number, number] }) => d.position,
      getFillColor: [16, 185, 129, 255], // Emerald green locator dot
      getRadius: 200,
      radiusMinPixels: 6,
      pickable: true
    })
  ].filter(Boolean);

  return (
    <div style={{ padding: isMobile ? '1rem' : '2rem', display: 'flex', flexDirection: 'column', gap: '1rem', minHeight: '100vh', background: 'var(--color-background)', color: 'var(--color-text-main)', fontFamily: 'var(--font-manrope)' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: '0.9rem', borderBottom: '1px solid var(--color-surface-variant)', paddingBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: 'var(--color-text-main)', fontSize: isMobile ? '1rem' : '1.5rem', fontFamily: 'var(--font-jakarta)' }}><Activity size={isMobile ? 18 : 24} style={{ marginRight: '8px', verticalAlign: 'middle', color: 'var(--color-primary)' }} /> OPERATIONS: {aoi_id}</h2>
        
        <div style={{ display: 'flex', gap: '0.7rem', flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
          <button 
            onClick={() => handleExportMission('gpx')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: 'var(--color-surface-high)', color: 'var(--color-primary)', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset', transition: 'all 0.3s ease' }}>
            <CheckCircle size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'gpx' ? 'GENERATING...' : 'EXPORT GPX'}
          </button>

          <button
            onClick={() => handleExportMission('geojson')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: 'var(--color-surface-highest)', color: 'var(--color-primary)', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset', transition: 'all 0.3s ease' }}>
            <FileCode2 size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'geojson' ? 'GENERATING...' : 'EXPORT GEOJSON'}
          </button>

          <button
            onClick={() => handleExportMission('pdf')}
            disabled={!!generatingMission || !detectionData}
            style={{ padding: '0.6rem 1rem', background: 'var(--color-primary)', color: 'var(--color-on-primary)', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 180 : 'unset', transition: 'all 0.3s ease' }}>
            <FileText size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission === 'pdf' ? 'GENERATING...' : 'EXPORT PDF'}
          </button>
          
          <button onClick={() => navigate('/drift')} style={{ padding: '0.6rem 1rem', background: 'var(--color-surface-container)', color: 'var(--color-text-main)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 140 : 'unset', transition: 'background 0.3s' }}>
            ABORT & RETURN
          </button>
        </div>
      </header>

      <div ref={dashboardRef} style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr', gap: '1rem', flex: 1 }}>
        <div style={{ background: 'var(--color-surface-container-low)', borderRadius: '16px', display: 'flex', flexDirection: 'column', padding: '6px', border: 'none' }}>
          <div style={{ position: 'relative', flexGrow: 1, minHeight: isMobile ? '380px' : '600px', backgroundColor: 'var(--color-surface-lowest)', borderRadius: '12px 12px 0 0', overflow: 'hidden' }}>
            <DeckGL
              initialViewState={viewState}
              onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState as typeof INITIAL_VIEW_STATE)}
              controller={true}
              layers={layers}
              getTooltip={({object}) => object && (object.properties?.id || "Detection Polygon")}
            >
              <Map mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
            </DeckGL>
          </div>
          
          <div style={{ padding: isMobile ? '1rem' : '1.5rem', display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: '1rem', alignItems: isMobile ? 'stretch' : 'center', background: 'var(--color-surface-container)', borderRadius: '0 0 12px 12px', border: 'none' }}>
            <div style={{ flexGrow: 1, display: 'flex', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: '0.8rem' }}>
              <label style={{ color: 'var(--color-text-main)', fontWeight: 'bold', fontFamily: 'var(--font-jakarta)' }}>T+ FORECAST: <span style={{ color: 'var(--color-primary)' }}>{timeSlider}h</span></label>
              <input type="range" min="0" max="72" step="24" value={timeSlider} onChange={e => setTimeSlider(Number(e.target.value))} style={{ flexGrow: 1, width: '100%', accentColor: 'var(--color-primary)' }} />
            </div>
            <button disabled={loading} onClick={() => fetchForecast(timeSlider)} style={{ padding: '0.75rem 1.2rem', background: 'var(--color-primary)', color: 'var(--color-on-primary)', fontWeight: 'bold', border: 'none', borderRadius: '9999px', cursor: 'pointer', width: isMobile ? '100%' : 'auto', transition: 'opacity 0.3s' }}>
              CALCULATE D.R.I.F.T. PHYSICS
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ background: 'var(--color-surface-container-low)', borderRadius: '16px', padding: isMobile ? '1rem' : '1.5rem', border: 'none' }}>
            <h3 style={{ margin: '0 0 1rem 0', color: 'var(--color-text-main)', fontWeight: 'bold', fontFamily: 'var(--font-jakarta)' }}>RADAR LOGS</h3>
            
            <div style={{ padding: '1rem', background: 'var(--color-surface-container)', borderRadius: '8px', borderLeft: '4px solid var(--color-tertiary)', marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--color-tertiary)' }}>Current Intel</h4>
              {loading ? <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>Scanning...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--color-text-main)' }}>
                  {detectionData ? `Detected ${detectionData.features?.length || 0} anomaly clusters.` : 'No baseline data.'}
                </div>
              )}
            </div>

            <div style={{ padding: '1rem', background: 'var(--color-surface-container)', borderRadius: '8px', borderLeft: '4px solid var(--color-primary)' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--color-primary)' }}>Simulation Output</h4>
              {loading ? <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>Processing vectors...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--color-text-main)' }}>
                  {forecastData ? `Generated ${forecastData.features?.length || 0} future D.R.I.F.T. paths.` : 'No active simulation.'}
                </div>
              )}
            </div>

            <div style={{ padding: '1rem', background: 'var(--color-surface-container)', borderRadius: '8px', borderLeft: '4px solid var(--color-secondary)', marginTop: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--color-secondary)' }}>Mission Plan</h4>
              {missionData?.features?.[0]?.properties ? (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--color-text-main)' }}>
                  {(missionData.features[0].properties.waypoint_count ?? 0)} waypoints · {(missionData.features[0].properties.total_distance_km ?? 0).toFixed(1)} km
                </div>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                  No mission plan available.
                </div>
              )}
            </div>
          </div>

          <div style={{ background: 'var(--color-surface-container-low)', borderRadius: '16px', padding: isMobile ? '1rem' : '1.5rem', border: 'none', flexGrow: 1 }}>
            <h3 style={{ margin: '0 0 1.5rem 0', color: 'var(--color-text-main)', fontWeight: 'bold', fontFamily: 'var(--font-jakarta)' }}><BarChart2 size={18} style={{ marginRight: '8px', verticalAlign: 'middle', color: 'var(--color-primary)' }} /> PLASTIC DEGRADATION MODEL</h3>
            {metricsData && metricsData.biofouling_chart_data && metricsData.biofouling_chart_data.length > 0 ? (
              <div style={{ height: '250px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metricsData.biofouling_chart_data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-surface-variant)" />
                    <XAxis dataKey="age_days" stroke="var(--color-text-muted)" />
                    <YAxis stroke="var(--color-text-muted)" />
                    <Tooltip contentStyle={{ backgroundColor: 'var(--color-surface-highest)', borderRadius: '8px', border: 'none', color: 'var(--color-text-main)', boxShadow: '0 4px 15px rgba(0,0,0,0.5)' }} />
                    <Line type="monotone" dataKey="simulated_confidence" stroke="var(--color-primary)" strokeWidth={3} dot={{ fill: 'var(--color-primary)' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-muted)', textAlign: 'center', marginTop: '2rem' }}>No atmospheric degradation metrics logged.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
