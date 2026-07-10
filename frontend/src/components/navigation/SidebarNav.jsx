import React, { useCallback, useEffect, useMemo } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard, HardDrive, Database, Shield, DollarSign, Search,
  ChevronRight, Server, Container, KeyRound, AppWindow, Layers,
  GitBranch, CloudCog, Settings, Boxes, Globe, Network,
  ChevronsDownUp, ChevronsUpDown, Sparkles,
} from 'lucide-react';
import AssetIcon from '../AssetIcon';
import usePersistedState from '../../hooks/usePersistedState';
import { useAuth } from '../../context/AuthContext';
import { AppCtx } from '../../App';
import { fetchResourceCounts } from '../../api/azure';
import {
  OVERVIEW_NAV,
  ADVANCED_NAV_GROUPS,
  ADVANCED_SECTION_ID,
  advancedNavGroupOpen,
  advancedNavSectionOpen,
  NAV_GROUP_EXTRA_LINKS,
  SYSTEM_NAV_GROUP,
  systemNavGroupOpen,
  systemNavItems,
  isSystemNavVisible,
  isAdvancedPath,
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
import SidebarRailTooltip from './SidebarRailTooltip';
import { useNavAccess } from '../../hooks/useNavAccess';

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

function NavIcon({ iconKey, size = 14 }) {
  const Fallback = FALLBACK_ICONS[iconKey] || Boxes;
  return <AssetIcon iconKey={PAGE_ICON_KEYS[iconKey]} size={size} fallback={<Fallback size={size} />} />;
}

function SidebarRailDivider() {
  return <div className="sidebar-rail-divider" aria-hidden />;
}

function NavGroup({
  id, label, iconKey, color, open, onToggle, badge, headerAction, children,
  collapsed = false, onExpandSidebar,
}) {
  const handleCollapsedClick = () => {
    onExpandSidebar?.();
    if (!open) onToggle();
  };

  if (collapsed) {
    return (
      <SidebarRailTooltip label={label}>
        <button
          type="button"
          className={`sidebar-rail-btn nav-item--collapsed-group${open ? ' nav-item--collapsed-group-open' : ''}`}
          aria-label={label}
          aria-expanded={open}
          onClick={handleCollapsedClick}
        >
          <span className="sidebar-rail-btn__icon" style={{ color }}>
            <AssetIcon iconKey={NAV_GROUP_KEYS[iconKey]} size={18} />
          </span>
        </button>
      </SidebarRailTooltip>
    );
  }

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

export default function SidebarNav({ onNavClick, collapsed = false, onExpandSidebar }) {
  const location = useLocation();
  const { subscription } = React.useContext(AppCtx);
  const { isAdmin } = useAuth();
  const { canView } = useNavAccess();
  const [groups, setGroups] = usePersistedState('finops-nav-groups', DEFAULT_NAV_OPEN);

  const overviewNav = useMemo(
    () => (canView('section:overview')
      ? OVERVIEW_NAV.filter((item) => canView(item.path))
      : []),
    [canView],
  );
  const advancedNavGroups = useMemo(
    () => (canView('section:advanced')
      ? ADVANCED_NAV_GROUPS
        .filter((group) => canView(`section:advanced:${group.id}`))
        .map((group) => ({
          ...group,
          items: group.items.filter((item) => canView(item.path)),
        }))
        .filter((group) => group.items.length > 0)
      : []),
    [canView],
  );
  const systemNav = useMemo(
    () => (canView('section:system')
      ? systemNavItems(isAdmin).filter((item) => canView(item.path))
      : []),
    [isAdmin, canView],
  );

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
  const advancedSectionOpen = advancedNavSectionOpen(groups);

  useEffect(() => {
    const activeGroup = groupForPath(location.pathname);
    const updates = {};
    if (activeGroup && !groups[activeGroup]) {
      updates[activeGroup] = true;
    }
    if (isAdvancedPath(location.pathname) && !advancedNavSectionOpen(groups)) {
      updates[ADVANCED_SECTION_ID] = true;
    }
    if (Object.keys(updates).length) {
      setGroups((prev) => ({ ...prev, ...updates }));
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleGroup = useCallback((id) => {
    setGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }, [setGroups]);

  const allAdvancedOpen = advancedNavGroups.length > 0
    && advancedNavGroups.every((g) => advancedNavGroupOpen(groups, g.id));
  const toggleAllAdvanced = () => {
    const next = !allAdvancedOpen;
    setGroups((prev) => {
      const updated = { ...prev };
      advancedNavGroups.forEach((g) => { updated[g.id] = next; });
      return updated;
    });
  };

  const toggleAdvancedSection = () => {
    setGroups((prev) => ({
      ...prev,
      [ADVANCED_SECTION_ID]: !advancedNavSectionOpen(prev),
    }));
  };

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

  const navLink = (path, label, iconKey, { end = false, sub = false } = {}) => {
    if (collapsed && sub) return null;
    const link = (
      <NavLink
        key={path}
        to={path}
        end={end}
        className={({ isActive }) => [
          collapsed ? 'sidebar-rail-btn' : 'nav-item',
          sub && !collapsed ? 'nav-sub' : '',
          isActive ? 'active' : '',
        ].filter(Boolean).join(' ')}
        onClick={onNavClick}
        aria-label={collapsed ? label : undefined}
      >
        <span className={collapsed ? 'sidebar-rail-btn__icon' : undefined}>
          <NavIcon iconKey={iconKey} size={sub && !collapsed ? 14 : 18} />
        </span>
        {!collapsed && <span className="nav-item__label">{label}</span>}
      </NavLink>
    );
    if (!collapsed) return link;
    return (
      <SidebarRailTooltip key={path} label={label}>
        {link}
      </SidebarRailTooltip>
    );
  };

  return (
    <div className={`sidebar-nav${collapsed ? ' sidebar-nav--collapsed' : ''}`}>
      {!collapsed && overviewNav.length > 0 && <div className="sidebar-section">Overview</div>}
      {overviewNav.map((item) => navLink(item.path, item.title, item.iconKey, { end: item.end }))}

      {collapsed && (advancedNavGroups.length > 0 || showResourceNav) && <SidebarRailDivider />}

      {/* ── Advanced tool groups ─────────────────────────────────── */}
      {advancedNavGroups.length > 0 && (
        <>
          {collapsed ? (
            <SidebarRailTooltip label="Advanced tools">
              <button
                type="button"
                className={`sidebar-rail-btn sidebar-rail-btn--section${advancedSectionOpen ? ' active' : ''}`}
                aria-label="Advanced tools"
                aria-expanded={advancedSectionOpen}
                onClick={() => {
                  onExpandSidebar?.();
                  setGroups((prev) => ({ ...prev, [ADVANCED_SECTION_ID]: true }));
                }}
              >
                <span className="sidebar-rail-btn__icon">
                  <Sparkles size={18} />
                </span>
              </button>
            </SidebarRailTooltip>
          ) : (
            <div className="sidebar-section sidebar-section--row">
              <button
                type="button"
                className="sidebar-section__label-btn"
                onClick={toggleAdvancedSection}
                aria-expanded={advancedSectionOpen}
                aria-controls="sidebar-advanced-groups"
              >
                <span className={`sidebar-section__chevron${advancedSectionOpen ? ' sidebar-section__chevron--open' : ''}`}>
                  <ChevronRight size={13} />
                </span>
                Advanced
              </button>
              {advancedSectionOpen && (
                <button
                  type="button"
                  className="sidebar-section__toggle"
                  onClick={toggleAllAdvanced}
                  title={allAdvancedOpen ? 'Collapse all advanced groups' : 'Expand all advanced groups'}
                  aria-label={allAdvancedOpen ? 'Collapse all advanced groups' : 'Expand all advanced groups'}
                >
                  {allAdvancedOpen ? <ChevronsDownUp size={13} /> : <ChevronsUpDown size={13} />}
                </button>
              )}
            </div>
          )}
          {(collapsed || advancedSectionOpen) && (
            <div id="sidebar-advanced-groups" className={`sidebar-advanced-groups${collapsed ? ' sidebar-advanced-groups--rail' : ''}`}>
              {advancedNavGroups.map((group) => (
                <NavGroup
                  key={group.id}
                  id={group.id}
                  label={group.label}
                  iconKey={group.iconKey}
                  color={group.color}
                  open={advancedNavGroupOpen(groups, group.id)}
                  collapsed={collapsed}
                  onExpandSidebar={onExpandSidebar}
                  onToggle={() => {
                    setGroups((prev) => ({
                      ...prev,
                      [group.id]: !advancedNavGroupOpen(prev, group.id),
                    }));
                  }}
                >
                  {group.items.map((item) =>
                    navLink(item.path, item.title, item.iconKey, { sub: true })
                  )}
                </NavGroup>
              ))}
            </div>
          )}
        </>
      )}

      {!collapsed && canView('section:resources') && (
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
      )}

      {collapsed && showResourceNav && canView('section:resources') && navResourceGroups.length === 0 && (
        <SidebarRailDivider />
      )}

      {collapsed && showResourceNav && canView('section:resources') && navResourceGroups.length === 0 && (
        <SidebarRailTooltip label="Resources">
          <button
            type="button"
            className="sidebar-rail-btn sidebar-rail-btn--section"
            aria-label="Resources"
            onClick={onExpandSidebar}
          >
            <span className="sidebar-rail-btn__icon">
              <Layers size={18} />
            </span>
          </button>
        </SidebarRailTooltip>
      )}

      {!showResourceNav && !collapsed && (
        <p className="sidebar-nav__hint">Select a subscription to browse resources.</p>
      )}

      {showResourceNav && canView('section:resources') && navResourceGroups.length > 0 && collapsed && (
        <SidebarRailDivider />
      )}

      {showResourceNav && canView('section:resources') && navResourceGroups.map((group) => {
        if (!canView(`section:resources:${group.id}`)) return null;
        const visibleIds = group.resourceIds.filter((id) => canView(RESOURCE_PAGES[id]?.path));
        if (!visibleIds.length) return null;
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
            collapsed={collapsed}
            onExpandSidebar={onExpandSidebar}
            onToggle={() => toggleGroup(group.id)}
            headerAction={!collapsed && isAdmin && !countsLoading && badge === 0 ? (
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

      {systemNav.length > 0 && collapsed && <SidebarRailDivider />}

      {systemNav.length > 0 && (
        <NavGroup
          id={SYSTEM_NAV_GROUP.id}
          label={SYSTEM_NAV_GROUP.label}
          iconKey={SYSTEM_NAV_GROUP.iconKey}
          color={SYSTEM_NAV_GROUP.color}
          open={systemNavGroupOpen(groups)}
          collapsed={collapsed}
          onExpandSidebar={onExpandSidebar}
          onToggle={() => {
            setGroups((prev) => ({
              ...prev,
              [SYSTEM_NAV_GROUP.id]: !systemNavGroupOpen(prev),
            }));
          }}
        >
          {(() => {
            let lastSection = null;
            return systemNav.flatMap((item) => {
              const nodes = [];
              if (!collapsed && item.section && item.section !== lastSection) {
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
