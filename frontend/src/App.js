import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fetchSubscriptions, fetchCostSummary } from './api/azure';
import { hasActiveSession } from './api/tokenStorage';
import { getErrorMessage } from './api/errors';
import usePersistedState from './hooks/usePersistedState';
import MobileHeader from './components/MobileHeader';
import InfinityOpsLogo from './components/brand/InfinityOpsLogo';
import ErrorBoundary from './components/ErrorBoundary';
import ProtectedRoute from './components/ProtectedRoute';
import AuthSessionSync from './components/AuthSessionSync';
import SidebarNav from './components/navigation/SidebarNav';
import AppTopbar from './components/navigation/AppTopbar';
import RailCollapseButton from './components/navigation/RailCollapseButton';
import RailFoot from './components/navigation/RailFoot';
import { createResourceRoutes } from './components/routing/ResourceRoutes';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { OperationProgressProvider } from './context/OperationProgressContext';
import { ToastProvider } from './context/ToastContext';
import GlobalProgressBar from './components/GlobalProgressBar';
import CommandPalette from './components/CommandPalette';
import { LoadingState } from './components/QueryStates';
import { iconForRoute } from './config/assetIcons';
import {
  resolveSubscriptionLabel,
} from './utils/subscriptionDisplay';
import { getPageTitle, APP_NAME, APP_TAGLINE } from './config/appRegistry';
import AddSubscriptionModal from './components/subscription/AddSubscriptionModal';

const Dashboard          = lazy(() => import('./pages/Dashboard'));
const CostExplorer       = lazy(() => import('./pages/CostExplorer'));
const CloudExplorer      = lazy(() => import('./pages/CloudExplorer'));
const ActionCentre       = lazy(() => import('./pages/ActionCentre'));
const ResourceDetail     = lazy(() => import('./pages/ResourceDetail'));
const LegacyOptimizationHubRedirect = lazy(() => import('./components/routing/LegacyOptimizationHubRedirect'));
const EngineConfig       = lazy(() => import('./pages/EngineConfig'));
const AdminOptimization  = lazy(() => import('./pages/AdminOptimization'));
const RunHistory         = lazy(() => import('./pages/RunHistory'));
const SettingsPage       = lazy(() => import('./pages/Settings'));
const ApiExplorer        = lazy(() => import('./pages/ApiExplorer'));
const K8sSnapshots       = lazy(() => import('./pages/K8sSnapshots'));
const Login              = lazy(() => import('./pages/Login'));

// Advanced tools
const WasteHeatmap         = lazy(() => import('./pages/WasteHeatmap'));
const CostAnomalyDetector  = lazy(() => import('./pages/CostAnomalies'));
const PlannedMaintenance   = lazy(() => import('./pages/PlannedMaintenance'));
const QuotaUsage           = lazy(() => import('./pages/QuotaUsage'));
const BudgetManager        = lazy(() => import('./pages/BudgetManager'));
const SavingsPlanner       = lazy(() => import('./pages/SavingsPlanner'));
const ReservationAdvisor   = lazy(() => import('./pages/ReservationAdvisor'));
const CostComparison       = lazy(() => import('./pages/CostComparison'));
const ActivityLog          = lazy(() => import('./pages/ActivityLog'));
const DemandForecaster     = lazy(() => import('./pages/DemandForecaster'));

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
});

export const AppCtx = createContext({});

