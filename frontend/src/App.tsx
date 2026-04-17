import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { NewLandingPage } from './components/NewLandingPage';
import { LandingForm } from './components/LandingForm';
import { OpsDashboard } from './components/OpsDashboard';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app-container" style={{ width: '100%', height: '100vh', margin: 0, padding: 0 }}>
        <Routes>
          <Route path="/" element={<NewLandingPage />} />
          <Route path="/drift" element={<LandingForm />} />
          <Route path="/drift/aoi/:aoi_id" element={<OpsDashboard />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
