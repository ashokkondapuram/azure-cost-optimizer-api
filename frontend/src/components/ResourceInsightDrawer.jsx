import React, { useContext, useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  X, ExternalLink, AlertTriangle, Activity,
  Copy, Check, Server,
} from 'lucide-react';
import { toDisplayText } from '../utils/formatDisplay';
import { resolveResourceFindings } from '../utils/resourceFindingsUtils';
import { formatCurrency } from '../utils/format';
import { resourceTotalCost, resourceCostTrend } from '../utils/costCurrency';
import TrendBadge from './visual/TrendBadge';
import AssetIcon from './AssetIcon';
import InsightFindingsPanel from './InsightFindingsPanel';
import ResourceAzureMetrics from './ResourceAzureMetrics';
import ResourceCostDrivingSignals from './ResourceCostDrivingSignals';
import ResourceDrawerOverview from './ResourceDrawerOverview';
import DrawerCollapsibleSection from './DrawerCollapsibleSection';
import useResizableDrawerWidth from '../hooks/useResizableDrawerWidth';
import usePersistedMetricTimespan from '../hooks/usePersistedMetricTimespan';
import { useAuth } from '../context/AuthContext';
import { AppCtx } from '../App';
import TagEditor from './TagEditor';
import { iconForRow, resourceLabelForRow } from '../config/assetIcons';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import useDrawerResourceBundle from '../hooks/useDrawerResourceBundle';
import AdvisorResourceSection from './advisor/AdvisorResourceSection';
import AdvancedResourceSection from './optimization/AdvancedResourceSection';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import { countTriggerMetricsForFindings } from '../utils/triggerUtils';

function stateTone(state) {
  const value = String(state || '').toLowerCase();
  if (['running', 'active', 'online', 'associated', 'succeeded'].some((s) => value.includes(s))) {
    return 'ok';
  }
  if (['stopped', 'deallocated', 'failed', 'unattached'].some((s) => value.includes(s))) {
    return 'warn';
  }
  return 'muted';
}

function ResourceIdRow({ resourceId, compact = false }) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(resourceId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }, [resourceId]);

  return (
    <div className={`insight-drawer__resource-id${compact ? ' insight-drawer__resource-id--compact' : ''}`}>
      <span className="insight-drawer__resource-id-label">Resource ID</span>
      {isArmResourceId(resourceId) ? (
        <ArmResourceLink
          resourceId={resourceId}
          className="insight-drawer__resource-id-value"
        />
      ) : (
        <code className="insight-drawer__resource-id-value" title={resourceId}>{resourceId}</code>
      )}
      <button
        type="button"
        className="insight-drawer__resource-id-copy"
        onClick={onCopy}
        aria-label={copied ? 'Copied' : 'Copy resource ID'}
        title={copied ? 'Copied' : 'Copy resource ID'}
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </button>
    </div>
  );
}

