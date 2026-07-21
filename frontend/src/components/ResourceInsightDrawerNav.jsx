import React, { forwardRef } from 'react';
import {
  Activity,
  AlertTriangle,
  DollarSign,
  Layers,
  LayoutDashboard,
  Lightbulb,
  List,
  PanelLeftClose,
  PanelLeftOpen,
  Settings2,
  Sparkles,
  Tag,
  TrendingUp,
  Zap,
} from 'lucide-react';

const SECTION_ICONS = {
  overview: LayoutDashboard,
  findings: AlertTriangle,
  'cost-drivers': DollarSign,
  trends: TrendingUp,
  cost: DollarSign,
  properties: Settings2,
  metrics: Activity,
  analysis: Sparkles,
  advisor: Lightbulb,
  tags: Tag,
  pools: Layers,
  actions: Zap,
};

function sanitizeDrawerDomId(sectionId) {
  return String(sectionId || 'section').replace(/[^a-zA-Z0-9_-]/g, '-');
}

function sectionIcon(section) {
  if (SECTION_ICONS[section.id]) return SECTION_ICONS[section.id];
  return List;
}

function sectionTooltip(section) {
  if (!section.badge || section.badge <= 0) return section.label;
  const count = section.badge > 999 ? '999+' : section.badge;
  return `${section.label} (${count})`;
}

/**
 * Vertical nav — scroll-spy highlights shift as the flow body scrolls.
 * Supports expanded labels or a collapsed icon rail with tooltips.
 */
const ResourceInsightDrawerNav = forwardRef(function ResourceInsightDrawerNav({
  sections,
  activeSection,
  onNavigate,
  expanded = false,
  collapsed = false,
  onToggleCollapse,
}, ref) {
  if (!sections.length) return null;

  return (
    <nav
      ref={ref}
      className={[
        'insight-drawer__nav',
        'insight-drawer__nav--vertical',
        'insight-drawer__nav--v2',
        expanded ? 'insight-drawer__nav--expanded' : '',
        collapsed ? 'insight-drawer__nav--collapsed' : '',
      ].filter(Boolean).join(' ')}
      aria-label="Resource insight sections"
      aria-expanded={!collapsed}
    >
      <div className="insight-drawer__nav-items">
        {sections.map((section) => {
          const Icon = sectionIcon(section);
          const isActive = activeSection === section.id;
          const panelId = sanitizeDrawerDomId(section.id);
          const badgeLabel = section.badge > 999 ? '999+' : section.badge;
          return (
            <button
              key={section.id}
              type="button"
              id={`drawer-tab-${panelId}`}
              aria-current={isActive ? 'true' : undefined}
              aria-label={collapsed ? sectionTooltip(section) : undefined}
              title={collapsed ? sectionTooltip(section) : undefined}
              className={`insight-drawer__nav-item${isActive ? ' insight-drawer__nav-item--active' : ''}`}
              onClick={() => onNavigate(section.id)}
            >
              {Icon && (
                <span className="insight-drawer__nav-icon" aria-hidden>
                  <Icon size={expanded && !collapsed ? 16 : 14} />
                  {collapsed && section.badge > 0 && (
                    <span className="insight-drawer__nav-badge-dot" aria-hidden />
                  )}
                </span>
              )}
              <span className="insight-drawer__nav-label">{section.label}</span>
              {!collapsed && section.badge > 0 && (
                <span className="insight-drawer__nav-badge">
                  {badgeLabel}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {typeof onToggleCollapse === 'function' && (
        <button
          type="button"
          className="insight-drawer__nav-toggle"
          onClick={onToggleCollapse}
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      )}
    </nav>
  );
});

export default ResourceInsightDrawerNav;

export function focusSectionToTab(focusSection) {
  if (!focusSection) return 'overview';
  if (focusSection === 'advanced-analysis') return 'analysis';
  if (focusSection === 'cost-signals' || focusSection === 'cost-drivers') return 'cost-drivers';
  if (focusSection === 'consistency-policy'
    || focusSection === 'prop-consistencyPolicy'
    || focusSection === 'tag-compliance') {
    return 'overview';
  }
  if (focusSection === 'technical-properties' || focusSection === 'details') return 'overview';
  if (focusSection === 'vm-metrics') return 'metrics';
  if (focusSection === 'proposed-actions') return 'actions';
  if (focusSection.startsWith('prop:') || focusSection.startsWith('prop-')) return 'overview';
  if (focusSection === 'assessment') return 'analysis';
  return focusSection;
}
