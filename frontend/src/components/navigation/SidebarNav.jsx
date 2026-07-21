import React, { useCallback, useEffect, useMemo } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard, HardDrive, Database, Shield, DollarSign, Search,
  ChevronRight, Server, Container, KeyRound, AppWindow, Layers,
  GitBranch, CloudCog, Settings, Boxes, Globe, Network,
} from 'lucide-react';
import AssetIcon from '../AssetIcon';
import usePersistedState from '../../hooks/usePersistedState';
import { AppCtx } from '../../App';
import { fetchResourceCounts, fetchFindingsSummary } from '../../api/azure';
import {
  OVERVIEW_NAV,
  ADVANCED_NAV_GROUPS,
  NAV_GROUP_EXTRA_LINKS,
  SYSTEM_NAV_GROUP,
  systemNavGroupOpen,
  systemNavItems,
  NAV_RESOURCE_GROUPS,
  RESOURCE_PAGES,
  DEFAULT_NAV_OPEN,
  groupForPath,
  PAGE_ICON_KEYS,
  NAV_GROUP_KEYS,
  NAV_LINK_HINTS,
  visibleNavGroups,
  syncTypesForResourceIds,
  categoryResourceCount,
} from '../../config/appRegistry';
import CategorySyncButton from './CategorySyncButton';
import SidebarRailTooltip from './SidebarRailTooltip';
import { useNavAccess } from '../../hooks/useNavAccess';
import { useAuth } from '../../context/AuthContext';
import { openFindingsCount } from '../../utils/findingsSummaryUtils';

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

function navHint(path, title) {
  if (NAV_LINK_HINTS[path]) return NAV_LINK_HINTS[path];
  const page = Object.values(RESOURCE_PAGES).find((p) => p.path === path);
  if (page) return 'Inventory and metrics';
  return title;
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
    <div className={`nav-group nav-group--collapsible${open ? ' nav-group--open' : ''}`}>
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

  const { data: findingsSummary } = useQuery({
    queryKey: ['findings-summary-nav', subscription],
    queryFn: () => fetchFindingsSummary({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 60_000,
  });

  const actionCentreBadge = openFindingsCount(findingsSummary);

  const navResourceGroups = useMemo(
    () => (subscription ? visibleNavGroups(counts) : []),
    [subscription, counts],
  );

  const showResourceNav = Boolean(subscription);
  const hasManageContent = showResourceNav || advancedNavGroups.length > 0 || systemNav.length > 0;

  useEffect(() => {
    const activeGroup = groupForPath(location.pathname);
    if (activeGroup && !groups[activeGroup]) {
      setGroups((prev) => ({ ...prev, [activeGroup]: true }));
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleGroup = useCallback((id) => {
    setGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }, [setGroups]);

  const navLink = (path, label, iconKey, {
    end = false,
    sub = false,
    badge = 0,
    disabled = false,
  } = {}) => {
    if (collapsed && sub) return null;

    const hint = navHint(path, label);
    const content = (
      <>
        <span className={collapsed ? 'sidebar-rail-btn__icon' : 'nav-link__icon'}>
          <NavIcon iconKey={iconKey} size={sub && !collapsed ? 14 : 18} />
        </span>
        {!collapsed && (
          <span className="nav-link__text">
            <span className="nav-link__label">{label}</span>
            <span className="nav-link__hint">{hint}</span>
          </span>
        )}
        {!collapsed && badge > 0 && (
          <span className="nav-badge" aria-label={`${badge} open items`}>{badge}</span>
        )}
      </>
    );

    if (disabled) {
      if (collapsed) return null;
      return (
        <span
          key={path}
          className="nav-link nav-link--disabled"
          aria-disabled="true"
          tabIndex={-1}
        >
          {content}
        </span>
      );
    }

    const link = (
      <NavLink
        key={path}
        to={path}
        end={end}
        className={({ isActive }) => [
          collapsed ? 'sidebar-rail-btn' : 'nav-link',
          sub && !collapsed ? 'nav-link--sub' : '',
          isActive ? 'active' : '',
        ].filter(Boolean).join(' ')}
        onClick={onNavClick}
        aria-label={collapsed ? label : undefined}
      >
        {content}
      </NavLink>
    );

    if (!collapsed) return link;
    return (
      <SidebarRailTooltip key={path} label={label}>
        {link}
      </SidebarRailTooltip>
    );
  };

  const collapsedRail = (
    <>
      {overviewNav.map((item) => navLink(item.path, item.title, item.iconKey, {
        end: item.end,
        badge: item.path === '/action-centre' ? actionCentreBadge : 0,
      }))}

      {collapsed && advancedNavGroups.length > 0 && <SidebarRailDivider />}

      {advancedNavGroups.map((group, groupIndex) => (
        <React.Fragment key={group.id}>
          {collapsed && groupIndex > 0 && <SidebarRailDivider />}
          {group.items.map((item) => navLink(item.path, item.title, item.iconKey))}
        </React.Fragment>
      ))}

      {collapsed && (advancedNavGroups.length > 0 || showResourceNav) && <SidebarRailDivider />}

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

      {showResourceNav && canView('section:resources') && navResourceGroups.length > 0 && collapsed && (
        <SidebarRailDivider />
      )}

      {showResourceNav && canView('section:resources') && navResourceGroups.map((group) => {
        if (!canView(`section:resources:${group.id}`)) return null;
        const visibleIds = group.resourceIds.filter((id) => canView(RESOURCE_PAGES[id]?.path));
        if (!visibleIds.length) return null;
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
            headerAction={null}
          >
            {visibleIds.map((resourceId) => {
              const page = RESOURCE_PAGES[resourceId];
              return navLink(page.path, page.navLabel, page.iconKey, { sub: true });
            })}
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
          {systemNav.map((item) => navLink(item.path, item.title, item.iconKey, { sub: true }))}
        </NavGroup>
      )}
    </>
  );

  const expandedNav = (
    <nav className="nav" aria-label="Main">
      {overviewNav.length > 0 && (
        <div className="nav-group">
          <span className="nav-group__label">Workspace</span>
          {overviewNav.map((item) => navLink(item.path, item.title, item.iconKey, {
            end: item.end,
            badge: item.path === '/action-centre' ? actionCentreBadge : 0,
          }))}
        </div>
      )}

      {hasManageContent && (
        <div className="nav-group">
          <span className="nav-group__label">Manage</span>

          {!showResourceNav && (
            <p className="sidebar-nav__hint">Select a subscription to browse resources.</p>
          )}

          {showResourceNav && canView('section:resources') && navResourceGroups.length > 0 && (
            <>
              <span className="nav-group__sublabel">Resources</span>
              {navResourceGroups.map((group) => {
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
                    collapsed={false}
                    onExpandSidebar={onExpandSidebar}
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
            </>
          )}

          {advancedNavGroups.map((group) => (
            <React.Fragment key={group.id}>
              <span className="nav-group__sublabel">{group.label}</span>
              {group.items.map((item) => navLink(item.path, item.title, item.iconKey))}
            </React.Fragment>
          ))}

          {systemNav.length > 0 && (
            <NavGroup
              id={SYSTEM_NAV_GROUP.id}
              label={SYSTEM_NAV_GROUP.label}
              iconKey={SYSTEM_NAV_GROUP.iconKey}
              color={SYSTEM_NAV_GROUP.color}
              open={systemNavGroupOpen(groups)}
              collapsed={false}
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
      )}
    </nav>
  );

  return (
    <div className={`sidebar-nav${collapsed ? ' sidebar-nav--collapsed' : ''}`}>
      {collapsed ? collapsedRail : expandedNav}
    </div>
  );
}
