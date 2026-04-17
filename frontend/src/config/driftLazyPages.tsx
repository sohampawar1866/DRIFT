import { lazy } from 'react';

export const LandingFormPage = lazy(() =>
  import('../components/LandingForm').then((mod) => ({ default: mod.LandingForm })),
);

export const OpsDashboardPage = lazy(() =>
  import('../components/OpsDashboard').then((mod) => ({ default: mod.OpsDashboard })),
);

export const HistoryPage = lazy(() =>
  import('../components/HistoryPage').then((mod) => ({ default: mod.HistoryPage })),
);

export const IntelDashboardPage = lazy(() =>
  import('../components/IntelDashboardPage').then((mod) => ({ default: mod.IntelDashboardPage })),
);
