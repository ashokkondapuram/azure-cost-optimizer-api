/**
 * SidebarNav — collapsible two-group sidebar navigation
 *
 * Groups:
 *   Core         — always visible (Overview)
 *   Advanced     — collapsible (Waste Heatmap … AI Analysis)
 *   Optimization — collapsible (Reservation Advisor … Demand Forecaster)
 */
import React, { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Flame, Tag, CalendarClock, Bell, TrendingUp, GitCommitHorizontal,
  Zap,
  BookMarked, Shield, Layers, Download, BarChart2,
  ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  ADVANCED_TOOLS_NAV, ADVANCED_NAV_GROUP,
  OPTIMIZATION_NAV, OPTIMIZATION_NAV_GROUP,
  DEFAULT_NAV_OPEN, groupForPath,
} from '../appRegistry';

const ICON_MAP = {
  '/':                   LayoutDashboard,
  '/advisor':            Flame,
  '/tag-compliance':     Tag,
  '/auto-scheduler':     CalendarClock,
  '/notifications':      Bell,
  '/anomaly-detector':   TrendingUp,
  '/timeline':           GitCommitHorizontal,
  '/ai-analysis':        Zap,
  '/reservation-advisor':BookMarked,
  '/governance':         Shield,
  '/cost-allocation':    Layers,
  '/export-center':      Download,
  '/demand-forecaster':  BarChart2,
};

const GROUP_ACCENT = {
  indigo: {
    btn:    'hover:bg-indigo-50 dark:hover:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300',
    dot:    'bg-indigo-400',
    active: 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300',
  },
  teal: {
    btn:    'hover:bg-teal-50 dark:hover:bg-teal-900/20 text-teal-700 dark:text-teal-300',
    dot:    'bg-teal-500',
    active: 'bg-teal-50 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300',
  },
};

function NavItem({ path, title, accent }) {
  const Icon = ICON_MAP[path] ?? LayoutDashboard;
  return (
    <NavLink
      to={path}
      end={path === '/'}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
          isActive
            ? (accent?.active ?? 'bg-teal-50 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300')
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100'
        }`
      }
    >
      <Icon size={16} strokeWidth={1.8} />
      <span>{title}</span>
    </NavLink>
  );
}

function NavGroup({ group, items, open, onToggle }) {
  const accent = GROUP_ACCENT[group.color] ?? GROUP_ACCENT.teal;
  return (
    <div className="mb-1">
      <button
        onClick={onToggle}
        className={`w-full flex items-center justify-between rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors ${accent.btn}`}
      >
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${accent.dot}`} />
          {group.label}
        </div>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="mt-0.5 ml-2 pl-2 border-l border-gray-200 dark:border-gray-700 space-y-0.5">
          {items.map((item) => (
            <NavItem key={item.path} path={item.path} title={item.title} accent={accent} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function SidebarNav() {
  const location = useLocation();
  const [open, setOpen] = useState({ ...DEFAULT_NAV_OPEN });

  // Auto-expand the group containing the active route
  useEffect(() => {
    const grp = groupForPath(location.pathname);
    if (grp && !open[grp]) setOpen((o) => ({ ...o, [grp]: true }));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggle(id) { setOpen((o) => ({ ...o, [id]: !o[id] })); }

  return (
    <nav className="flex flex-col gap-1 p-3">
      {/* Core */}
      <NavItem path="/" title="Overview" />

      <div className="my-1 border-t border-gray-100 dark:border-gray-800" />

      {/* Advanced tools */}
      <NavGroup
        group={ADVANCED_NAV_GROUP}
        items={ADVANCED_TOOLS_NAV}
        open={open.advanced}
        onToggle={() => toggle('advanced')}
      />

      {/* Optimization */}
      <NavGroup
        group={OPTIMIZATION_NAV_GROUP}
        items={OPTIMIZATION_NAV}
        open={open.optimization}
        onToggle={() => toggle('optimization')}
      />
    </nav>
  );
}