function Shell() {
  const {
    subscription, setSubscription, subscriptionOptions,
    loading, subscriptionError, reloadSubscriptions, billingCurrency,
    registeredSubscriptionIds,
  } = useContext(AppCtx);
  const { user, logout, isAdmin } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [addSubOpen, setAddSubOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = usePersistedState('finops-sidebar-collapsed', false);
  const subName = resolveSubscriptionLabel(subscription, subscriptionOptions);
  const pageTitle = getPageTitle(location.pathname);

  const closeMobile = useCallback(() => setMobileOpen(false), []);
  const expandSidebar = useCallback(() => setSidebarCollapsed(false), [setSidebarCollapsed]);
  const goToAddSubscription = useCallback(() => {
    closeMobile();
    setAddSubOpen(true);
  }, [closeMobile]);
  const handleSubscriptionAdded = useCallback((result) => {
    reloadSubscriptions?.();
    const addedId = result?.subscription_id
      || result?.subscriptions?.find((s) => s.isDefault)?.subscriptionId;
    if (addedId) {
      setSubscription(addedId);
    }
  }, [reloadSubscriptions, setSubscription]);

  useEffect(() => {
    document.title = pageTitle === APP_NAME ? APP_NAME : `${pageTitle} · ${APP_NAME}`;
  }, [pageTitle]);

  useEffect(() => { closeMobile(); }, [location.pathname, closeMobile]);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileOpen]);

  return (
    <ToastProvider>
    <OperationProgressProvider
      subscription={subscription}
      subscriptionRegistered={!subscription || registeredSubscriptionIds.has(subscription)}
    >
    <div className={`app-shell${mobileOpen ? ' app-shell--nav-open' : ''}${sidebarCollapsed ? ' app-shell--sidebar-collapsed' : ''}`}>
      <GlobalProgressBar />
      <CommandPalette subscription={subscription} />
      {isAdmin && (
        <AddSubscriptionModal
          open={addSubOpen}
          onClose={() => setAddSubOpen(false)}
          onAdded={handleSubscriptionAdded}
          hasExistingSubscriptions={subscriptionOptions.length > 0}
        />
      )}
      <div className="sidebar-backdrop" onClick={closeMobile} aria-hidden={!mobileOpen} />

      <aside className={`sidebar rail${sidebarCollapsed ? ' sidebar--collapsed' : ''}`} aria-label="Main navigation">
        <div className="rail-head">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              <InfinityOpsLogo size={36} />
            </div>
            {!sidebarCollapsed && (
              <div className="brand-text">
                <strong>{APP_NAME}</strong>
                <span>{APP_TAGLINE}</span>
              </div>
            )}
            <RailCollapseButton
              collapsed={sidebarCollapsed}
              onToggle={() => setSidebarCollapsed((c) => !c)}
            />
          </div>

        </div>

        <SidebarNav
          onNavClick={closeMobile}
          collapsed={sidebarCollapsed}
          onExpandSidebar={expandSidebar}
        />

        <RailFoot
          collapsed={sidebarCollapsed}
          user={user}
          onLogout={logout}
        />
      </aside>

      <div className="main-column">
        <MobileHeader
          open={mobileOpen}
          onToggle={() => setMobileOpen((o) => !o)}
          title={pageTitle}
          iconKey={iconForRoute(location.pathname)}
        />
        <AppTopbar
          subscription={subscription}
          subscriptionOptions={subscriptionOptions}
          subscriptionName={subName}
          billingCurrency={billingCurrency}
          loading={loading}
          error={subscriptionError}
          isAdmin={isAdmin}
          onAddSubscription={goToAddSubscription}
          onSubscriptionChange={setSubscription}
          showSyncProgress={location.pathname === '/dashboard'}
        />
        <main className="main-content">
          <ErrorBoundary>
            <Suspense fallback={<LoadingState message="Loading page…" />}>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/action-centre/workflow" element={<Navigate to="/action-centre?hasAction=1" replace />} />
                <Route path="/action-centre" element={<ActionCentre />} />
                <Route path="/resource/:resourceId" element={<ResourceDetail />} />
                <Route path="/explorer/*" element={<ProtectedRoute superuserOnly><CloudExplorer /></ProtectedRoute>} />
                <Route path="/issues" element={<Navigate to="/action-centre" replace />} />
                <Route path="/inventory" element={<Navigate to="/explorer" replace />} />
                <Route path="/costs" element={<CostExplorer />} />
                <Route path="/recommendations" element={<Navigate to="/action-centre" replace />} />
                <Route path="/optimization-hub/*" element={<LegacyOptimizationHubRedirect />} />
                <Route path="/optimize/actions" element={<Navigate to="/action-centre?hasAction=1" replace />} />
                <Route path="/optimize/rollout-monitor" element={<Navigate to="/action-centre" replace />} />
                <Route path="/findings" element={<Navigate to="/action-centre" replace />} />
                <Route path="/k8s" element={<K8sSnapshots />} />
                <Route path="/engine" element={<ProtectedRoute adminOnly><EngineConfig /></ProtectedRoute>} />
                <Route path="/admin/optimization" element={<ProtectedRoute adminOnly><AdminOptimization /></ProtectedRoute>} />
                <Route path="/history" element={<RunHistory />} />
                <Route path="/settings" element={<ProtectedRoute adminOnly><SettingsPage /></ProtectedRoute>} />
                <Route path="/admin/api-explorer" element={<ProtectedRoute adminOnly><ApiExplorer /></ProtectedRoute>} />
                {/* Advanced tools */}
                <Route path="/waste-heatmap" element={<WasteHeatmap />} />
                <Route path="/planned-maintenance" element={<PlannedMaintenance />} />
                <Route path="/quota-usage" element={<QuotaUsage />} />
                <Route path="/anomaly-detector" element={<CostAnomalyDetector />} />
                <Route path="/budgets" element={<BudgetManager />} />
                <Route path="/savings-planner" element={<SavingsPlanner />} />
                <Route path="/reservation-advisor" element={<ReservationAdvisor />} />
                <Route path="/cost-comparison" element={<CostComparison />} />
                <Route path="/activity-log" element={<ActivityLog />} />
                <Route path="/demand-forecaster" element={<DemandForecaster />} />
                {createResourceRoutes()}
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
    </OperationProgressProvider>
    </ToastProvider>
  );
}

