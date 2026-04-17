import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { DRIFT_ROUTE_CONFIG } from './config/driftRouteConfig';
import ErrorBoundary from './components/ErrorBoundary';
import './App.css';

const NewLandingPage = lazy(() => import('./components/NewLandingPage').then((mod) => ({ default: mod.NewLandingPage })));
const DriftAppShell = lazy(() => import('./components/DriftAppShell').then((mod) => ({ default: mod.DriftAppShell })));

const Loader = () => (
  <div
    style={{
      minHeight: '100vh',
      width: '100%',
      display: 'grid',
      placeItems: 'center',
      background: '#1e2229',
      color: '#9fb0c6',
      fontSize: 'var(--type-body-md)',
      letterSpacing: '0.04em',
    }}
  >
    Loading D.R.I.F.T. modules...
  </div>
);

function App() {
  return (
    <Router>
      <div className="app-container" style={{ width: '100%', height: '100vh', margin: 0, padding: 0 }}>
        <ErrorBoundary>
        <Suspense fallback={<Loader />}>
          <Routes>
            <Route path="/" element={<NewLandingPage />} />
            <Route path="/drift" element={<DriftAppShell />}>
              {DRIFT_ROUTE_CONFIG.map((route) => {
                const RouteComponent = route.component;
                return route.index ? (
                  <Route key={route.key} index element={<RouteComponent />} />
                ) : (
                  <Route key={route.key} path={route.path} element={<RouteComponent />} />
                );
              })}
            </Route>
          </Routes>
        </Suspense>
        </ErrorBoundary>
      </div>
    </Router>
  );
}

export default App;
