import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { LandingForm } from './components/LandingForm';
import { OpsDashboard } from './components/OpsDashboard';
import { HistoryPage } from './components/HistoryPage';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app-container" style={{ width: '100%', height: '100vh', margin: 0, padding: 0 }}>
        <Routes>
          <Route path="/" element={<LandingForm />} />
          <Route path="/aoi/:aoi_id" element={<OpsDashboard />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