function AppRoutes() {
  return (
    <>
      <AuthSessionSync />
      <Routes>
        <Route
          path="/login"
          element={(
            <Suspense fallback={<LoadingState message="Loading…" />}>
              <Login />
            </Suspense>
          )}
        />
        <Route path="/*" element={<ProtectedRoute><Shell /></ProtectedRoute>} />
      </Routes>
    </>
  );
}

function AppData() {
  const { loading: authLoading } = useAuth();
  const [subscriptionRaw, setSubscriptionRaw] = usePersistedState('finops-subscription', '');
  const setSubscription = useCallback((value) => {
    setSubscriptionRaw(value ? String(value).trim().toLowerCase() : '');
  }, [setSubscriptionRaw]);
  const subscription = subscriptionRaw ? String(subscriptionRaw).trim().toLowerCase() : '';

  const [subscriptions, setSubscriptions] = useState([]);
  const [defaultSubscriptionId, setDefaultSubscriptionId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscriptionError, setSubscriptionError] = useState('');

  const subscriptionOptions = useMemo(() => {
    const byId = new Map();
    subscriptions.forEach((s) => {
      if (s.subscriptionId) byId.set(s.subscriptionId, s);
    });
    return Array.from(byId.values()).sort((a, b) =>
      (a.displayName || a.subscriptionId).localeCompare(b.displayName || b.subscriptionId),
    );
  }, [subscriptions]);

  const registeredSubscriptionIds = useMemo(
    () => new Set(subscriptionOptions.map((s) => s.subscriptionId)),
    [subscriptionOptions],
  );

  const { data: costSummary } = useQuery({
    queryKey: ['cost-summary-meta', subscription],
    queryFn: () => fetchCostSummary({ subscription_id: subscription, timeframe: 'MonthToDate' }),
    enabled: !!subscription && hasActiveSession() && !authLoading,
    staleTime: 30 * 60_000,
  });

  const billingCurrency = costSummary?.billing_currency || 'CAD';

  const loadSubscriptions = useCallback(() => {
    if (authLoading || !hasActiveSession()) {
      if (!hasActiveSession()) {
        setSubscriptions([]);
        setLoading(false);
      }
      return;
    }
    setLoading(true);
    fetchSubscriptions()
      .then(({ subscriptions: list, defaultSubscriptionId: configuredDefault }) => {
        setSubscriptions(list);
        setDefaultSubscriptionId(configuredDefault);
        setSubscriptionError('');
        if (list.length > 0) {
          const ids = new Set(list.map((s) => s.subscriptionId));
          const preferred = configuredDefault && ids.has(configuredDefault)
            ? configuredDefault
            : list.find((s) => s.isDefault)?.subscriptionId;
          if (!subscription || !ids.has(subscription)) {
            setSubscription(preferred || list[0].subscriptionId);
          }
        } else if (configuredDefault) {
          setSubscription(configuredDefault);
        } else if (subscription) {
          setSubscription('');
        }
      })
      .catch((err) => {
        setSubscriptionError(getErrorMessage(err, 'Could not load subscriptions.'));
      })
      .finally(() => setLoading(false));
  }, [setSubscription, subscription, authLoading]);

  useEffect(() => {
    if (authLoading) return;
    loadSubscriptions();
  }, [loadSubscriptions, authLoading]);

  return (
    <AppCtx.Provider value={{
      subscription,
      setSubscription,
      subscriptions,
      defaultSubscriptionId,
      subscriptionOptions,
      registeredSubscriptionIds,
      loading,
      subscriptionError,
      reloadSubscriptions: loadSubscriptions,
      billingCurrency,
    }}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppCtx.Provider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <AuthProvider>
          <AppData />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
