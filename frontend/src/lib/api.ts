/**
 * Central API client for DRIFT frontend.
 *
 * Single source of truth for:
 *   - The backend base URL (env var VITE_API_BASE_URL, defaulting to localhost:8000)
 *   - Every endpoint call (typed request + response)
 *   - Axios instance with a single timeout + error pattern
 *
 * Components import named functions (e.g. `api.detect(aoi_id)`) instead of
 * calling `axios.get(...)` directly.  A URL change touches only this file.
 */
import axios, { AxiosError } from 'axios';

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
});

/** Stable error message regardless of whether the error is a network
 *  failure, timeout, or structured backend {detail} response. */
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

// ---------------------------------------------------------------- types
// Adapter shapes returned by the backend service layer. Extra/optional
// fields are tolerated (pydantic does not reach the API surface here).

export interface AoiEntry {
  id: string;
  name?: string;
  center: [number, number];           // [lon, lat]
  bounds?: [[number, number], [number, number]];
}
export interface AoiListResponse { aois: AoiEntry[] }

export interface DetectionProps {
  id: string;
  confidence: number;
  area_sq_meters: number;
  age_days: number;
  type: string;                        // always "macroplastic" today
  fraction_plastic?: number;
}
export interface DetectionFeature {
  type: 'Feature';
  geometry: GeoJSON.Polygon;
  properties: DetectionProps;
}
export interface DetectionFC {
  type: 'FeatureCollection';
  features: DetectionFeature[];
}

export interface ForecastFC extends GeoJSON.FeatureCollection {
  // Features carry `properties.forecast_hour` and `properties.type` in
  // {'density_contour', 'particle'}; we keep them as generic GeoJSON
  // so deck.gl can render directly.
}

export interface MissionFC extends GeoJSON.FeatureCollection {
  features: Array<GeoJSON.Feature<GeoJSON.LineString, {
    mission_id: string;
    estimated_vessel_time_hours: number;
    priority: string;
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
}

export interface SearchRecord {
  id: string;
  date: string;
  density: number;
  center: [number, number];
  coordinates: Array<[number, number]>;
  driftVector: [number, number];
}

export type ExportFormat = 'gpx' | 'geojson' | 'pdf';
export type ForecastHours = 24 | 48 | 72;

// ---------------------------------------------------------------- v1 API

export async function listAois(): Promise<AoiListResponse> {
  const res = await client.get<AoiListResponse>('/api/v1/aois');
  return res.data;
}

export async function detect(
  aoi_id: string,
  s2_tile_path?: string,
): Promise<DetectionFC> {
  const res = await client.get<DetectionFC>('/api/v1/detect', {
    params: { aoi_id, s2_tile_path },
  });
  return res.data;
}

export async function forecast(
  aoi_id: string,
  hours: ForecastHours,
): Promise<ForecastFC> {
  const res = await client.get<ForecastFC>('/api/v1/forecast', {
    params: { aoi_id, hours },
  });
  return res.data;
}

export async function mission(aoi_id: string): Promise<MissionFC> {
  const res = await client.get<MissionFC>('/api/v1/mission', { params: { aoi_id } });
  return res.data;
}

export async function dashboardMetrics(aoi_id: string): Promise<DashboardMetrics> {
  const res = await client.get<DashboardMetrics>('/api/v1/dashboard/metrics', {
    params: { aoi_id },
  });
  return res.data;
}

/** Build the absolute export URL so callers can `window.open` or embed as <a href>. */
export function exportUrl(aoi_id: string, format: ExportFormat): string {
  const u = new URL('/api/v1/mission/export', API_BASE_URL);
  u.searchParams.set('aoi_id', aoi_id);
  u.searchParams.set('format', format);
  return u.toString();
}

/** Snap an arbitrary slider value to the nearest legal backend horizon.
 *  Frontend sliders can stay continuous; backend only accepts {24,48,72}. */
export function snapForecastHours(h: number): ForecastHours {
  const legal: ForecastHours[] = [24, 48, 72];
  return legal.reduce<ForecastHours>(
    (best, cur) => (Math.abs(cur - h) < Math.abs(best - h) ? cur : best),
    24,
  );
}

// ---------------------------------------------------------------- tracker

export async function trackerCoastline(): Promise<GeoJSON.FeatureCollection> {
  const res = await client.get<GeoJSON.FeatureCollection>('/api/v1/tracker/coastline');
  return res.data;
}

export async function trackerSearch(): Promise<SearchRecord[]> {
  const res = await client.get<SearchRecord[]>('/api/v1/tracker/search');
  return res.data;
}

export async function trackerSubmit(
  coordinates: Array<[number, number]>,
): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>('/api/v1/tracker/search', { coordinates });
  return res.data;
}

export async function trackerRevisit(id: string): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>(`/api/v1/tracker/revisit/${encodeURIComponent(id)}`);
  return res.data;
}

// Namespaced default export for readable call sites: `api.detect(id)`.
const api = {
  API_BASE_URL,
  apiErrorMessage,
  listAois,
  detect,
  forecast,
  mission,
  dashboardMetrics,
  exportUrl,
  snapForecastHours,
  trackerCoastline,
  trackerSearch,
  trackerSubmit,
  trackerRevisit,
};
export default api;
