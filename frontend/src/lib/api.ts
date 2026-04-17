import axios, { AxiosError } from 'axios';

const RAW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();
const RAW_API_PREFIX = import.meta.env.VITE_API_PREFIX?.trim();

function normalizePrefix(prefix: string): string {
  if (!prefix) return '/api/v1';
  const withLeadingSlash = prefix.startsWith('/') ? prefix : `/${prefix}`;
  return withLeadingSlash.replace(/\/+$/, '') || '/api/v1';
}

function normalizeBaseUrl(baseUrl?: string): string {
  if (!baseUrl) return '';
  return baseUrl.replace(/\/+$/, '');
}

function isAbsoluteHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function basePathname(baseUrl: string): string {
  if (!baseUrl) return '';
  if (isAbsoluteHttpUrl(baseUrl)) {
    try {
      return new URL(baseUrl).pathname.replace(/\/+$/, '');
    } catch {
      return '';
    }
  }
  return baseUrl.replace(/\/+$/, '');
}

function baseAlreadyIncludesPrefix(baseUrl: string, prefix: string): boolean {
  const pathname = basePathname(baseUrl);
  if (!pathname || pathname === '/') return false;
  return pathname === prefix || pathname.endsWith(prefix);
}

const API_PREFIX = normalizePrefix(RAW_API_PREFIX || '/api/v1');
export const API_BASE_URL: string = normalizeBaseUrl(RAW_API_BASE_URL || '');
const SHOULD_PREPEND_PREFIX = !baseAlreadyIncludesPrefix(API_BASE_URL, API_PREFIX);

function endpoint(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return SHOULD_PREPEND_PREFIX ? `${API_PREFIX}${cleanPath}` : cleanPath;
}

