import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { fetchSubscriptions, fetchCostSummary } from './api/azure';
import { hasActiveSession } from './api/tokenStorage';
import { getErrorMessage } from './api/errors';
import usePersistedState from './hooks/usePersistedState';
import MobileHeader from './components/MobileHeader';
import AssetIcon from './components/AssetIcon';
import InfinityOpsLogo, { InfinityOpsWordmark } from './components/brand/InfinityOpsLogo';
import ErrorBoundary from './components/ErrorBoundary';
import ProtectedRoute from './components/ProtectedRoute';
import AuthSessionSync from './components/AuthSessionSync';
import SidebarNav from './components/navigation/SidebarNav';
import { createResourceRoutes } from './components/routing/ResourceRoutes';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { OperationProgressProvider } from './context/OperationProgressContext';
import { ToastProvider } from './context/ToastContext';
import GlobalProgressBar from './components/GlobalProgressBar';
import CommandPalette from './components/CommandPalette';
import ThemeToggle from './components/ThemeToggle';
import { LoadingState } from './components/QueryStates';
import { PAGE_ICONS, iconForRoute } from './config/assetIcons';
import { getPageTitle, APP_NAME } from './config/appRegistry';
import { formatUserRole } from './utils/roleLabels';
import './styles/features.css';
import './styles/advanced.css';

const Dashboard          = lazy(() => import('./pages/Dashboard'));
const CostExplorer       = lazy(() => import('./pages/CostExplorer'));
const CostForecast       = lazy(() => import('./pages/CostForecast'));
const Recommendations    = lazy(() => import('./pages/Recommendations'));
const OptimizationHub    = lazy(() => import('./pages/OptimizationHub'));
const EngineConfig       = lazy(() => import('./pages/EngineConfig'));
const AdminOptimization  = lazy(() => import('./pages/AdminOptimization'));
const RunHistory         = lazy(() => import('./pages/RunHistory'));
const SettingsPage       = lazy(() => import('./pages/Settings'));
const ApiExplorer        = lazy(() => import('./pages/ApiExplorer'));
const K8sSnapshots       = lazy(() => import('./pages/K8sSnapshots'));
const Login              = lazy(() => import('./pages/Login'));
const SavingsRealised    = lazy(() => import('./pages/SavingsRealised'));
const DriftDetection     = lazy(() => import('./pages/DriftDetection'));
const CrossSubscription  = lazy(() => import('./pages/CrossSubscription'));

// ── Advanced pages (Phase 1) ─────────────────────────────────────────────────
const WasteHeatmap         = lazy(() => import('./pages/WasteHeatmap'));
const TagCompliancePage    = lazy(() => import('./pages/TagCompliancePage'));
const AutoScheduler        = lazy(() => import('./pages/AutoScheduler'));
const NotificationChannels = lazy(() => import('./pages/NotificationChannels'));
const CostAnomalyDetector  = lazy(() => import('./pages/CostAnomalyDetector'));
const OptimizationTimeline = lazy(() => import('./pages/OptimizationTimeline'));

