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
  baseURL: API_BASE_URL || undefined,
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

export type ForecastHours = number;
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

export interface AoiListResponse {
  aois: AoiEntry[];
}

export interface DetectionFC extends GeoJSON.FeatureCollection {
  features: Array<GeoJSON.Feature<GeoJSON.Polygon, {
    id?: string;
    confidence?: number;
    confidence_decay_k?: number;
    area_sq_meters?: number;
    age_days?: number;
    type?: string;
    predicted_class?: string;
    water_temp_c?: number | null;
    chlorophyll_mg_m3?: number | null;
    fraction_plastic?: number;
  }>>;
}

export interface ForecastFeatureProperties {
  forecast_hour?: number;
  aoi_id?: string;
  type?: string;
  layer?: string;
  level?: number;
  density?: number;
  render_color?: string;
}

export interface ForecastMetadata {
  requested_horizon_hours?: number;
  effective_horizon_hours?: number;
  simulated_until_hour?: number;
  total_particles?: number;
  alive_particles?: number;
  beached_particles?: number;
  stop_track_at_90d_cap_applied?: boolean;
  never_beached_particles_remaining?: number;
  never_beached_until_stop?: boolean;
  stopped_early_all_beached?: boolean;
  stop_reason?: string;
  requested_forecast_hour?: number;
}

export interface ForecastFC extends GeoJSON.FeatureCollection {
  features: Array<GeoJSON.Feature<GeoJSON.Geometry, ForecastFeatureProperties>>;
  metadata?: ForecastMetadata;
}

export interface EnvironmentSummary {
  aoi_id: string;
  bbox: [number, number, number, number];
  water_temp_c: number;
  chlorophyll_mg_m3: number;
  confidence_decay_k: number;
  generated_at: string;
  source: string | null;
}

export interface AlertPreview {
  aoi_id: string;
  forecast_hours: number;
  deposition_hotspots: number;
  threshold_density: number;
  threshold_persistence_hours: number;
  triggered: boolean;
  notifications: Array<{
    organization: string;
    contact: string;
    distance_km: number;
    hotspot_center: [number, number];
    segment_key?: string;
    channel: string;
  }>;
  coastal_segment_km?: number;
  coastal_segments_evaluated?: number;
  coastal_segments_triggered?: number;
  segment_alerts?: Array<{
    segment_key: string;
    source_segment_id?: number | null;
    bin_index?: number | null;
    segment_center: [number, number];
    segment_length_km: number;
    hotspot_count: number;
    density_score: number;
    persistence_hours: number;
    min_coast_distance_km?: number | null;
    triggered: boolean;
  }>;
  status: string;
}

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
  region_statistics?: {
    plastic_coverage_pct: number;
    average_confidence: number;
    area_m2: number;
  };
  environment?: EnvironmentSummary;
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

export async function listAois(): Promise<AoiListResponse> {
  const res = await client.get<AoiListResponse>(endpoint('/aois'));
  return res.data;
}

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
  });
  return res.data;
}

export async function forecast(aoi_id: string, hours: ForecastHours, spatial?: SpatialQuery): Promise<ForecastFC> {
  const res = await client.get<ForecastFC>(endpoint('/forecast'), {
    params: { aoi_id, hours, ...spatialParams(spatial) },
  });
  return res.data;
}

export async function environmentContext(aoi_id: string, spatial?: SpatialQuery): Promise<EnvironmentSummary> {
  const res = await client.get<EnvironmentSummary>(endpoint('/environment'), {
    params: { aoi_id, ...spatialParams(spatial) },
  });
  return res.data;
}

export async function alertPreview(aoi_id: string, hours: ForecastHours, spatial?: SpatialQuery): Promise<AlertPreview> {
  const res = await client.get<{ alerts: AlertPreview }>(endpoint('/alerts/preview'), {
    params: { aoi_id, hours, ...spatialParams(spatial) },
  });
  return res.data.alerts;
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
  const bounded = Math.max(24, Math.min(2160, Math.round(h / 24) * 24));
  return bounded;
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

const api = {
  API_BASE_URL,
  apiErrorMessage,
  listAois,
  detect,
  forecast,
  environmentContext,
  alertPreview,
  mission,
  dashboardMetrics,
  exportUrl,
  snapForecastHours,
  trackerCoastline,
  trackerSearch,
  trackerSubmit,
  trackerRevisit,
  trackerClearHistory,
};

export default api;
