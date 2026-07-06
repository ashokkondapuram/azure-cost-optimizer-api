import React, { useCallback, useEffect, useMemo } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard, HardDrive, Database, Shield, DollarSign, Search,
  ChevronRight, Server, Container, KeyRound, AppWindow, Layers,
  GitBranch, CloudCog, Settings, Boxes, Globe, Network,
  ChevronsDownUp, ChevronsUpDown, Flame, Tag, CalendarClock,
  Bell, TrendingUp, GitCommitHorizontal, Wallet, PiggyBank, ShieldCheck,
  BookMarked, ShieldCheck as GovernanceIcon, Layers as AllocationIcon, Download, BarChart2, Zap,
} from 'lucide-react';
import AssetIcon from '../AssetIcon';
import usePersistedState from '../../hooks/usePersistedState';
import { useAuth } from '../../context/AuthContext';
import { AppCtx } from '../../App';
import { fetchResourceCounts } from '../../api/azure';
import {
  OVERVIEW_NAV,
  ADVANCED_TOOLS_NAV,
  ADVANCED_NAV_GROUP,
  NAV_GROUP_EXTRA_LINKS,
  SYSTEM_NAV_GROUP,
  systemNavGroupOpen,
  systemNavItems,
  isSystemNavVisible,
  NAV_RESOURCE_GROUPS,
  RESOURCE_PAGES,
  DEFAULT_NAV_OPEN,
  groupForPath,
  PAGE_ICON_KEYS,
  NAV_GROUP_KEYS,
  visibleNavGroups,
  syncTypesForResourceIds,
  categoryResourceCount,
} from '../../config/appRegistry';
import CategorySyncButton from './CategorySyncButton';

const FALLBACK_ICONS = {
  dashboard: LayoutDashboard,
  costs: DollarSign,
  costResources: DollarSign,
  recommendations: Search,
  engine: CloudCog,
  optimization: CloudCog,
  apiExplorer: AppWindow,
  history: Search,
  settings: Settings,
  vms: Server,
  vmss: Server,
  disks: HardDrive,
  snapshots: HardDrive,
  aks: Boxes,
  acr: Container,
  kubernetes: Boxes,
  appservices: AppWindow,
  appserviceplans: Layers,
  storage: HardDrive,
  publicips: Globe,
  vnets: Network,
  nics: Network,
  natgateways: Network,
  loadbalancers: Layers,
  appgateways: GitBranch,
  nsgs: Shield,
  privateendpoints: Network,
  privatelinkservices: Network,
  privatedns: Network,
  sql: Database,
  cosmosdb: Database,
  postgresql: Database,
  redis: Database,
  monitoring: Search,
  integration: AppWindow,
  messaging: Boxes,
  analytics: DollarSign,
  backup: HardDrive,
  search: Search,
  keyvaults: KeyRound,
};

// Icons specifically for advanced tool nav items
const ADVANCED_ITEM_ICONS = {
  '/waste-heatmap':       Flame,
  '/tag-compliance':      Tag,
  '/auto-scheduler':      CalendarClock,
  '/notifications':       Bell,
  '/anomaly-detector':    TrendingUp,
  '/timeline':            GitCommitHorizontal,
  '/ai-analysis':         Zap,
  // Phase 2
  '/budgets':             Wallet,
  '/savings-planner':     PiggyBank,
  '/policy':              ShieldCheck,
  // Week 4
  '/reservation-advisor': BookMarked,
  '/governance':          GovernanceIcon,
  // Week 5
  '/cost-allocation':     AllocationIcon,
  '/export-center':       Download,
  // Ongoing
  '/demand-forecaster':   BarChart2,
};

function NavIcon({ iconKey, size = 14 }) {
  const Fallback = FALLBACK_ICONS[iconKey] || Boxes;
  return <AssetIcon iconKey={PAGE_ICON_KEYS[iconKey]} size={size} fallback={<Fallback size={size} />} />;
}

function NavGroup({
  id, label, iconKey, color, open, onToggle, badge, headerAction, children,
}) {
  return (
    <div className={`nav-group${open ? ' nav-group--open' : ''}`}>
      <div className="nav-group__header">
        <button
          type="button"
          className="nav-group-btn"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={`nav-group-${id}`}
        >
          <span className="nav-group-btn__icon" style={{ color }}>
            <AssetIcon iconKey={NAV_GROUP_KEYS[iconKey]} size={14} />
          </span>
          <span className="nav-group-btn__label">{label}</span>
          {badge > 0 && (
            <span className="nav-group-btn__badge" title={`${badge} synced resources`}>
              {badge}
            </span>
          )}
        </button>
        {headerAction}
        <button
          type="button"
          className="nav-group-btn__chevron-btn"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={`${open ? 'Collapse' : 'Expand'} ${label}`}
        >
          <span className={`nav-group-btn__chevron${open ? ' nav-group-btn__chevron--open' : ''}`}>
            <ChevronRight size={14} />
          </span>
        </button>
      </div>
      <div id={`nav-group-${id}`} className="nav-group__panel">
        <div className="nav-group__items">{children}</div>
      </div>
    </div>
  );
}