// ── Phase 2 pages ────────────────────────────────────────────────────────────
const BudgetManager      = lazy(() => import('./pages/BudgetManager'));
const SavingsPlanner     = lazy(() => import('./pages/SavingsPlanner'));
const PolicyEnforcement  = lazy(() => import('./pages/PolicyEnforcement'));

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
    loading, subscriptionError, billingCurrency,
  } = useContext(AppCtx);
  const { user, logout, isAdmin } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const subName = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;
  const pageTitle = getPageTitle(location.pathname);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

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
    <OperationProgressProvider subscription={subscription}>
    <div className={`app-shell${mobileOpen ? ' app-shell--nav-open' : ''}`}>
      <GlobalProgressBar />
      <CommandPalette subscription={subscription} />
      <div className="sidebar-backdrop" onClick={closeMobile} aria-hidden={!mobileOpen} />

      <aside className="sidebar" aria-label="Main navigation">
        <div className="sidebar-logo">
          <div className="sidebar-logo__icon sidebar-logo__icon--brand">
            <InfinityOpsLogo size={32} />
          </div>
          <InfinityOpsWordmark />
        </div>

        <div className="sidebar-sub-picker">
          <div className="topbar-label icon-inline">
            <AssetIcon iconKey={PAGE_ICONS.subscription} size={12} />
            Subscription
          </div>
          {loading ? (
            <div className="sidebar-loading">
              <div className="spin" style={{ width: 14, height: 14, borderWidth: 2 }} />
              Loading…
            </div>
          ) : subscriptionError ? (
            <div className="sidebar-error" role="alert">{subscriptionError}</div>
          ) : subscriptionOptions.length === 0 ? (
            <div className="sidebar-empty-sub" role="status">
              No subscriptions in the database yet.
              {isAdmin && (
                <span> Set a default subscription in Settings, or run Sync from Azure.</span>
              )}
            </div>
          ) : (
            <select
              className="select-field"
              value={subscription}
              onChange={(e) => setSubscription(e.target.value)}
            >
              <option value="">Select subscription</option>
              {subscriptionOptions.map((s) => (
                <option key={s.subscriptionId} value={s.subscriptionId}>
                  {s.displayName || s.subscriptionId}
                </option>
              ))}
            </select>
          )}
        </div>

        <SidebarNav onNavClick={closeMobile} />

        <div className="sidebar-footer">
          <div className="sidebar-theme">
            <div className="topbar-label">Appearance</div>
            <ThemeToggle />
          </div>
          <div className="sidebar-footer__user">
            <span className="sidebar-footer__name" title={user?.username}>
              {user?.display_name || user?.username}
            </span>
            {user?.role && <span className="sidebar-footer__role">{formatUserRole(user.role)}</span>}
          </div>
          <button type="button" className="sidebar-footer__logout" onClick={logout} title="Sign out">
            <LogOut size={14} />
            Sign out
          </button>
          {subName && <span className="sidebar-footer__sub" title={subName}>{subName}</span>}
        </div>
      </aside>

      <div className="main-column">
        <MobileHeader
          open={mobileOpen}
          onToggle={() => setMobileOpen((o) => !o)}
          title={pageTitle}
          iconKey={iconForRoute(location.pathname)}
        />
        <main className="main-content">
          <ErrorBoundary>
            <Suspense fallback={<LoadingState message="Loading page…" />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/costs" element={<CostExplorer />} />
                <Route path="/costs/forecast" element={<CostForecast />} />
                <Route path="/savings-realised" element={<SavingsRealised />} />
                <Route path="/drift" element={<DriftDetection />} />
                <Route path="/cross-subscription" element={<CrossSubscription />} />
                <Route path="/recommendations" element={<Navigate to="/optimization-hub?tab=actions" replace />} />
                <Route path="/findings" element={<Navigate to="/optimization-hub?tab=findings" replace />} />
                <Route path="/rollout-monitor" element={<Navigate to="/optimization-hub?tab=rollout" replace />} />
                <Route path="/optimization-hub" element={<OptimizationHub />} />
                <Route path="/optimize/actions" element={<Navigate to="/optimization-hub?tab=actions" replace />} />
                <Route path="/optimize/scoreboard" element={<Navigate to="/optimization-hub?tab=scoreboard" replace />} />
                <Route path="/optimize/rollout-monitor" element={<Navigate to="/optimization-hub?tab=rollout" replace />} />
                <Route path="/k8s" element={<K8sSnapshots />} />
                <Route path="/engine" element={<ProtectedRoute adminOnly><EngineConfig /></ProtectedRoute>} />
                <Route path="/admin/optimization" element={<ProtectedRoute adminOnly><AdminOptimization /></ProtectedRoute>} />
                <Route path="/history" element={<RunHistory />} />
                <Route path="/settings" element={<ProtectedRoute adminOnly><SettingsPage /></ProtectedRoute>} />
                <Route path="/admin/api-explorer" element={<ProtectedRoute adminOnly><ApiExplorer /></ProtectedRoute>} />

                {/* ── Advanced pages (Phase 1) ─────────────────────── */}
                <Route path="/waste-heatmap"    element={<WasteHeatmap />} />
                <Route path="/tag-compliance"   element={<TagCompliancePage />} />
                <Route path="/auto-scheduler"   element={<AutoScheduler />} />
                <Route path="/notifications"    element={<NotificationChannels />} />
                <Route path="/anomaly-detector" element={<CostAnomalyDetector />} />
                <Route path="/timeline"         element={<OptimizationTimeline />} />

                {/* ── Phase 2 pages ────────────────────────────────── */}
                <Route path="/budgets"          element={<BudgetManager />} />
                <Route path="/savings-planner"  element={<SavingsPlanner />} />
                <Route path="/policy"           element={<PolicyEnforcement />} />

                {createResourceRoutes()}
                <Route path="*" element={<Navigate to="/" replace />} />
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
        <Route path="/login" element={<Login />} />
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
  const [loading, setLoading] = useState(true);
  const [subscriptionError, setSubscriptionError] = useState('');

  const subscriptionOptions = useMemo(() => {
    const byId = new Map();
    subscriptions.forEach((s) => {
      if (s.subscriptionId) byId.set(s.subscriptionId, s);
    });
    if (subscription && !byId.has(subscription)) {
      byId.set(subscription, { subscriptionId: subscription, displayName: subscription, state: 'Synced' });
    }
    return Array.from(byId.values()).sort((a, b) =>
      (a.displayName || a.subscriptionId).localeCompare(b.displayName || b.subscriptionId),
    );
  }, [subscriptions, subscription]);

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
      .then((list) => {
        setSubscriptions(list);
        setSubscriptionError('');
        if (list.length > 0) {
          const ids = new Set(list.map((s) => s.subscriptionId));
          if (!subscription || !ids.has(subscription)) {
            setSubscription(list[0].subscriptionId);
          }
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
      subscriptionOptions,
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
