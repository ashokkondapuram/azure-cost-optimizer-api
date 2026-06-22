import React, { createContext, useContext, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Cpu, HardDrive, Network, Database,
  Shield, DollarSign, Settings, Search, Activity,
  ChevronDown, ChevronRight, Bell, RefreshCw, Boxes, CloudCog,
  Globe, Server, Container, KeyRound, SquareCode, Layers,
  GitBranch, Wallet, AppWindow, FolderOpen
} from 'lucide-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fetchSubscriptions } from './api/azure';

import Dashboard       from './pages/Dashboard';
import CostExplorer   from './pages/CostExplorer';
import Findings       from './pages/Findings';
import VirtualMachines from './pages/VirtualMachines';
import AKSClusters    from './pages/AKSClusters';
import AllResources   from './pages/AllResources';
import EngineConfig   from './pages/EngineConfig';
import RunHistory     from './pages/RunHistory';
import ResourceList   from './pages/ResourceList';

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } });
export const AppCtx = createContext({});

// ─── Collapsible nav group ────────────────────────────────────────────────────
function NavGroup({ label, icon, color, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center',
          gap: 8, padding: '6px 1rem', background: 'none', border: 'none',
          cursor: 'pointer', color: 'var(--text2)', fontSize: '0.78rem',
          fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        <span style={{ color }}>{icon}</span>
        <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>
        {open
          ? <ChevronDown size={13} style={{ opacity: 0.5 }} />
          : <ChevronRight size={13} style={{ opacity: 0.5 }} />}
      </button>
      {open && (
        <div style={{ paddingLeft: '0.75rem' }}>
          {children}
        </div>
      )}
    </div>
  );
}

