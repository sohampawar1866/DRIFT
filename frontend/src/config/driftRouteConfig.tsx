import type { ComponentType } from 'react';
import { Gauge, History, Map, Radar } from 'lucide-react';
import {
  LandingFormPage,
  OpsDashboardPage,
  HistoryPage,
  IntelDashboardPage,
} from './driftLazyPages';

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
    component: LandingFormPage,
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
    component: OpsDashboardPage,
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
