import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, BarChart2, CheckCircle, FileCode2, FileText } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import api, {
  apiErrorMessage,
  type DashboardMetrics,
  type DetectionFC,
  type ForecastFC,
  type MissionFC,
  type ExportFormat,
  type AlertsResponse,
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
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [detectionData, setDetectionData] = useState<DetectionFC | null>(null);
  const [forecastData, setForecastData] = useState<ForecastFC | null>(null);
  const [missionData, setMissionData] = useState<MissionFC | null>(null);
  const [metricsData, setMetricsData] = useState<DashboardMetrics | null>(null);
  const [alertsData, setAlertsData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [timeSlider, setTimeSlider] = useState(24);
  const [generatingMission, setGeneratingMission] = useState<ExportFormat | null>(null);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const fetchDetection = React.useCallback(async () => {
    setLoading(true);
    try {
      if (!aoi_id) return;
      setDetectionData(await api.detect(aoi_id));
    } catch (err) {
      console.error('detect:', apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [aoi_id]);

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
      setForecastData(await api.forecast(aoi_id, allowedHours));
    } catch (err) {
      console.error('forecast:', apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [aoi_id]);

  const fetchMission = React.useCallback(async () => {
    try {
      if (!aoi_id) return;
      setMissionData(await api.mission(aoi_id));
    } catch (err) {
      console.error('mission:', apiErrorMessage(err));
      setMissionData(null);
    }
  }, [aoi_id]);

  const fetchDashboardMetrics = React.useCallback(async () => {
    try {
      if (!aoi_id) return;
      setMetricsData(await api.dashboardMetrics(aoi_id));
    } catch (err) {
      console.error('metrics:', apiErrorMessage(err));
    }
  }, [aoi_id]);

  const fetchAlerts = React.useCallback(async () => {
    try {
      if (!aoi_id) return;
      setAlertsData(await api.alerts(aoi_id));
    } catch (err) {
      console.error('alerts:', apiErrorMessage(err));
      setAlertsData(null);
    }
  }, [aoi_id]);

  useEffect(() => {
    if (!aoi_id) return;
    fetchDashboardMetrics();
    fetchDetection();
    fetchForecast(timeSlider);
    fetchMission();
    fetchAlerts();
    
    // Dynamically update viewState center based on custom string or available AOIs
    if (aoi_id && aoi_id.startsWith('custom_')) {
      const parts = aoi_id.split('_');
      if (parts.length === 3) {
        setViewState(prev => ({
          ...prev,
          longitude: parseFloat(parts[1]),
          latitude: parseFloat(parts[2])
        }));
      }
    } else {
      api.listAois().then((res) => {
        const aois = res.aois;
        const matched = aois.find((a: any) => a.id === aoi_id);
        if (matched) {
          setViewState(prev => ({ ...prev, longitude: matched.center[0], latitude: matched.center[1] }));
        }
      }).catch((err) => console.error('aois:', apiErrorMessage(err)));
    }
  }, [aoi_id, fetchDashboardMetrics, fetchDetection, fetchForecast, fetchMission, fetchAlerts]);

  const handleExportMission = (format: ExportFormat) => {
    if (!aoi_id) return;
    setGeneratingMission(format);
    window.open(api.exportUrl(aoi_id, format), '_blank');
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

    // OceanTrace: deposition heatmap (landfall impact zones, red hue)
    metricsData?.deposition_heatmap && new GeoJsonLayer({
      id: 'deposition-heatmap',
      data: metricsData.deposition_heatmap as any,
      getFillColor: [239, 68, 68, 130],
      getLineColor: [220, 38, 38, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
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
          
          <button onClick={() => navigate('/drift')} style={{ padding: '0.6rem 1rem', background: '#272c35', color: '#cbd5e1', border: '1px solid #475569', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', flex: isMobile ? 1 : 'unset', minWidth: isMobile ? 140 : 'unset' }}>
            ABORT & RETURN
          </button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr', gap: '1rem' }}>
        <div style={{ background: '#272c35', borderRadius: '8px', border: '1px solid #38404d', display: 'flex', flexDirection: 'column', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
          <div style={{ position: 'relative', flexGrow: 1, minHeight: isMobile ? '380px' : '600px', backgroundColor: '#1e2229', borderRadius: '8px 8px 0 0', overflow: 'hidden' }}>
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
          
          <div style={{ padding: isMobile ? '1rem' : '1.5rem', display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: '1rem', alignItems: isMobile ? 'stretch' : 'center', background: '#2a2f38', borderRadius: '0 0 8px 8px', borderTop: '1px solid #38404d' }}>
            <div style={{ flexGrow: 1, display: 'flex', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: '0.8rem' }}>
              <label style={{ color: '#cbd5e1', fontWeight: 'bold' }}>T+ FORECAST (HOURS): <span style={{ color: '#10b981' }}>{timeSlider}h</span></label>
              <input type="range" min="0" max="72" step="24" value={timeSlider} onChange={e => setTimeSlider(Number(e.target.value))} style={{ flexGrow: 1, width: '100%', accentColor: '#10b981' }} />
            </div>
            <button disabled={loading} onClick={() => fetchForecast(timeSlider)} style={{ padding: '0.75rem 1.2rem', background: '#10b981', color: '#1e2229', fontWeight: 'bold', border: 'none', borderRadius: '4px', cursor: 'pointer', boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)', width: isMobile ? '100%' : 'auto' }}>
              CALCULATE D.R.I.F.T. PHYSICS
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {metricsData?.live_environment && (
            <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '0.75rem' : '1rem', border: '1px solid #38404d', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>SST</div>
                <div style={{ fontSize: '1.25rem', color: '#f59e0b', fontWeight: 'bold' }}>{metricsData.live_environment.sst_c.toFixed(1)}°C</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>Chl-a</div>
                <div style={{ fontSize: '1.25rem', color: '#10b981', fontWeight: 'bold' }}>{metricsData.live_environment.chl_mg_m3.toFixed(2)} <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>mg/m³</span></div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>Class</div>
                <div style={{ fontSize: '0.85rem', color: '#06b6d4', fontWeight: 'bold', marginTop: '0.4rem' }}>{metricsData.live_environment.predicted_class}</div>
              </div>
            </div>
          )}

          {alertsData && alertsData.alerts && alertsData.alerts.length > 0 && (
            <div style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.5)', borderRadius: '8px', padding: '0.75rem 1rem' }}>
              <h4 style={{ margin: '0 0 0.4rem 0', color: '#ef4444', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>⚠ Coastal Alerts ({alertsData.alerts.length})</h4>
              {alertsData.alerts.slice(0, 3).map((a) => (
                <div key={a.segment_id} style={{ fontSize: '0.75rem', color: '#fecaca', fontFamily: 'monospace' }}>
                  [{a.severity.toUpperCase()}] {a.centroid[1].toFixed(2)}°N, {a.centroid[0].toFixed(2)}°E — {a.hit_count} hits
                </div>
              ))}
            </div>
          )}

          <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '1rem' : '1.5rem', border: '1px solid #38404d', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
            <h3 style={{ margin: '0 0 1rem 0', color: '#e2e8f0', fontWeight: 'bold' }}>RADAR LOGS</h3>
            
            <div style={{ padding: '1rem', background: 'rgba(245, 158, 11, 0.1)', borderLeft: '3px solid #f59e0b', marginBottom: '1rem' }}>
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

          {metricsData?.summary && (
            <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '0.75rem' : '1rem', border: '1px solid #38404d', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.5rem' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>Patches</div>
                <div style={{ fontSize: '1.25rem', color: '#f59e0b', fontWeight: 'bold' }}>{metricsData.summary.total_patches}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>Avg Conf</div>
                <div style={{ fontSize: '1.25rem', color: '#10b981', fontWeight: 'bold' }}>{(metricsData.summary.avg_confidence * 100).toFixed(0)}%</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>Total Area</div>
                <div style={{ fontSize: '1rem', color: '#06b6d4', fontWeight: 'bold' }}>{(metricsData.summary.total_area_sq_meters / 1e6).toFixed(2)} km²</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>High-Pri</div>
                <div style={{ fontSize: '1.25rem', color: '#ef4444', fontWeight: 'bold' }}>{metricsData.summary.high_priority_targets}</div>
              </div>
            </div>
          )}

          <div style={{ background: '#272c35', borderRadius: '8px', padding: isMobile ? '1rem' : '1.5rem', border: '1px solid #38404d', flexGrow: 1, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)' }}>
            <h3 style={{ margin: '0 0 1.5rem 0', color: '#e2e8f0', fontWeight: 'bold' }}><BarChart2 size={18} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#10b981' }} /> PLASTIC DEGRADATION MODEL</h3>
            {metricsData && metricsData.biofouling_chart_data && metricsData.biofouling_chart_data.length > 0 ? (
              <div style={{ height: '250px' }}>
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
