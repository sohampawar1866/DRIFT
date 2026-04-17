import { lazy, type ComponentType } from 'react';
import { Gauge, History, Map, Radar } from 'lucide-react';

const LandingForm = lazy(() => import('../components/LandingForm').then((mod) => ({ default: mod.LandingForm })));
const OpsDashboard = lazy(() => import('../components/OpsDashboard').then((mod) => ({ default: mod.OpsDashboard })));
const HistoryPage = lazy(() => import('../components/HistoryPage').then((mod) => ({ default: mod.HistoryPage })));
const IntelDashboardPage = lazy(() => import('../components/IntelDashboardPage').then((mod) => ({ default: mod.IntelDashboardPage })));

type NavConfig = {
  label: string;
  to: string;
  icon: ComponentType<{ size?: number }>;
  activePrefixes: string[];
};

export type DriftRouteConfig = {
  key: string;
  index?: boolean;
  path?: string;
  component: ComponentType;
  nav?: NavConfig;
};

export const DRIFT_ROUTE_CONFIG: DriftRouteConfig[] = [
  {
    key: 'map-ops',
    index: true,
    component: LandingForm,
    nav: {
      label: 'Map Ops',
      to: '/drift',
      icon: Map,
      activePrefixes: ['/drift'],
    },
  },
  {
    key: 'ops-detail',
    path: 'aoi/:aoi_id',
    component: OpsDashboard,
    nav: {
      label: 'Ops Detail',
      to: '/drift/aoi/mumbai',
      icon: Radar,
      activePrefixes: ['/drift/aoi/'],
    },
  },
  {
    key: 'history',
    path: 'history',
    component: HistoryPage,
    nav: {
      label: 'History',
      to: '/drift/history',
      icon: History,
      activePrefixes: ['/drift/history'],
    },
  },
  {
    key: 'intel',
    path: 'dashboard',
    component: IntelDashboardPage,
    nav: {
      label: 'Intel',
      to: '/drift/dashboard',
      icon: Gauge,
      activePrefixes: ['/drift/dashboard'],
    },
  },
];

export const DRIFT_NAV_ITEMS = DRIFT_ROUTE_CONFIG.filter((route) => route.nav).map((route) => route.nav!);
