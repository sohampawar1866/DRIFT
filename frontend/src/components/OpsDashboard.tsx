import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity, BarChart2, AlertTriangle, Download, FileText, FileCode2 } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import api, {
  apiErrorMessage,
  snapForecastHours,
  type DetectionFC,
  type ForecastFC,
  type MissionFC,
  type DashboardMetrics,
} from '../lib/api';

const INITIAL_VIEW_STATE = {
  longitude: 72.8,
  latitude: 19.0,
  zoom: 9,
  pitch: 30,
  bearing: 0,
};

export const OpsDashboard: React.FC = () => {
  const { aoi_id } = useParams<{ aoi_id: string }>();
  const navigate = useNavigate();

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [detectionData, setDetectionData] = useState<DetectionFC | null>(null);
  const [forecastData, setForecastData] = useState<ForecastFC | null>(null);
  const [missionData, setMissionData] = useState<MissionFC | null>(null);
  const [metricsData, setMetricsData] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [timeSlider, setTimeSlider] = useState(24);

  const fetchDetection = React.useCallback(async (id: string) => {
    setLoading(true); setErrorMsg(null);
    try {
      setDetectionData(await api.detect(id));
    } catch (err) {
      setErrorMsg(`Detection failed: ${apiErrorMessage(err)}`);
    } finally { setLoading(false); }
  }, []);

  const fetchForecast = React.useCallback(async (id: string, rawHours: number) => {
    const hours = snapForecastHours(rawHours);  // snap to 24/48/72
    setLoading(true); setErrorMsg(null);
    try {
      setForecastData(await api.forecast(id, hours));
    } catch (err) {
      setErrorMsg(`Forecast failed: ${apiErrorMessage(err)}`);
    } finally { setLoading(false); }
  }, []);

  const fetchMission = React.useCallback(async (id: string) => {
    try {
      setMissionData(await api.mission(id));
    } catch (err) {
      // Non-fatal; mission overlay just won't render.
      console.error('mission:', apiErrorMessage(err));
    }
  }, []);

  const fetchDashboardMetrics = React.useCallback(async (id: string) => {
    try {
      setMetricsData(await api.dashboardMetrics(id));
    } catch (err) {
      console.error('metrics:', apiErrorMessage(err));
    }
  }, []);

  const centerOnAoi = React.useCallback(async (id: string) => {
    // Custom `custom_{lon}_{lat}` id → parse directly.
    if (id.startsWith('custom_')) {
      const parts = id.split('_');
      if (parts.length === 3) {
        const lon = parseFloat(parts[1]);
        const lat = parseFloat(parts[2]);
        if (Number.isFinite(lon) && Number.isFinite(lat)) {
          setViewState(prev => ({ ...prev, longitude: lon, latitude: lat }));
          return;
        }
      }
    }
    try {
      const { aois } = await api.listAois();
      const match = aois.find(a => a.id === id);
      if (match) {
        setViewState(prev => ({
          ...prev, longitude: match.center[0], latitude: match.center[1],
        }));
      }
    } catch (err) {
      console.error('aois:', apiErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (!aoi_id) return;
    centerOnAoi(aoi_id);
    fetchDashboardMetrics(aoi_id);
    fetchDetection(aoi_id);
    fetchForecast(aoi_id, timeSlider);
    fetchMission(aoi_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aoi_id]);

  const snappedHours = snapForecastHours(timeSlider);

  const handleExport = (format: 'gpx' | 'geojson' | 'pdf') => {
    if (!aoi_id) return;
    window.open(api.exportUrl(aoi_id, format), '_blank');
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
    detectionData && new GeoJsonLayer({
      id: 'ai-detections',
      data: detectionData,
      getFillColor: [245, 158, 11, 180],
      getLineColor: [245, 158, 11, 255],
      stroked: true, filled: true, lineWidthMinPixels: 2, pickable: true,
    }),
    forecastData && new GeoJsonLayer({
      id: 'drift-forecast',
      data: forecastData,
      getFillColor: [16, 185, 129, 100],
      getLineColor: [16, 185, 129, 255],
      stroked: true, filled: true, lineWidthMinPixels: 2,
      getLineDashArray: [3, 3], dashJustified: true,
      getPointRadius: 150, pointRadiusMinPixels: 3, pointRadiusUnits: 'meters',
      pickable: true,
    }),
    missionData && new GeoJsonLayer({
      id: 'mission-route',
      data: missionData,
      getLineColor: [6, 182, 212, 255],   // cyan #06b6d4
      lineWidthMinPixels: 3,
      stroked: true, filled: false, pickable: true,
    }),
    missionWaypoints.length > 0 && new ScatterplotLayer({
      id: 'mission-waypoints',
      data: missionWaypoints,
      getPosition: (d: { position: [number, number] }) => d.position,
      getFillColor: [6, 182, 212, 255],
      getLineColor: [224, 242, 254, 255],
      getRadius: 250, radiusMinPixels: 7, stroked: true, lineWidthMinPixels: 2,
      pickable: true,
    }),
    missionWaypoints.length > 0 && new TextLayer({
      id: 'mission-waypoint-labels',
      data: missionWaypoints,
      getPosition: (d: { position: [number, number] }) => d.position,
      getText: (d: { order: number }) => String(d.order),
      getSize: 14, getColor: [15, 23, 42, 255],
      getTextAnchor: 'middle', getAlignmentBaseline: 'center',
    }),
  ].filter(Boolean);

  // --- helper for the four stat cards ------------------------------------
  const s = metricsData?.summary;
  const stat = (label: string, value: string | number | undefined | null) => (
    <div style={{
      background: '#2a2f38', borderRadius: '6px', padding: '0.75rem 1rem',
      border: '1px solid #38404d', flex: 1, minWidth: 0,
    }}>
      <div style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
        {label}
      </div>
      <div style={{ color: '#e2e8f0', fontSize: '1.15rem', fontWeight: 700, marginTop: '0.25rem' }}>
        {value === undefined || value === null || value === '' ? '—' : value}
      </div>
    </div>
  );

  return (
    <div style={{
      padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem',
      minHeight: '100vh', background: '#1e2229', color: '#e2e8f0',
      fontFamily: 'Inter, sans-serif',
    }}>
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid #38404d', paddingBottom: '1rem',
      }}>
        <h2 style={{ margin: 0, color: '#e2e8f0' }}>
          <Activity size={24} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#f59e0b' }} />
          OPERATIONS: {aoi_id}
        </h2>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => handleExport('gpx')} disabled={!detectionData}
            style={exportBtnStyle(!!detectionData, '#f59e0b')}>
            <Download size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> GPX
          </button>
          <button onClick={() => handleExport('geojson')} disabled={!detectionData}
            style={exportBtnStyle(!!detectionData, '#10b981')}>
            <FileCode2 size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> GeoJSON
          </button>
          <button onClick={() => handleExport('pdf')} disabled={!detectionData}
            style={exportBtnStyle(!!detectionData, '#06b6d4')}>
            <FileText size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> PDF
          </button>
          <button onClick={() => navigate('/drift')}
            style={{
              padding: '0.6rem 1.2rem', background: '#272c35', color: '#cbd5e1',
              border: '1px solid #475569', borderRadius: '4px', cursor: 'pointer',
              fontWeight: 'bold',
            }}>
            ABORT & RETURN
          </button>
        </div>
      </header>

      {errorMsg && (
        <div style={{
          background: 'rgba(220, 38, 38, 0.15)', borderLeft: '4px solid #dc2626',
          padding: '0.75rem 1rem', borderRadius: '4px', color: '#fecaca',
          display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <AlertTriangle size={16} /> {errorMsg}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
        <div style={{
          background: '#272c35', borderRadius: '8px', border: '1px solid #38404d',
          display: 'flex', flexDirection: 'column', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.2)',
        }}>
          <div style={{
            position: 'relative', flexGrow: 1, minHeight: '600px',
            backgroundColor: '#1e2229', borderRadius: '8px 8px 0 0', overflow: 'hidden',
          }}>
            <DeckGL
              initialViewState={viewState}
              onViewStateChange={({ viewState: vs }) => setViewState(vs as typeof viewState)}
              controller={true}
              layers={layers}
              getTooltip={(info) => {
                const object = info?.object;
                if (!object) return null;
                const o = object as { properties?: Record<string, unknown>; order?: number };
                if (typeof o.order === 'number') return `Waypoint ${o.order}`;
                return (o.properties?.id as string | undefined)
                  || (o.properties?.type as string | undefined)
                  || 'Feature';
              }}
            >
              <Map mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
            </DeckGL>
          </div>

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
                type="range" min="0" max="72" step="1"
                value={timeSlider}
                onChange={e => setTimeSlider(Number(e.target.value))}
                style={{ flexGrow: 1, accentColor: '#10b981' }}
              />
            </div>
            <button disabled={loading || !aoi_id}
              onClick={() => aoi_id && fetchForecast(aoi_id, timeSlider)}
              style={{
                padding: '0.75rem 2rem', background: '#10b981', color: '#1e2229',
                fontWeight: 'bold', border: 'none', borderRadius: '4px',
                cursor: loading ? 'wait' : 'pointer',
                boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)',
              }}>
              {loading ? 'CALCULATING…' : 'CALCULATE DRIFT PHYSICS'}
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
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
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#f59e0b' }}>Current Intel</h4>
              {loading ? (
                <p style={{ margin: 0, color: '#94a3b8' }}>Scanning…</p>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {detectionData
                    ? `Detected ${detectionData.features?.length || 0} anomaly clusters.`
                    : 'No baseline data.'}
                </div>
              )}
            </div>

            <div style={{
              padding: '1rem', background: 'rgba(16, 185, 129, 0.1)',
              borderLeft: '3px solid #10b981', marginBottom: '1rem',
            }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#10b981' }}>Simulation Output</h4>
              {loading ? (
                <p style={{ margin: 0, color: '#94a3b8' }}>Processing vectors…</p>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {forecastData
                    ? `Generated ${forecastData.features?.length || 0} future drift paths.`
                    : 'No active simulation.'}
                </div>
              )}
            </div>

            <div style={{
              padding: '1rem', background: 'rgba(6, 182, 212, 0.1)',
              borderLeft: '3px solid #06b6d4',
            }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#06b6d4' }}>Mission Plan</h4>
              {missionData?.features?.[0]?.properties ? (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#cbd5e1' }}>
                  {missionData.features[0].properties.waypoint_count ?? 0} waypoints ·
                  {' '}{(missionData.features[0].properties.total_distance_km ?? 0).toFixed(1)} km ·
                  {' '}{missionData.features[0].properties.estimated_vessel_time_hours.toFixed(1)} h
                </div>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#94a3b8' }}>
                  No mission plan available.
                </div>
              )}
            </div>
          </div>

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
              <div style={{ height: '250px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metricsData.biofouling_chart_data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#38404d" />
                    <XAxis dataKey="age_days" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip contentStyle={{ backgroundColor: '#272c35', border: '1px solid #f59e0b', color: '#e2e8f0' }} />
                    <Line type="monotone" dataKey="simulated_confidence" stroke="#10b981"
                      strokeWidth={3} dot={{ fill: '#10b981' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p style={{ color: '#94a3b8', textAlign: 'center', marginTop: '2rem' }}>
                No atmospheric degradation metrics logged.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

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
