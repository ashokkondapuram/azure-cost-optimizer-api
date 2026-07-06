import React, { useCallback, useEffect, useMemo } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard, HardDrive, Database, Shield, DollarSign, Search,
  ChevronRight, Server, Container, KeyRound, AppWindow, Layers,
  GitBranch, CloudCog, Settings, Boxes, Globe, Network,
  ChevronsDownUp, ChevronsUpDown, Flame, Tag, CalendarClock,
  Bell, TrendingUp, GitCommitHorizontal, Wallet, PiggyBank, ShieldCheck,
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
  '/waste-heatmap':    Flame,
  '/tag-compliance':   Tag,
  '/auto-scheduler':   CalendarClock,
  '/notifications':    Bell,
  '/anomaly-detector': TrendingUp,
  '/timeline':         GitCommitHorizontal,
  // Phase 2
  '/budgets':          Wallet,
  '/savings-planner':  PiggyBank,
  '/policy':           ShieldCheck,
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
        <div className="