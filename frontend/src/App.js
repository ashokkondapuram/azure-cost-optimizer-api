import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Resources from './pages/Resources';
import K8sPage from './pages/K8sPage';
import CostHistory from './pages/CostHistory';

export default function App() {
  const [subscriptionId, setSubscriptionId] = useState(
    localStorage.getItem('subscriptionId') || ''
  );

  const handleSubChange = (e) => {
    setSubscriptionId(e.target.value);
    localStorage.setItem('subscriptionId', e.target.value);
  };

  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <h1>☁️ Azure Cost Optimizer</h1>
          <input
            placeholder="Subscription ID"
            value={subscriptionId}
            onChange={handleSubChange}
            style={{ marginBottom: 12, width: '100%' }}
          />
          <NavLink to="/" end>📊 Dashboard</NavLink>
          <NavLink to="/resources">🗂 Resources</NavLink>
          <NavLink to="/k8s">⎈ Kubernetes</NavLink>
          <NavLink to="/history">📜 Cost History</NavLink>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard subscriptionId={subscriptionId} />} />
            <Route path="/resources" element={<Resources subscriptionId={subscriptionId} />} />
            <Route path="/k8s" element={<K8sPage />} />
            <Route path="/history" element={<CostHistory />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
