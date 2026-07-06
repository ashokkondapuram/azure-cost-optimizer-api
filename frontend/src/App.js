/**
 * App.js — full route + lazy-import registry
 *
 * Route map:
 *   /                        → Dashboard (Overview)
 *   /advisor                 → WasteHeatmap
 *   /tag-compliance          → TagCompliancePage
 *   /auto-scheduler          → AutoScheduler
 *   /notifications           → NotificationChannels
 *   /anomaly-detector        → CostAnomalyDetector
 *   /timeline                → OptimizationTimeline
 *   /ai-analysis             → AIAnalysis
 *   /reservation-advisor     → ReservationAdvisor
 *   /governance              → GovernanceDashboard
 *   /cost-allocation         → CostAllocation
 *   /export-center           → ExportCenter
 *   /demand-forecaster       → DemandForecaster
 */
import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './styles/advanced.css';

// Core
const Dashboard           = lazy(() => import('./pages/Dashboard'));
const WasteHeatmap        = lazy(() => import('./pages/WasteHeatmap'));
const TagCompliancePage   = lazy(() => import('./pages/TagCompliancePage'));
const AutoScheduler       = lazy(() => import('./pages/AutoScheduler'));
const NotificationChannels= lazy(() => import('./pages/NotificationChannels'));
const CostAnomalyDetector = lazy(() => import('./pages/CostAnomalyDetector'));
// Week 3
const OptimizationTimeline= lazy(() => import('./pages/OptimizationTimeline'));
const AIAnalysis          = lazy(() => import('./pages/AIAnalysis'));
// Week 4
const ReservationAdvisor  = lazy(() => import('./pages/ReservationAdvisor'));
const GovernanceDashboard = lazy(() => import('./pages/GovernanceDashboard'));
// Week 5
const CostAllocation      = lazy(() => import('./pages/CostAllocation'));
const ExportCenter        = lazy(() => import('./pages/ExportCenter'));
// Ongoing
const DemandForecaster    = lazy(() => import('./pages/DemandForecaster'));

const SidebarLayout = lazy(() => import('./components/SidebarLayout'));

function PageLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <Suspense fallback={<PageLoader />}>
        <SidebarLayout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            {/* Advanced tools */}
            <Route path="/advisor"            element={<WasteHeatmap />} />
            <Route path="/tag-compliance"     element={<TagCompliancePage />} />
            <Route path="/auto-scheduler"     element={<AutoScheduler />} />
            <Route path="/notifications"      element={<NotificationChannels />} />
            <Route path="/anomaly-detector"   element={<CostAnomalyDetector />} />
            {/* Week 3 */}
            <Route path="/timeline"           element={<OptimizationTimeline />} />
            <Route path="/ai-analysis"        element={<AIAnalysis />} />
            {/* Week 4 */}
            <Route path="/reservation-advisor" element={<ReservationAdvisor />} />
            <Route path="/governance"          element={<GovernanceDashboard />} />
            {/* Week 5 */}
            <Route path="/cost-allocation"    element={<CostAllocation />} />
            <Route path="/export-center"      element={<ExportCenter />} />
            {/* Ongoing */}
            <Route path="/demand-forecaster"  element={<DemandForecaster />} />
          </Routes>
        </SidebarLayout>
      </Suspense>
    </Router>
  );
}