function Shell() {
  const { subscription, setSubscription, subscriptions, loading } = useContext(AppCtx);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* ── Sidebar ── */}
      <nav className="sidebar">
        <div className="sidebar-logo">
          <CloudCog size={18} color="#2563eb" />
          Azure<span>FinOps</span>
        </div>

        {/* Subscription selector */}
        <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--border)' }}>
          <div className="topbar-label" style={{ marginBottom: 6 }}>Subscription</div>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text3)', fontSize: '0.8rem' }}>
              <div className="spin" style={{ width: 14, height: 14 }} /> Loading...
            </div>
          ) : (
            <select
              value={subscription}
              onChange={e => setSubscription(e.target.value)}
              style={{ width: '100%', fontSize: '0.78rem', padding: '6px 8px' }}
            >
              <option value="">-- Select --</option>
              {subscriptions.map(s => (
                <option key={s.subscriptionId} value={s.subscriptionId}>
                  {s.displayName || s.subscriptionId}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Nav links */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0' }}>

          {/* ── Overview ── */}
          <div className="sidebar-section">Overview</div>
          <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <LayoutDashboard size={15} /> Dashboard
          </NavLink>
          <NavLink to="/costs" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <DollarSign size={15} /> Cost Explorer
          </NavLink>
          <NavLink to="/findings" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Activity size={15} /> Findings
          </NavLink>

          {/* ── Resources ── */}
          <div className="sidebar-section">Resources</div>

          <NavLink to="/resources" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <FolderOpen size={15} /> All Resources
          </NavLink>

          {/* Compute */}
          <NavGroup label="Compute" icon={<Cpu size={14} />} color="#3b82f6" defaultOpen={true}>
            <NavLink to="/vms"   className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Server size={14} /> Virtual Machines
            </NavLink>
            <NavLink to="/disks" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <HardDrive size={14} /> Managed Disks
            </NavLink>
          </NavGroup>

          {/* Containers */}
          <NavGroup label="Containers" icon={<Boxes size={14} />} color="#7c3aed">
            <NavLink to="/aks" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Boxes size={14} /> AKS Clusters
            </NavLink>
            <NavLink to="/acr" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Container size={14} /> Container Registries
            </NavLink>
          </NavGroup>

          {/* App Services */}
          <NavGroup label="App Services" icon={<AppWindow size={14} />} color="#0891b2">
            <NavLink to="/appservices" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <AppWindow size={14} /> Web / Function Apps
            </NavLink>
          </NavGroup>

          {/* Storage */}
          <NavGroup label="Storage" icon={<HardDrive size={14} />} color="#d97706">
            <NavLink to="/storage" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <HardDrive size={14} /> Storage Accounts
            </NavLink>
          </NavGroup>

          {/* Networking */}
          <NavGroup label="Networking" icon={<Network size={14} />} color="#059669">
            <NavLink to="/publicips"     className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Globe size={14} /> Public IPs
            </NavLink>
            <NavLink to="/loadbalancers" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Layers size={14} /> Load Balancers
            </NavLink>
            <NavLink to="/appgateways"   className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <GitBranch size={14} /> App Gateways
            </NavLink>
            <NavLink to="/nsgs"          className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Shield size={14} /> Network Sec. Groups
            </NavLink>
          </NavGroup>

          {/* Databases */}
          <NavGroup label="Databases" icon={<Database size={14} />} color="#dc2626">
            <NavLink to="/sql"        className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Database size={14} /> SQL Servers
            </NavLink>
            <NavLink to="/cosmosdb"   className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Database size={14} /> Cosmos DB
            </NavLink>
            <NavLink to="/postgresql" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <Database size={14} /> PostgreSQL
            </NavLink>
          </NavGroup>

          {/* Security */}
          <NavGroup label="Security" icon={<Shield size={14} />} color="#f97316">
            <NavLink to="/keyvaults" className={({ isActive }) => `nav-item nav-sub${isActive ? ' active' : ''}`}>
              <KeyRound size={14} /> Key Vaults
            </NavLink>
          </NavGroup>

          {/* ── Engine ── */}
          <div className="sidebar-section">Engine</div>
          <NavLink to="/engine"  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <CloudCog size={15} /> Engine Config
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Search size={15} /> Run History
          </NavLink>
        </div>

        <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.72rem', color: 'var(--text3)' }}>
          v5.0 · AzureFinOps
        </div>
      </nav>

      {/* ── Main content ── */}
      <main className="main-content">
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/costs"       element={<CostExplorer />} />
          <Route path="/findings"    element={<Findings />} />
          <Route path="/vms"         element={<VirtualMachines />} />
          <Route path="/aks"         element={<AKSClusters />} />
          <Route path="/resources"   element={<AllResources />} />
          <Route path="/engine"      element={<EngineConfig />} />
          <Route path="/history"     element={<RunHistory />} />
          {/* Generic resource list pages */}
          <Route path="/disks"        element={<ResourceList type="compute/disk"         title="Managed Disks"            apiPath="/resources/disks" />} />
          <Route path="/acr"          element={<ResourceList type="containers/acr"       title="Container Registries"     apiPath="/resources/acr" />} />
          <Route path="/appservices"  element={<ResourceList type="appservice/webapp"    title="Web / Function Apps"      apiPath="/resources/appservices" />} />
          <Route path="/storage"      element={<ResourceList type="storage/account"      title="Storage Accounts"         apiPath="/resources/storage" />} />
          <Route path="/publicips"    element={<ResourceList type="network/publicip"     title="Public IPs"               apiPath="/resources/publicips" />} />
          <Route path="/loadbalancers" element={<ResourceList type="network/loadbalancer" title="Load Balancers"           apiPath="/resources/loadbalancers" />} />
          <Route path="/appgateways"  element={<ResourceList type="network/appgateway"   title="Application Gateways"     apiPath="/resources/appgateways" />} />
          <Route path="/nsgs"         element={<ResourceList type="network/nsg"          title="Network Security Groups"  apiPath="/resources/nsgs" />} />
          <Route path="/sql"          element={<ResourceList type="database/sql"         title="SQL Servers"              apiPath="/resources/sql" />} />
          <Route path="/cosmosdb"     element={<ResourceList type="database/cosmosdb"    title="Cosmos DB Accounts"       apiPath="/resources/cosmosdb" />} />
          <Route path="/postgresql"   element={<ResourceList type="database/postgresql"  title="PostgreSQL Servers"       apiPath="/resources/postgresql" />} />
          <Route path="/keyvaults"    element={<ResourceList type="security/keyvault"    title="Key Vaults"               apiPath="/resources/keyvaults" />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [subscription, setSubscription] = useState('');
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSubscriptions()
      .then(data => {
        const list = Array.isArray(data) ? data : (data?.value || []);
        setSubscriptions(list);
        if (list.length > 0 && !subscription) setSubscription(list[0].subscriptionId);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <QueryClientProvider client={qc}>
      <AppCtx.Provider value={{ subscription, setSubscription, subscriptions, loading }}>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </AppCtx.Provider>
    </QueryClientProvider>
  );
}