export default function SidebarNav({ onNavClick }) {
  const location = useLocation();
  const { subscription } = React.useContext(AppCtx);
  const { isAdmin } = useAuth();
  const [groups, setGroups] = usePersistedState('finops-nav-groups', DEFAULT_NAV_OPEN);

  const { data: counts = {}, isLoading: countsLoading } = useQuery({
    queryKey: ['resource-counts', subscription],
    queryFn: () => fetchResourceCounts(subscription),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const navResourceGroups = useMemo(
    () => (subscription ? visibleNavGroups(counts) : []),
    [subscription, counts],
  );

  const showResourceNav = Boolean(subscription);

  useEffect(() => {
    const activeGroup = groupForPath(location.pathname);
    if (activeGroup && !groups[activeGroup]) {
      setGroups((prev) => ({ ...prev, [activeGroup]: true }));
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleGroup = useCallback((id) => {
    setGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }, [setGroups]);

  const allResourceOpen = showResourceNav
    && NAV_RESOURCE_GROUPS.every((g) => groups[g.id]);
  const toggleAllResources = () => {
    const next = !allResourceOpen;
    setGroups((prev) => {
      const updated = { ...prev };
      NAV_RESOURCE_GROUPS.forEach((g) => { updated[g.id] = next; });
      return updated;
    });
  };

  const navLink = (path, label, iconKey, { end = false, sub = false, Icon = null } = {}) => (
    <NavLink
      key={path}
      to={path}
      end={end}
      className={({ isActive }) => `nav-item${sub ? ' nav-sub' : ''}${isActive ? ' active' : ''}`}
      onClick={onNavClick}
    >
      {Icon ? <Icon size={sub ? 14 : 16} /> : <NavIcon iconKey={iconKey} size={sub ? 14 : 16} />}
      {label}
    </NavLink>
  );

  return (
    <div className="sidebar-nav">
      <div className="sidebar-section">Overview</div>
      {OVERVIEW_NAV.map((item) => navLink(item.path, item.title, item.iconKey, { end: item.end }))}

      {/* ── Advanced tools collapsible group ───────────────────────── */}
      <NavGroup
        id={ADVANCED_NAV_GROUP.id}
        label={ADVANCED_NAV_GROUP.label}
        iconKey={ADVANCED_NAV_GROUP.iconKey}
        color={ADVANCED_NAV_GROUP.color}
        open={!!groups[ADVANCED_NAV_GROUP.id]}
        onToggle={() => toggleGroup(ADVANCED_NAV_GROUP.id)}
      >
        {ADVANCED_TOOLS_NAV.map((item) =>
          navLink(item.path, item.title, item.iconKey, {
            sub: true,
            Icon: ADVANCED_ITEM_ICONS[item.path] || null,
          }),
        )}
      </NavGroup>

      <div className="sidebar-section sidebar-section--row">
        <span>Resources</span>
        {showResourceNav && (
          <button
            type="button"
            className="sidebar-section__toggle"
            onClick={toggleAllResources}
            title={allResourceOpen ? 'Collapse all' : 'Expand all'}
            aria-label={allResourceOpen ? 'Collapse all resource categories' : 'Expand all resource categories'}
          >
            {allResourceOpen ? <ChevronsDownUp size={13} /> : <ChevronsUpDown size={13} />}
          </button>
        )}
      </div>

      {!showResourceNav && (
        <p className="sidebar-nav__hint">Select a subscription to browse resources.</p>
      )}

      {showResourceNav && navResourceGroups.map((group) => {
        const visibleIds = group.resourceIds;
        const categorySyncTypes = syncTypesForResourceIds(visibleIds);
        const fullGroup = NAV_RESOURCE_GROUPS.find((g) => g.id === group.id);
        const badge = categoryResourceCount(fullGroup, counts, {
          costOnly: Boolean(counts?.breakdown),
        });

        return (
          <NavGroup
            key={group.id}
            id={group.id}
            label={group.label}
            iconKey={group.iconKey}
            color={group.color}
            badge={countsLoading ? 0 : badge}
            open={!!groups[group.id]}
            onToggle={() => toggleGroup(group.id)}
            headerAction={isAdmin && !countsLoading && badge === 0 ? (
              <CategorySyncButton
                label={group.label}
                syncTypes={categorySyncTypes}
                variant="header"
              />
            ) : null}
          >
            {visibleIds.length === 0 ? (
              <p className="nav-group__empty">
                {isAdmin
                  ? 'Nothing synced in this category yet. Use Sync beside the category name.'
                  : 'No resources synced yet.'}
              </p>
            ) : (
              <>
                {visibleIds.map((resourceId) => {
                  const page = RESOURCE_PAGES[resourceId];
                  return navLink(page.path, page.navLabel, page.iconKey, { sub: true });
                })}
                {(NAV_GROUP_EXTRA_LINKS[group.id] || []).map((link) =>
                  navLink(link.path, link.title, link.iconKey, { sub: true }),
                )}
              </>
            )}
          </NavGroup>
        );
      })}

      {isSystemNavVisible(isAdmin) && (
        <NavGroup
          id={SYSTEM_NAV_GROUP.id}
          label={SYSTEM_NAV_GROUP.label}
          iconKey={SYSTEM_NAV_GROUP.iconKey}
          color={SYSTEM_NAV_GROUP.color}
          open={systemNavGroupOpen(groups)}
          onToggle={() => {
            setGroups((prev) => ({
              ...prev,
              [SYSTEM_NAV_GROUP.id]: !systemNavGroupOpen(prev),
            }));
          }}
        >
          {(() => {
            let lastSection = null;
            const entries = systemNavItems(isAdmin);
            return entries.flatMap((item) => {
              const nodes = [];
              if (item.section && item.section !== lastSection) {
                lastSection = item.section;
                nodes.push(
                  <p key={`section-${item.section}`} className="nav-group__section-label">
                    {item.section}
                  </p>,
                );
              }
              nodes.push(navLink(item.path, item.title, item.iconKey, { sub: true }));
              return nodes;
            });
          })()}
        </NavGroup>
      )}
    </div>
  );
}