export default function ResourceInsightDrawer({
  resource,
  findings = [],
  indexReady = true,
  onClose,
  title,
  iconKey,
  apiPath,
  suppressLiveMetrics = false,
  currency = 'CAD',
  children,
}) {
  const { isAdmin } = useAuth();
  const { subscription } = useContext(AppCtx);
  const { width: drawerWidth, onResizeStart } = useResizableDrawerWidth();
  const [metricsTimespan, onMetricsTimespanChange] = usePersistedMetricTimespan(
    'finops-drawer-metrics-timespan',
  );
  const [localTags, setLocalTags] = useState(null);
  const [metricsSectionOpen, setMetricsSectionOpen] = useState(true);
  const [costDriversSectionOpen, setCostDriversSectionOpen] = useState(true);
  const drawerRef = useRef(null);
  const closeBtnRef = useRef(null);

  useEffect(() => {
    setLocalTags(null);
  }, [resource?.id, resource?.resource_id]);

  useEffect(() => {
    closeBtnRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousFocus = document.activeElement;
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      if (previousFocus && typeof previousFocus.focus === 'function') {
        previousFocus.focus();
      }
    };
  }, [onClose]);

  const resolved = useMemo(() => {
    if (!resource) return null;
    const rid = resource.id || resource.resource_id || '';
    const name = resource.name || resource.resource_name || 'Resource';
    const typeLabel = resourceLabelForRow(resource) || title || 'Resource';
    const rowIcon = iconForRow(resource, { apiPath, fallback: iconKey });
    return { rid, name, typeLabel, rowIcon };
  }, [resource, apiPath, iconKey, title]);

  const inventoryContext = useMemo(() => {
    if (!resource) return null;
    return {
      sku: toDisplayText(resource.sku) || null,
      resourceGroup: toDisplayText(resource.resourceGroup || resource.resource_group) || null,
      location: toDisplayText(resource.location) || null,
      state: toDisplayText(resource.state) || null,
      armType: toDisplayText(resource.type) || null,
      canonicalType: resource.type || null,
      liveMetricsShown: !suppressLiveMetrics,
    };
  }, [resource, suppressLiveMetrics]);

  const displayFindings = useMemo(
    () => (resource ? resolveResourceFindings(resource, findings, { indexReady }) : []),
    [resource, findings, indexReady],
  );

  const resourceRid = (resource?.id || resource?.resource_id || '').toLowerCase();
  const shouldLoadBundle = Boolean(resourceRid && subscription);
  const {
    data: drawerBundle,
    isLoading: drawerBundleLoading,
    isError: drawerBundleError,
    error: drawerBundleErrorDetail,
  } = useDrawerResourceBundle({
    subscriptionId: subscription,
    resourceId: resourceRid,
    timespan: metricsTimespan,
    enabled: shouldLoadBundle,
  });
  const bundleMetrics = drawerBundle?.metrics ?? null;
  const bundleAnalysis = drawerBundle?.advanced_analysis ?? null;

  const {
    byResourceId: advisorByResourceId,
    indexReady: advisorIndexReady,
    isLoading: advisorIndexLoading,
  } = useAdvisorIndex(subscription);
  const advisorRecommendations = useMemo(
    () => lookupAdvisorForResource(advisorByResourceId, resource),
    [advisorByResourceId, resource],
  );
  const subscriptionHasAdvisor = advisorByResourceId.size > 0;
  const triggerCount = countTriggerMetricsForFindings(displayFindings);

  const totalCost = resourceTotalCost(resource);
  const costTrend = resourceCostTrend(resource);
  const totalSavings = useMemo(
    () => displayFindings.reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0),
    [displayFindings],
  );

  const resourceState = toDisplayText(resource?.state || resource?._state);
  const displayTags = localTags ?? resource?.tags ?? {};
  const resourceGroup = toDisplayText(resource?.resourceGroup || resource?.resource_group);
  const resourceLocation = toDisplayText(resource?.location);

  if (!resource || !resolved) return null;

  const { rid, name, typeLabel, rowIcon } = resolved;

  const emptyMessage = isAdmin
    ? 'No open findings for this resource. Sync and analyze from Optimization center to generate recommendations.'
    : 'No open findings for this resource yet. Check Recommendations for subscription-wide opportunities.';

  const showMetricsSection = (rid && !suppressLiveMetrics) || (rid && suppressLiveMetrics && children);

  return (
    <div className="insight-drawer-overlay" onClick={onClose} role="presentation">
      <aside
        ref={drawerRef}
        className={`insight-drawer${drawerWidth >= 560 ? ' insight-drawer--expanded' : ''}`}
        style={{ width: `${drawerWidth}px`, maxWidth: '100vw' }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="insight-drawer-title"
      >
        <div
          className="insight-drawer__resize-handle"
          onMouseDown={onResizeStart}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panel"
          title="Drag to resize"
        />
        <header className="insight-drawer__header">
          <div className="insight-drawer__header-accent" aria-hidden />
          <div className="insight-drawer__header-inner">
            <div className="insight-drawer__header-main">
              <div className="insight-drawer__title-row">
                <div className="insight-drawer__title-icon">
                  <AssetIcon iconKey={rowIcon} size={20} />
                </div>
                <div className="insight-drawer__title-block">
                  <h2 id="insight-drawer-title" className="insight-drawer__title">{name}</h2>
                  <p className="insight-drawer__sub">{typeLabel}</p>
                  {(resourceGroup || resourceLocation) && (
                    <p className="insight-drawer__meta-line">
                      {[resourceGroup, resourceLocation].filter(Boolean).join(' · ')}
                    </p>
                  )}
                </div>
              </div>

              <div className="insight-drawer__kpi-strip">
                <div className="insight-drawer__kpi insight-drawer__kpi--cost">
                  <span className="insight-drawer__kpi-label">Total cost</span>
                  <span className="insight-drawer__kpi-value">
                    {totalCost > 0
                      ? formatCurrency(totalCost, { currency })
                      : '—'}
                  </span>
                  {totalCost > 0 && (
                    <span className="insight-drawer__kpi-trend">
                      <TrendBadge deltaAmount={costTrend} currency={currency} invert />
                    </span>
                  )}
                </div>
                {resourceState && (
                  <div className={`insight-drawer__kpi insight-drawer__kpi--${stateTone(resourceState)}`}>
                    <span className="insight-drawer__kpi-label">State</span>
                    <span className="insight-drawer__kpi-value">{resourceState}</span>
                  </div>
                )}
                <div className="insight-drawer__kpi insight-drawer__kpi--findings">
                  <span className="insight-drawer__kpi-label">Findings</span>
                  <span className="insight-drawer__kpi-value">{displayFindings.length}</span>
                </div>
                {subscriptionHasAdvisor && (
                  <div className="insight-drawer__kpi insight-drawer__kpi--advisor">
                    <span className="insight-drawer__kpi-label">Advisor</span>
                    <span className="insight-drawer__kpi-value">{advisorRecommendations.length}</span>
                  </div>
                )}
                {triggerCount > 0 && (
                  <div className="insight-drawer__kpi insight-drawer__kpi--signals">
                    <span className="insight-drawer__kpi-label">Cost signals</span>
                    <span className="insight-drawer__kpi-value">{triggerCount}</span>
                  </div>
                )}
                {totalSavings > 0 && (
                  <div className="insight-drawer__kpi insight-drawer__kpi--savings">
                    <span className="insight-drawer__kpi-label">Savings</span>
                    <span className="insight-drawer__kpi-value trend-indicator">
                      {formatCurrency(totalSavings, { currency, decimals: 0 })}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="insight-drawer__header-actions">
              <button
                ref={closeBtnRef}
                type="button"
                className="btn btn-ghost btn-icon-only"
                onClick={onClose}
                aria-label="Close"
              >
                <X size={17} />
              </button>
            </div>
          </div>
        </header>

        <div className="insight-drawer__body">
          <div className="insight-drawer__stack insight-drawer__stack--compact">
            <section className="insight-drawer__summary" id="drawer-overview">
              <ResourceDrawerOverview resource={resource} compact />
              {rid && <ResourceIdRow resourceId={rid} compact />}
            </section>

            {rid && subscription && (
              <DrawerCollapsibleSection
                title="Tags"
                storageKey="tags"
                defaultOpen={false}
                compact
              >
                <TagEditor
                  resourceId={rid}
                  subscriptionId={subscription}
                  tags={displayTags}
                  onUpdated={setLocalTags}
                />
              </DrawerCollapsibleSection>
            )}

            {resource._pools?.length > 0 && (
              <DrawerCollapsibleSection
                title="Node pools"
                icon={<Server size={13} />}
                badge={resource._pools.length}
                storageKey="node-pools"
                defaultOpen={resource._pools.length <= 4}
                compact
              >
                <div className="table-wrap insight-drawer__table-wrap">
                  <table className="insight-drawer__table">
                    <thead>
                      <tr>
                        <th>Pool</th>
                        <th>Mode</th>
                        <th>Count</th>
                        <th>VM size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {resource._pools.map((pp) => (
                        <tr key={pp.name}>
                          <td>{pp.name}</td>
                          <td>{pp.mode || '—'}</td>
                          <td>{pp.count ?? 0}</td>
                          <td className="insight-drawer__mono">{pp.vmSize || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </DrawerCollapsibleSection>
            )}

            {showMetricsSection && (
              <DrawerCollapsibleSection
                title="Metrics"
                icon={<Activity size={13} />}
                storageKey="metrics"
                defaultOpen
                compact
                onOpenChange={setMetricsSectionOpen}
              >
                {rid && suppressLiveMetrics && children && (
                  <div className="insight-drawer__metrics-block" id="drawer-vm-metrics">
                    {children}
                  </div>
                )}

                {rid && !suppressLiveMetrics && metricsSectionOpen && (
                  <div id="drawer-metrics">
                    <ResourceAzureMetrics
                      resourceId={rid}
                      enabled
                      sectionTitle="Azure Monitor metrics"
                      timespan={metricsTimespan}
                      onTimespanChange={onMetricsTimespanChange}
                      prefetchedData={bundleMetrics}
                      prefetchedLoading={drawerBundleLoading}
                      prefetchedError={drawerBundleError ? drawerBundleErrorDetail : null}
                    />
                  </div>
                )}
              </DrawerCollapsibleSection>
            )}

            <DrawerCollapsibleSection
              title="Findings"
              icon={<AlertTriangle size={13} />}
              badge={displayFindings.length || null}
              storageKey="findings"
              defaultOpen
              compact
            >
              <div
                className={displayFindings.length ? 'insight-drawer__findings-body insight-drawer__findings-body--active' : 'insight-drawer__findings-body'}
                id="drawer-findings"
              >
                <InsightFindingsPanel
                  findings={displayFindings}
                  emptyMessage={emptyMessage}
                  currency={currency}
                  resourceTypeLabel={typeLabel}
                  resourceId={rid}
                  inventoryContext={inventoryContext}
                  compact
                  showAllByDefault
                />
              </div>
            </DrawerCollapsibleSection>

            {rid && (
              <div className="insight-drawer__section-slot" id="drawer-advisor">
                <AdvisorResourceSection
                  recommendations={advisorRecommendations}
                  indexReady={advisorIndexReady}
                  isLoading={advisorIndexLoading}
                  currency={currency}
                  subscriptionHasAdvisor={subscriptionHasAdvisor}
                />
              </div>
            )}

            {rid && (
              <div className="insight-drawer__section-slot" id="drawer-advanced-analysis">
                <AdvancedResourceSection
                  resourceId={rid}
                  subscriptionId={subscription}
                  currency={currency}
                  prefetchedData={bundleAnalysis}
                  prefetchedLoading={drawerBundleLoading}
                  prefetchedError={drawerBundleError ? drawerBundleErrorDetail : null}
                />
              </div>
            )}

            {rid && (
              <DrawerCollapsibleSection
                title="Cost drivers"
                storageKey="cost-drivers"
                defaultOpen={displayFindings.length > 0 || countTriggerMetricsForFindings(displayFindings) > 0}
                compact
                onOpenChange={setCostDriversSectionOpen}
              >
                <div id="drawer-cost-signals">
                  <ResourceCostDrivingSignals
                    resourceId={rid}
                    enabled={costDriversSectionOpen}
                    metricsData={bundleMetrics}
                    metricsLoading={drawerBundleLoading}
                    timespan={metricsTimespan}
                    onTimespanChange={onMetricsTimespanChange}
                  />
                </div>
              </DrawerCollapsibleSection>
            )}
          </div>
        </div>

        <footer className="insight-drawer__footer">
          <Link to="/optimization-hub?tab=actions" className="btn btn-secondary btn-sm" onClick={onClose}>
            <ExternalLink size={13} /> View actions
          </Link>
        </footer>
      </aside>
    </div>
  );
}