const client = axios.create({
<<<<<<< HEAD
  baseURL: API_BASE_URL || undefined,
  timeout: 20_000,
=======
  baseURL: API_BASE_URL,
  timeout: 120_000,
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
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
export type Bbox = [number, number, number, number];

export interface SpatialQuery {
  bbox?: Bbox;
  polygon?: Array<[number, number]>;
}

export interface AoiEntry {
  id: string;
  name?: string;
  center: [number, number];
  bounds?: [[number, number], [number, number]];
}

<<<<<<< HEAD
export interface AoiListResponse {
  aois: AoiEntry[];
=======
export interface DetectionProps {
  id: string;
  confidence: number;
  area_sq_meters: number;
  age_days: number;
  type: string;                        // always "macroplastic" today
  fraction_plastic?: number;
  water_temp?: number;
  chlorophyll?: number;
  fdi?: number;
  ndvi?: number;
  k_factor?: number;
  conf_range?: [number, number];
  class_est?: string;
}
export interface DetectionFeature {
  type: 'Feature';
  geometry: GeoJSON.Polygon;
  properties: DetectionProps;
}
export interface DetectionFC {
  type: 'FeatureCollection';
  features: DetectionFeature[];
  bbox?: [number, number, number, number]; // [min_lon, min_lat, max_lon, max_lat]
  visual_url?: string;
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
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

export type ForecastFC = GeoJSON.FeatureCollection;

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
    water_temp?: number;
    chlorophyll?: number;
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

<<<<<<< HEAD
=======
export type ForecastHours = 24 | 48 | 72 | 168 | 360;

// ---------------------------------------------------------------- v1 API

>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
export async function listAois(): Promise<AoiListResponse> {
  const res = await client.get<AoiListResponse>(endpoint('/aois'));
  return res.data;
}

<<<<<<< HEAD
function spatialParams(spatial?: SpatialQuery): Record<string, string> {
  const params: Record<string, string> = {};
  if (spatial?.bbox) {
    params.bbox = spatial.bbox.join(',');
  }
  if (spatial?.polygon && spatial.polygon.length >= 3) {
    params.polygon = JSON.stringify(spatial.polygon);
  }
  return params;
}

export async function detect(aoi_id: string, spatial?: SpatialQuery): Promise<DetectionFC> {
  const res = await client.get<DetectionFC>(endpoint('/detect'), {
    params: { aoi_id, ...spatialParams(spatial) },
=======
export async function detect(
  aoi_id: string,
  lat?: number,
  lon?: number,
  s2_tile_path?: string,
): Promise<DetectionFC> {
  const res = await client.get<DetectionFC>('/api/v1/detect', {
    params: { aoi_id, lat, lon, s2_tile_path },
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
  });
  return res.data;
}

<<<<<<< HEAD
export async function forecast(aoi_id: string, hours: ForecastHours, spatial?: SpatialQuery): Promise<ForecastFC> {
  const res = await client.get<ForecastFC>(endpoint('/forecast'), {
    params: { aoi_id, hours, ...spatialParams(spatial) },
=======
export async function forecast(
  aoi_id: string,
  hours: ForecastHours,
  lat?: number,
  lon?: number,
): Promise<ForecastFC> {
  const res = await client.get<ForecastFC>('/api/v1/forecast', {
    params: { aoi_id, hours, lat, lon },
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
  });
  return res.data;
}

export async function mission(aoi_id: string, spatial?: SpatialQuery): Promise<MissionFC> {
  const res = await client.get<MissionFC>(endpoint('/mission'), {
    params: { aoi_id, ...spatialParams(spatial) },
  });
  return res.data;
}

export async function dashboardMetrics(aoi_id: string, spatial?: SpatialQuery): Promise<DashboardMetrics> {
  const res = await client.get<DashboardMetrics>(endpoint('/dashboard/metrics'), {
    params: { aoi_id, ...spatialParams(spatial) },
  });
  return res.data;
}

export function exportUrl(aoi_id: string, format: ExportFormat, spatial?: SpatialQuery): string {
  const params = new URLSearchParams();
  params.set('aoi_id', aoi_id);
  params.set('format', format);
  if (spatial?.bbox) {
    params.set('bbox', spatial.bbox.join(','));
  }
  if (spatial?.polygon && spatial.polygon.length >= 3) {
    params.set('polygon', JSON.stringify(spatial.polygon));
  }

  const path = endpoint('/mission/export');
  if (isAbsoluteHttpUrl(API_BASE_URL)) {
    const absoluteBase = API_BASE_URL.endsWith('/') ? API_BASE_URL : `${API_BASE_URL}/`;
    const url = new URL(path, absoluteBase);
    url.search = params.toString();
    return url.toString();
  }

  const basePath = API_BASE_URL ? API_BASE_URL.replace(/\/+$/, '') : '';
  const combinedPath = `${basePath}${path}`;
  const query = params.toString();
  return query ? `${combinedPath}?${query}` : combinedPath;
}

export function snapForecastHours(h: number): ForecastHours {
  const legal: ForecastHours[] = [24, 48, 72, 168, 360];
  return legal.reduce<ForecastHours>(
    (best, cur) => (Math.abs(cur - h) < Math.abs(best - h) ? cur : best),
    24,
  );
}

export async function trackerCoastline(): Promise<GeoJSON.FeatureCollection> {
  const res = await client.get<GeoJSON.FeatureCollection>(endpoint('/tracker/coastline'));
  return res.data;
}

export async function trackerSearch(): Promise<SearchRecord[]> {
  const res = await client.get<SearchRecord[]>(endpoint('/tracker/search'));
  return res.data;
}

export async function trackerSubmit(coordinates: Array<[number, number]>): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>(endpoint('/tracker/search'), { coordinates });
  return res.data;
}

export async function trackerRevisit(id: string): Promise<SearchRecord> {
  const res = await client.post<SearchRecord>(endpoint(`/tracker/revisit/${encodeURIComponent(id)}`));
  return res.data;
}

export async function trackerClearHistory(): Promise<{ status: string; cleared: number; remaining: number }> {
  const res = await client.delete<{ status: string; cleared: number; remaining: number }>(
    endpoint('/tracker/search'),
  );
  return res.data;
}

<<<<<<< HEAD
=======
export async function clearCache(): Promise<{ status: string }> {
  const res = await client.post<{ status: string }>('/api/v1/cache/clear');
  return res.data;
}

// Namespaced default export for readable call sites: `api.detect(id)`.
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
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
<<<<<<< HEAD
  trackerClearHistory,
=======
  clearCache,
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
};

export default api;
