import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { PolygonLayer, GeoJsonLayer } from '@deck.gl/layers';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, BarChart2, CheckCircle } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [detectionData, setDetectionData] = useState<any>(null);
  const [forecastData, setForecastData] = useState<any>(null);
  const [metricsData, setMetricsData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [timeSlider, setTimeSlider] = useState(24);
  const [generatingMission, setGeneratingMission] = useState(false);

  useEffect(() => {
    fetchDashboardMetrics();
    fetchDetection();
  }, [aoi_id]);

  const fetchDetection = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/detect?aoi_id=${aoi_id}`);
      setDetectionData(res.data);
    } catch (err) {
      console.error('Error fetching detect data', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchForecast = async () => {
    if (timeSlider === 0) {
      setForecastData(null);
      return;
    }
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/forecast?aoi_id=${aoi_id}&hours=${timeSlider}`);
      setForecastData(res.data);
    } catch (err) {
      console.error('Error fetching forecast data', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchDashboardMetrics = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/dashboard/metrics?aoi_id=${aoi_id}`);
      setMetricsData(res.data);
    } catch (err) {
      console.error('Error fetching metrics', err);
    }
  };

  const handleExportMission = () => {
    setGeneratingMission(true);
    window.open(`${API_BASE_URL}/api/v1/mission/export?aoi_id=${aoi_id}&format=gpx`, '_blank');
    setTimeout(() => setGeneratingMission(false), 2000);
  };

  // Rendering Layers
  const layers = [
    // Live detection polygons (what the AI found)
    detectionData && new GeoJsonLayer({
      id: 'ai-detections',
      data: detectionData,
      getFillColor: [255, 23, 68, 180], // Red polygons
      getLineColor: [255, 23, 68, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
      pickable: true
    }),

    // Forecast polygons (where it is going)
    forecastData && new GeoJsonLayer({
      id: 'drift-forecast',
      data: forecastData,
      getFillColor: [0, 229, 255, 100], // Cyan ghost polygons
      getLineColor: [0, 229, 255, 255],
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2,
      getLineDashArray: [3, 3], // Dashed outlines for forecast
      dashJustified: true
    })
  ].filter(Boolean);

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem', minHeight: '100vh', background: '#0a0a0a', color: '#fff' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #333', paddingBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: '#00e5ff' }}><Activity size={24} style={{ marginRight: '8px', verticalAlign: 'middle' }} /> OPERATIONS: {aoi_id}</h2>
        
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button 
            onClick={handleExportMission}
            disabled={generatingMission || !detectionData}
            style={{ padding: '0.6rem 1.5rem', background: '#ff1744', color: 'white', border: 'none', borderRadius: '4px', cursor: (generatingMission || !detectionData) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}>
            <CheckCircle size={16} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            {generatingMission ? 'GENERATING...' : 'EXPORT GPX MISSION'}
          </button>
          
          <button onClick={() => navigate('/')} style={{ padding: '0.6rem 1.5rem', background: '#333', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
            ABORT & RETURN
          </button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
        <div style={{ background: '#111', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', flexGrow: 1, minHeight: '600px', backgroundColor: '#000', borderRadius: '8px 8px 0 0', overflow: 'hidden' }}>
            <DeckGL
              initialViewState={viewState}
              onViewStateChange={({viewState}) => setViewState(viewState)}
              controller={true}
              layers={layers}
              getTooltip={({object}) => object && (object.properties?.id || "Detection Polygon")}
            >
              <Map mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
            </DeckGL>
          </div>
          
          <div style={{ padding: '1.5rem', display: 'flex', gap: '2rem', alignItems: 'center', background: '#1a1a1a', borderRadius: '0 0 8px 8px', borderTop: '1px solid #333' }}>
            <div style={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <label style={{ color: '#aaa', fontWeight: 'bold' }}>T+ FORECAST (HOURS): <span style={{ color: '#00e5ff' }}>{timeSlider}h</span></label>
              <input type="range" min="0" max="72" step="24" value={timeSlider} onChange={e => setTimeSlider(Number(e.target.value))} style={{ flexGrow: 1, accentColor: '#00e5ff' }} />
            </div>
            <button disabled={loading} onClick={fetchForecast} style={{ padding: '0.75rem 2rem', background: '#00e5ff', color: '#000', fontWeight: 'bold', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
              CALCULATE DRIFT PHYSICS
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ background: '#111', borderRadius: '8px', padding: '1.5rem', border: '1px solid #333' }}>
            <h3 style={{ margin: '0 0 1rem 0', color: '#aaa' }}>RADAR LOGS</h3>
            
            <div style={{ padding: '1rem', background: 'rgba(255, 23, 68, 0.1)', borderLeft: '3px solid #ff1744', marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#ff1744' }}>Current Intel</h4>
              {loading ? <p style={{ margin: 0, color: '#aaa' }}>Scanning...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#fff' }}>
                  {detectionData ? `Detected ${detectionData.features?.length || 0} anomaly clusters.` : 'No baseline data.'}
                </div>
              )}
            </div>

            <div style={{ padding: '1rem', background: 'rgba(0, 229, 255, 0.1)', borderLeft: '3px solid #00e5ff' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#00e5ff' }}>Simulation Output</h4>
              {loading ? <p style={{ margin: 0, color: '#aaa' }}>Processing vectors...</p> : (
                <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#fff' }}>
                  {forecastData ? `Generated ${forecastData.features?.length || 0} future drift paths.` : 'No active simulation.'}
                </div>
              )}
            </div>
          </div>

          <div style={{ background: '#111', borderRadius: '8px', padding: '1.5rem', border: '1px solid #333', flexGrow: 1 }}>
            <h3 style={{ margin: '0 0 1.5rem 0', color: '#aaa' }}><BarChart2 size={18} style={{ marginRight: '8px', verticalAlign: 'middle' }} /> PLASTIC DEGRADATION MODEL</h3>
            {metricsData && metricsData.length > 0 ? (
              <div style={{ height: '250px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metricsData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="time" stroke="#aaa" />
                    <YAxis stroke="#aaa" />
                    <Tooltip contentStyle={{ backgroundColor: '#222', border: '1px solid #00e5ff' }} />
                    <Line type="monotone" dataKey="value" stroke="#00e5ff" strokeWidth={3} dot={{ fill: '#00e5ff' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p style={{ color: '#666', textAlign: 'center', marginTop: '2rem' }}>No atmospheric degradation metrics logged.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
