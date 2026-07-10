/**
 * Shared UI primitives for advanced tool pages — KPIs, banners, cards, tables.
 */
import React from 'react';
import { RefreshCw, X, Database, Cloud, Sparkles, Cpu } from 'lucide-react';

export const fmtCurrency = (n, currency = 'CAD') =>
  n != null
    ? new Intl.NumberFormat('en-CA', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
    : '—';

export function AdvSkeleton({ className = '', style }) {
  return <div className={`adv-skeleton ${className}`} style={style} aria-hidden />;
}

export function AdvKpiCard({
  label, value, sub, icon: Icon, accent, active, onClick, variant,
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      className={[
        'anomaly-kpi',
        onClick ? 'anomaly-kpi--clickable' : '',
        active ? 'anomaly-kpi--active' : '',
        variant ? `anomaly-kpi--${variant}` : '',
      ].filter(Boolean).join(' ')}
      onClick={onClick}
    >
      {Icon && (
        <div className={`anomaly-kpi__icon ${accent || ''}`}>
          <Icon size={16} />
        </div>
      )}
      <div>
        <p className="anomaly-kpi__label">{label}</p>
        <p className="anomaly-kpi__value">{value}</p>
        {sub && <p className="anomaly-kpi__sub">{sub}</p>}
      </div>
    </Tag>
  );
}

export function AdvKpiGrid({ children, columns = 4, className = '' }) {
  const colStyle = columns === 2
    ? { gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }
    : undefined;
  return (
    <div className={`anomaly-kpi-grid adv-kpi-grid adv-kpi-grid--${columns} ${className}`} style={colStyle}>
      {children}
    </div>
  );
}

export function AdvKpiSkeleton({ count = 4 }) {
  return (
    <AdvKpiGrid>
      {Array.from({ length: count }).map((_, i) => (
        <AdvSkeleton key={i} className="h-[4.5rem] rounded-xl" />
      ))}
    </AdvKpiGrid>
  );
}

const SOURCE_ICON = {
  azure_live: Cloud,
  database: Database,
  azure_inventory: Cloud,
  azure_advisor_db: Sparkles,
  azure_reservation_recommendations: Sparkles,
  engine_findings: Cpu,
};

export function AdvSourceChips({ sources, labels, className = '' }) {
  if (!sources && !labels?.length) return null;

  const chips = labels ?? [
    sources?.cost_baseline === 'azure_live' && 'Azure live cost',
    sources?.cost_baseline === 'database' && 'Synced DB',
    sources?.azure_inventory && 'Azure inventory',
    sources?.azure_advisor_db && 'Azure Advisor',
    sources?.azure_reservation_recommendations && 'RI recommendations',
    sources?.azure_live && 'Azure inventory',
    sources?.engine_findings && 'Engine findings',
  ].filter(Boolean);

  if (!chips.length) return null;

  return (
    <div className={`adv-source-bar ${className}`}>
      <span className="adv-source-bar__label">Data sources</span>
      <div className="adv-source-bar__chips">
        {chips.map((label) => {
          const Icon = SOURCE_ICON[label] || null;
          return (
            <span key={label} className="adv-source-chip">
              {Icon && <Icon size={11} />}
              {label}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function AdvWarningsBanner({ warnings, onDismiss, className = '' }) {
  if (!warnings?.length) return null;
  return (
    <div className={`adv-warnings-banner ${className}`} role="status">
      <div className="adv-warnings-banner__body">
        <ul className="adv-warnings-banner__list">
          {warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
        {onDismiss && (
          <button type="button" className="adv-warnings-banner__dismiss chip" onClick={onDismiss} aria-label="Dismiss warnings">
            <X size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

export function AdvEmptyState({ title, description, action, icon: Icon, className = '' }) {
  return (
    <div className={`adv-empty-state ${className}`}>
      {Icon && (
        <div className="adv-empty-state__icon">
          <Icon size={22} />
        </div>
      )}
      <strong>{title}</strong>
      {description && <span>{description}</span>}
      {action}
    </div>
  );
}

export function AdvSyncButton({ onClick, syncing, loading, label = 'Sync from Azure' }) {
  return (
    <button
      type="button"
      className="adv-sync-btn chip"
      onClick={onClick}
      disabled={syncing || loading}
    >
      <RefreshCw size={14} className={syncing ? 'adv-spin' : ''} />
      {syncing ? 'Syncing…' : label}
    </button>
  );
}

export function AdvMetaBar({ items, className = '' }) {
  if (!items?.length) return null;
  return (
    <div className={`adv-meta-bar ${className}`}>
      {items.map((item) => (
        <span key={item} className="adv-meta-bar__item">{item}</span>
      ))}
    </div>
  );
}

export function AdvPageCard({
  title,
  subtitle,
  children,
  actions,
  accent,
  className = '',
  bodyClassName = '',
  noPadding = false,
}) {
  return (
    <section className={`anomaly-page-card adv-page-card${accent ? ` adv-page-card--${accent}` : ''} ${className}`}>
      {(title || subtitle || actions) && (
        <div className="tag-rg-explorer__header adv-page-card__header">
          <div>
            {title && <h3 className="tag-rg-explorer__title">{title}</h3>}
            {subtitle && <p className="tag-rg-explorer__sub">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={`adv-page-card__body${noPadding ? ' adv-page-card__body--flush' : ''} ${bodyClassName}`}>
        {children}
      </div>
    </section>
  );
}

export function AdvFilterChips({ options, value, onChange, className = '' }) {
  if (!options?.length) return null;
  return (
    <div className={`adv-filter-chips toolbar ${className}`}>
      {options.map((opt) => {
        const id = typeof opt === 'string' ? opt : opt.id;
        const label = typeof opt === 'string' ? opt.replace(/_/g, ' ') : opt.label;
        return (
          <button
            key={id}
            type="button"
            className={`chip${value === id ? ' active' : ''}`}
            onClick={() => onChange(id)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function AdvHighlightPanel({ title, count, subtitle, icon: Icon, accent, children, className = '' }) {
  return (
    <div className={`ai-analysis-hp adv-highlight-panel${accent ? ` adv-highlight-panel--${accent}` : ''} ${className}`}>
      <div className="ai-analysis-hp__head adv-highlight-panel__head">
        {Icon && <Icon size={15} className={`adv-highlight-panel__icon adv-highlight-panel__icon--${accent || 'default'}`} />}
        <h2 className="ai-analysis-hp__title">{title}</h2>
        {count != null && <span className="chip active">{count}</span>}
        {subtitle && <p className="ai-analysis-hp__sub">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function AdvSeverityBadge({ severity, className = '' }) {
  const key = (severity || 'medium').toLowerCase();
  return (
    <span className={`anomaly-alert__badge anomaly-alert__badge--${key} ${className}`}>
      {severity}
    </span>
  );
}

export function AdvDataTable({ columns, rows, emptyMessage, maxHeight, onRowClick, activeRowKey, rowKey }) {
  if (!rows?.length) {
    return emptyMessage ? (
      <div className="tag-rg-explorer__empty" style={{ minHeight: '8rem' }}>
        <strong>{emptyMessage}</strong>
      </div>
    ) : null;
  }

  return (
    <div className="tag-rg-explorer__scroll" style={maxHeight ? { maxHeight } : undefined}>
      <table className="tag-rg-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key || col}>{typeof col === 'string' ? col : col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const key = rowKey ? rowKey(row, i) : row.id ?? i;
            const active = activeRowKey != null && activeRowKey === key;
            return (
              <tr
                key={key}
                className={`tag-rg-table__row${active ? ' tag-rg-table__row--active' : ''}${onRowClick ? ' tag-rg-table__row--clickable' : ''}`}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                role={onRowClick ? 'button' : undefined}
                tabIndex={onRowClick ? 0 : undefined}
              >
                {columns.map((col) => {
                  const colKey = typeof col === 'string' ? col : col.key;
                  const render = typeof col === 'object' && col.render;
                  return (
                    <td
                      key={colKey}
                      className={col.className || (colKey === columns[0]?.key || colKey === columns[0] ? 'tag-rg-table__name' : 'tag-rg-table__count')}
                    >
                      {render ? render(row) : row[colKey]}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function AdvPageStack({ children, className = '' }) {
  return <div className={`adv-page-stack ${className}`}>{children}</div>;
}
