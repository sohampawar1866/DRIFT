import axios, { AxiosError } from 'axios';

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
});

export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string; error?: string }>;
    if (ax.response?.data?.detail) return String(ax.response.data.detail);
    if (ax.response?.data?.error) return String(ax.response.data.error);
    if (ax.code === 'ECONNABORTED') return 'Request timed out';
    if (ax.message) return ax.message;
  }
  return err instanceof Error ? err.message : 'Unknown error';
}

export type ForecastHours = 24 | 48 | 72;
export type ExportFormat = 'gpx' | 'geojson' | 'pdf';

export interface AoiEntry {
  id: string;
  name?: string;
  center: [number, number];
  bounds?: [[number, number], [number, number]];
}

export interface AoiListResponse {
  aois: AoiEntry[];
}

export interface DetectionFC extends GeoJSON.FeatureCollection {
  features: Array<GeoJSON.Feature<GeoJSON.Polygon, {
    id?: string;
    confidence?: number;
    area_sq_meters?: number;
    age_days?: number;
    type?: string;
    fraction_plastic?: number;
  }>>;
}

export interface ForecastFC extends GeoJSON.FeatureCollection {}

export interface MissionFC extends GeoJSON.FeatureCollection {
  features: Array<GeoJSON.Feature<GeoJSON.LineString, {
    mission_id?: string;
    estimated_vessel_time_hours?: number;
    priority?: string;
    total_distance_km?: number;
    waypoint_count?: number;
    waypoints?: Array<{
      order: number;
      lon: number;
      lat: number;
      arrival_hour: number;
      priority_score: number;
    }>;
  }>>;
}

export interface DashboardMetrics {
  summary?: {
    total_area_sq_meters: number;
    total_patches: number;
    avg_confidence: number;
    high_priority_targets: number;
  };
  biofouling_chart_data: Array<{ age_days: number; simulated_confidence: number }>;
  live_environment?: {
    sst_c: number;
    chl_mg_m3: number;
    predicted_class: string;
  };
  deposition_heatmap?: GeoJSON.FeatureCollection;
}

export interface AlertEntry {
  segment_id: string;
  centroid: [number, number];
  hit_count: number;
  severity: 'low' | 'elevated' | 'critical';
  aoi_id?: string | null;
  timestamp?: string | null;
}

export interface AlertsResponse {
  alerts: AlertEntry[];
  deposited_count?: number;
  dispatch_report?: { dispatched: number; logged: number; alerts: number };
  degraded?: boolean;
  reason?: string;
}

export interface SearchRecord {
  id: string;
  date: string;
  density: number;
  center: [number, number];
  coordinates: Array<[number, number]>;
  driftVector: [number, number];
}

export async function listAois(): Promise<AoiListResponse> {
  const res = await client.get<AoiListResponse>('/api/v1/aois');
  return res.data;
}

export async function detect(aoi_id: string): Promise<DetectionFC> {
  const res = await client.get<DetectionFC>('/api/v1/detect', {
    params: { aoi_id },
  });
  return res.data;
}

export async function forecast(aoi_id: string, hours: ForecastHours): Promise<ForecastFC> {
  const res = await client.get<ForecastFC>('/api/v1/forecast', {
    params: { aoi_id, hours },
  });
  return res.data;
}

export async function mission(aoi_id: string): Promise<MissionFC> {
  const res = await client.get<MissionFC>('/api/v1/mission', {
    params: { aoi_id },
  });
  return res.data;
}

export async function dashboardMetrics(aoi_id: string): Promise<DashboardMetrics> {
  const res = await client.get<DashboardMetrics>('/api/v1/dashboard/metrics', {
    params: { aoi_id },
  });
  return res.data;
}

export function exportUrl(aoi_id: string, format: ExportFormat): string {
  const u = new URL('/api/v1/mission/export', API_BASE_URL);
  u.searchParams.set('aoi_id', aoi_id);
  u.searchParams.set('format', format);
  return u.toString();
}

export function snapForecastHours(h: number): ForecastHours {
  const legal: ForecastHours[] = [24, 48, 72];
  return legal.reduce<ForecastHours>(
    (best, cur) => (Math.abs(cur - h) < Math.abs(best - h) ? cur : best),
    24,
  );
}

export async function alerts(aoi_id: string): Promise<AlertsResponse> {
  const res = await client.get<AlertsResponse>('/api/v1/alerts', {
    params: { aoi_id },
  });
  return res.data;
}

export async function trackerCoastline(): Promise<GeoJSON.FeatureCollection> {
  const res = await client.get<GeoJSON.FeatureCollection>('/api/v1/tracker/coastline');
  return res.data;
}

export async function trackerSearch(): Promise<SearchRecord[]> {
  const res = await client.get<SearchRecord[]>('/api/v1/tracker/search');
  return res.data;
}

export async function trackerSubmit(coordinates: Array<[number, number]>): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>('/api/v1/tracker/search', { coordinates });
  return res.data;
}

export async function trackerRevisit(id: string): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>(`/api/v1/tracker/revisit/${encodeURIComponent(id)}`);
  return res.data;
}

export async function trackerClearHistory(): Promise<{ status: string; cleared: number; remaining: number }> {
  const res = await client.delete<{ status: string; cleared: number; remaining: number }>('/api/v1/tracker/search');
  return res.data;
}

const api = {
  API_BASE_URL,
  apiErrorMessage,
  listAois,
  detect,
  forecast,
  mission,
  dashboardMetrics,
  alerts,
  exportUrl,
  snapForecastHours,
  trackerCoastline,
  trackerSearch,
  trackerSubmit,
  trackerRevisit,
  trackerClearHistory,
};

export default api;
