import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DeckGL from '@deck.gl/react';
import MapLibreMap from 'react-map-gl/maplibre';
import { LineLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  ArrowLeft,
} from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import api, { apiErrorMessage } from '../lib/api';

type HistoryRecord = {
  id: string;
  coordinates: [number, number][];
  center: [number, number];
  driftVector: [number, number];
  density: number;
  date: string;
};

const INITIAL_VIEW_STATE = {
  longitude: 80,
  latitude: 15,
  zoom: 4.4,
  pitch: 0,
  bearing: 0,
};

const RISK_COLORS = {
  critical: '#f59e0b',
  elevated: '#facc15',
  low: '#10b981',
};

const parseDateOnly = (raw: string) => {
  const day = (raw || '').split(' ')[0];
  const d = new Date(day);
  return Number.isNaN(d.getTime()) ? null : d;
};

const toDayKey = (raw: string) => {
  const day = (raw || '').split(' ')[0];
  return day || 'unknown';
};

const toPercent = (v: number) => `${(v * 100).toFixed(1)}%`;

export const IntelDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [dayWindow, setDayWindow] = useState<'7' | '30' | 'all'>('30');
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    api
      .trackerSearch()
      .then((res) => setRecords(Array.isArray(res) ? res : []))
      .catch((err) => {
        console.error('tracker/search:', apiErrorMessage(err));
        setRecords([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const filteredRecords = useMemo(() => {
    if (dayWindow === 'all') return records;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - Number(dayWindow));
    return records.filter((r) => {
      const d = parseDateOnly(r.date);
      return d ? d >= cutoff : false;
    });
  }, [records, dayWindow]);

  useEffect(() => {
    if (!filteredRecords.length) return;
    const avgLon = filteredRecords.reduce((acc, r) => acc + r.center[0], 0) / filteredRecords.length;
    const avgLat = filteredRecords.reduce((acc, r) => acc + r.center[1], 0) / filteredRecords.length;
    const frame = window.requestAnimationFrame(() => {
      setViewState((prev) => ({ ...prev, longitude: avgLon, latitude: avgLat }));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [filteredRecords]);

  const dailySeries = useMemo(() => {
    const dayMap = new Map<string, { day: string; deployments: number; avgDensity: number; peakDensity: number }>();
    for (const r of filteredRecords) {
      const key = toDayKey(r.date);
      if (!dayMap.has(key)) {
        dayMap.set(key, { day: key, deployments: 0, avgDensity: 0, peakDensity: 0 });
      }
      const row = dayMap.get(key)!;
      row.deployments += 1;
      row.avgDensity += r.density;
      row.peakDensity = Math.max(row.peakDensity, r.density);
    }
    const rows = Array.from(dayMap.values()).map((r) => ({
      ...r,
      avgDensity: r.deployments > 0 ? r.avgDensity / r.deployments : 0,
    }));
    rows.sort((a, b) => a.day.localeCompare(b.day));
    return rows;
  }, [filteredRecords]);

  const riskSplit = useMemo(() => {
    let critical = 0;
    let elevated = 0;
    let low = 0;
    for (const r of filteredRecords) {
      if (r.density > 0.7) critical += 1;
      else if (r.density > 0.4) elevated += 1;
      else low += 1;
    }
    return [
      { name: 'Critical', value: critical, color: RISK_COLORS.critical },
      { name: 'Elevated', value: elevated, color: RISK_COLORS.elevated },
      { name: 'Low', value: low, color: RISK_COLORS.low },
    ];
  }, [filteredRecords]);

  const hotspotRows = useMemo(() => {
    return [...filteredRecords]
      .sort((a, b) => b.density - a.density)
      .slice(0, 8)
      .map((r) => ({
        id: r.id,
        density: r.density,
        day: toDayKey(r.date),
        lat: r.center[1],
        lon: r.center[0],
      }));
  }, [filteredRecords]);

  const kpi = useMemo(() => {
    const total = filteredRecords.length;
    const avgDensity = total ? filteredRecords.reduce((acc, r) => acc + r.density, 0) / total : 0;
    const maxDensity = total ? Math.max(...filteredRecords.map((r) => r.density)) : 0;
    const activeDays = new Set(filteredRecords.map((r) => toDayKey(r.date))).size;
    return { total, avgDensity, maxDensity, activeDays };
  }, [filteredRecords]);

  const layers = useMemo(() => {
    return [
      new ScatterplotLayer({
        id: 'intel-heat-points',
        data: filteredRecords,
        getPosition: (d: HistoryRecord) => d.center,
        getRadius: (d: HistoryRecord) => 6000 + d.density * 14000,
        radiusMinPixels: 10,
        getFillColor: (d: HistoryRecord) => {
          if (d.density > 0.7) return [245, 158, 11, 170];
          if (d.density > 0.4) return [250, 204, 21, 140];
          return [16, 185, 129, 120];
        },
        pickable: true,
        opacity: 0.7,
      }),
      new LineLayer({
        id: 'intel-drift-lines',
        data: filteredRecords,
        getSourcePosition: (d: HistoryRecord) => d.center,
        getTargetPosition: (d: HistoryRecord) => d.driftVector,
        getColor: [245, 158, 11, 180],
        getWidth: 3,
        pickable: true,
      }),
      new PolygonLayer({
        id: 'intel-footprints',
        data: filteredRecords,
        getPolygon: (d: HistoryRecord) => d.coordinates,
        getFillColor: [16, 185, 129, 45],
        getLineColor: [16, 185, 129, 210],
        lineWidthMinPixels: 1,
        stroked: true,
        filled: true,
      }),
    ];
  }, [filteredRecords]);

  return (
    <main style={{ minHeight: '100vh', background: '#1e2229', color: '#e2e8f0', fontFamily: 'Inter, sans-serif', padding: isMobile ? '0.9rem' : '1.2rem 1.6rem 2rem 1.6rem', overflowX: 'hidden' }}>
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 16,
            marginBottom: 16,
            borderBottom: '1px solid #38404d',
            paddingBottom: 14,
          }}
        >
          <div>
            <h1 className="type-page-title" style={{ margin: 0, letterSpacing: '0.03em' }}>Operational Intelligence Dashboard</h1>
            <div className="type-body-md" style={{ color: '#9aa7ba', marginTop: 6 }}>
              Day-wise deployment analytics, heat signatures, and hotspot ranking from tracker history.
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
            <select
              value={dayWindow}
              onChange={(e) => setDayWindow(e.target.value as '7' | '30' | 'all')}
              style={{
                background: '#273140',
                color: '#e2e8f0',
                border: '1px solid #3f4d61',
                borderRadius: 8,
                padding: '8px 10px',
                fontWeight: 600,
                minWidth: isMobile ? '100%' : undefined,
              }}
            >
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="all">All time</option>
            </select>

            <button
              onClick={() => navigate('/drift')}
              style={{
                background: '#1f7a5d',
                color: '#eaf8f3',
                border: '1px solid #279a74',
                borderRadius: 8,
                padding: '8px 12px',
                fontWeight: 700,
                cursor: 'pointer',
                flex: isMobile ? 1 : undefined,
              }}
            >
              Open Map
            </button>
            <button
              onClick={() => navigate('/drift/history')}
              style={{
                background: '#2a3340',
                color: '#e2e8f0',
                border: '1px solid #415063',
                borderRadius: 8,
                padding: '8px 12px',
                fontWeight: 700,
                cursor: 'pointer',
                flex: isMobile ? 1 : undefined,
              }}
            >
              History
            </button>
            <button
              onClick={() => navigate('/')}
              style={{
                background: '#2a3340',
                color: '#e2e8f0',
                border: '1px solid #415063',
                borderRadius: 8,
                padding: '8px 12px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                flex: isMobile ? 1 : undefined,
                justifyContent: 'center',
              }}
            >
              <ArrowLeft size={14} /> Home
            </button>
          </div>
        </header>

        <section id="overview" style={{ marginBottom: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {[
              { label: 'Deployments', value: kpi.total.toString() },
              { label: 'Avg Density', value: toPercent(kpi.avgDensity) },
              { label: 'Peak Density', value: toPercent(kpi.maxDensity) },
              { label: 'Active Days', value: kpi.activeDays.toString() },
            ].map((card) => (
              <div
                key={card.label}
                style={{
                  background: '#262f3b',
                  border: '1px solid #3b4758',
                  borderRadius: 12,
                  padding: '14px 16px',
                }}
              >
                <div style={{ color: '#93a1b5', fontSize: 12, marginBottom: 6 }}>{card.label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#f3f7fb' }}>{card.value}</div>
              </div>
            ))}
          </div>
        </section>

        <section id="map-intel" style={{ marginBottom: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 2fr) minmax(280px, 1fr)', gap: 12 }}>
            <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ padding: '10px 12px', borderBottom: '1px solid #3b4758', fontWeight: 700, color: '#d5dfeb' }}>
                Heat Signature Map
              </div>
              <div style={{ height: isMobile ? 320 : 430, position: 'relative' }}>
                <DeckGL
                  style={{ position: 'absolute', inset: '0' }}
                  initialViewState={viewState}
                  onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState as typeof INITIAL_VIEW_STATE)}
                  controller={true}
                  layers={layers}
                  getTooltip={({ object }) => {
                    const entry = object as HistoryRecord | undefined;
                    if (!entry?.id) return null;
                    return {
                      text: `${entry.id}\nDensity: ${(entry.density * 100).toFixed(1)}%\nDate: ${entry.date}`,
                    };
                  }}
                >
                  <MapLibreMap mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
                </DeckGL>
              </div>
            </div>

            <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, padding: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Risk Distribution</div>
              {kpi.total === 0 ? (
                <div style={{ color: '#8f9caf', fontSize: 13 }}>No deployments for selected window.</div>
              ) : (
                <div style={{ height: 260, minWidth: 0 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={riskSplit} dataKey="value" nameKey="name" outerRadius={88} innerRadius={45}>
                        {riskSplit.map((r) => (
                          <Cell key={r.name} fill={r.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value, name) => [`${value ?? 0}`, name]}
                        contentStyle={{ backgroundColor: '#1f2732', border: '1px solid #364457', color: '#dce6f3' }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div style={{ marginTop: 8, fontSize: 12, color: '#9aa7ba', lineHeight: 1.5 }}>
                <div>Critical: density {'>'} 70%</div>
                <div>Elevated: density 40%-70%</div>
                <div>Low: density {'<='} 40%</div>
              </div>
            </div>
          </div>
        </section>

        <section id="day-trends" style={{ marginBottom: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
            <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, padding: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Average Density By Day</div>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={dailySeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3a4657" />
                    <XAxis dataKey="day" stroke="#9fb0c6" />
                    <YAxis stroke="#9fb0c6" />
                    <Tooltip
                      formatter={(v) => `${(Number(v ?? 0) * 100).toFixed(1)}%`}
                      contentStyle={{ backgroundColor: '#1f2732', border: '1px solid #364457', color: '#dce6f3' }}
                    />
                    <Line type="monotone" dataKey="avgDensity" stroke="#10b981" strokeWidth={3} dot={{ fill: '#10b981' }} />
                    <Line type="monotone" dataKey="peakDensity" stroke="#f59e0b" strokeWidth={2} dot={{ fill: '#f59e0b' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, padding: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Deployments Per Day</div>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dailySeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3a4657" />
                    <XAxis dataKey="day" stroke="#9fb0c6" />
                    <YAxis stroke="#9fb0c6" />
                    <Tooltip contentStyle={{ backgroundColor: '#1f2732', border: '1px solid #364457', color: '#dce6f3' }} />
                    <Bar dataKey="deployments" fill="#38bdf8" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </section>

        <section id="hotspots" style={{ marginBottom: 18 }}>
          <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Top Hotspots (Sorted By Density)</div>
            {hotspotRows.length === 0 ? (
              <div style={{ color: '#8f9caf', fontSize: 13 }}>No hotspot data in selected period.</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', color: '#96a6bd', borderBottom: '1px solid #3d495b' }}>
                      <th style={{ padding: '8px 6px' }}>ID</th>
                      <th style={{ padding: '8px 6px' }}>Density</th>
                      <th style={{ padding: '8px 6px' }}>Date</th>
                      <th style={{ padding: '8px 6px' }}>Lat</th>
                      <th style={{ padding: '8px 6px' }}>Lon</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hotspotRows.map((row) => (
                      <tr key={row.id} style={{ borderBottom: '1px solid #334052' }}>
                        <td style={{ padding: '8px 6px', color: '#e6edf6', fontWeight: 700 }}>{row.id}</td>
                        <td style={{ padding: '8px 6px', color: '#f59e0b' }}>{toPercent(row.density)}</td>
                        <td style={{ padding: '8px 6px', color: '#d0d9e5' }}>{row.day}</td>
                        <td style={{ padding: '8px 6px', color: '#d0d9e5' }}>{row.lat.toFixed(4)}</td>
                        <td style={{ padding: '8px 6px', color: '#d0d9e5' }}>{row.lon.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <section id="recent-ops">
          <div style={{ background: '#262f3b', border: '1px solid #3b4758', borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Recent Deployments</div>
            {loading ? (
              <div style={{ color: '#9aa7ba', fontSize: 13 }}>Loading mission logs...</div>
            ) : filteredRecords.length === 0 ? (
              <div style={{ color: '#9aa7ba', fontSize: 13 }}>No deployment records yet.</div>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {[...filteredRecords]
                  .sort((a, b) => b.date.localeCompare(a.date))
                  .slice(0, 10)
                  .map((r) => (
                    <div
                      key={r.id}
                      style={{
                        background: '#212a36',
                        border: '1px solid #334154',
                        borderRadius: 8,
                        padding: '10px 12px',
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                        gap: 8,
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ fontWeight: 700 }}>{r.id}</div>
                      <div style={{ color: '#9fb0c6' }}>{toDayKey(r.date)}</div>
                      <div style={{ color: '#10b981' }}>{r.center[1].toFixed(4)}N, {r.center[0].toFixed(4)}E</div>
                      <div style={{ color: '#f59e0b', fontWeight: 700 }}>{toPercent(r.density)}</div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </section>
    </main>
  );
};
