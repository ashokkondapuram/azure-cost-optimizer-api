import React, { useContext, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  X, ExternalLink,
} from 'lucide-react';
import { toDisplayText } from '../utils/formatDisplay';
import { resolveDrawerResourceFindings, resolveResourceSavings } from '../utils/resourceFindingsUtils';
import { formatCurrency } from '../utils/format';
import { resourceTotalCost, resourceCostTrend } from '../utils/costCurrency';
import TrendBadge from './visual/TrendBadge';
import AssetIcon from './AssetIcon';
import DrawerFindingsList from './DrawerFindingsList';
import DrawerEssentialsGroups from './DrawerEssentialsGroups';
import ResourceAzureMetrics from './ResourceAzureMetrics';
import ResourceCostDrivingSignals from './ResourceCostDrivingSignals';
import ResourceDrawerTrends from './ResourceDrawerTrends';
import ResourceDrawerCostSection from './ResourceDrawerCostSection';
import ResourceDrawerOverview, { useDrawerPropertyGroups } from './ResourceDrawerOverview';
import {
  enrichInventoryContext,
  resolvePropertiesPanel,
  shouldHideStateKpi,
} from '../it-services/registry';
import { enrichDrawerResource } from '../it-services/containers-aks';
import AksNodePoolsTable from '../it-services/containers-aks/components/AksNodePoolsTable';
import useResizableDrawerWidth from '../hooks/useResizableDrawerWidth';
import usePersistedMetricTimespan from '../hooks/usePersistedMetricTimespan';
import usePersistedDrawerNavCollapsed from '../hooks/usePersistedDrawerNavCollapsed';
import ResourceInsightDrawerNav, {
  focusSectionToTab,
} from './ResourceInsightDrawerNav';
import { useAuth } from '../context/AuthContext';
import { AppCtx } from '../App';
import TagEditor from './TagEditor';
import { iconForRow, resourceLabelForRow } from '../config/assetIcons';
import { actionCentreHubLink } from '../utils/armResourceLinks';
import useAdvisorIndex from '../hooks/useAdvisorIndex';
import useFindingsIndex from '../hooks/useFindingsIndex';
import useDrawerResourceBundle from '../hooks/useDrawerResourceBundle';
import useResourceAnalysisOnOpen from '../hooks/useResourceAnalysisOnOpen';
import useBodyScrollLock from '../hooks/useBodyScrollLock';
import ModalPortal from './ModalPortal';
import useOptimizationActions from '../hooks/useOptimizationActions';
import AdvisorResourceSection from './advisor/AdvisorResourceSection';
import AdvancedResourceSection from './optimization/AdvancedResourceSection';
import DrawerProposedActionItem from './DrawerProposedActionItem';
import { lookupAdvisorForResource } from '../utils/resourceAdvisorUtils';
import { syncTypesForApiPath } from '../utils/syncScope';
import {
  filterDrawerFindings,
  getDrawerCapabilities,
  resolveResourceDisplayName,
  buildDrawerSections,
  hasCostDriversContent,
  resolveCanonicalType,
} from '../utils/drawerCapabilities';
import { isCosmosResource } from '../utils/cosmosPrimaryFinding';
import { normalizeArmId } from '../utils/findingDedupe';
import { humanizeAzureRegion } from '../utils/format';
import { ACTION_INDEX_LIMIT } from '../utils/actionUtils';
import { getErrorMessage } from '../api/errors';

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

function sanitizeDrawerDomId(sectionId) {
  return String(sectionId || 'section').replace(/[^a-zA-Z0-9_-]/g, '-');
}

function DrawerFlowSection({ id, title, subtitle, badge, children, loading = false }) {
  const panelId = sanitizeDrawerDomId(id);
  return (
    <section
      id={`drawer-section-${panelId}`}
      className="insight-drawer__flow-section insight-drawer__flow-section-v2 zafin-prose"
      data-drawer-section={id}
      aria-labelledby={`drawer-flow-heading-${panelId}`}
    >
      <header className="insight-drawer__flow-section-head">
        <div className="insight-drawer__flow-heading">
          <h3 id={`drawer-flow-heading-${panelId}`} className="insight-drawer__flow-title">
            {title}
          </h3>
          {badge > 0 && (
            <span className="insight-drawer__flow-badge">
              {badge > 999 ? '999+' : badge}
            </span>
          )}
        </div>
        {subtitle && <p className="insight-drawer__flow-sub">{subtitle}</p>}
      </header>
      <div className="insight-drawer__flow-body">
        {loading ? <DrawerSectionSkeleton /> : children}
      </div>
    </section>
  );
}

function DrawerSectionSkeleton() {
  return (
    <div className="insight-drawer__skeleton" aria-hidden>
      <div className="insight-drawer__skeleton-line insight-drawer__skeleton-line--wide" />
      <div className="insight-drawer__skeleton-line" />
      <div className="insight-drawer__skeleton-line insight-drawer__skeleton-line--short" />
    </div>
  );
}

function DrawerEmpty({ children }) {
  return <p className="insight-drawer__empty">{children}</p>;
}

function DrawerLoadingState({ message = 'Loading resource details…' }) {
  return (
    <section
      className="insight-drawer__flow-section insight-drawer__flow-section-v2 insight-drawer__flow-section--loading"
      data-drawer-section="overview"
      aria-busy="true"
      aria-live="polite"
    >
      <header className="insight-drawer__flow-section-head">
        <h3 className="insight-drawer__flow-title">Overview</h3>
      </header>
      <div className="insight-drawer__flow-body">
        <DrawerSectionSkeleton />
        <p className="insight-drawer__empty">{message}</p>
      </div>
    </section>
  );
}

function DrawerOverviewKpiStrip({
  totalCost,
  costTrend,
  currency,
  resourceState,
  hideStateKpi,
  totalSavings,
}) {
  return (
    <div className="insight-drawer__kpi-strip insight-drawer__kpi-strip--overview">
      <div className="insight-drawer__kpi insight-drawer__kpi--cost">
        <span className="insight-drawer__kpi-label">Cost</span>
        <span className="insight-drawer__kpi-value">
          {totalCost > 0 ? formatCurrency(totalCost, { currency }) : '—'}
        </span>
        {totalCost > 0 && (
          <TrendBadge deltaAmount={costTrend} currency={currency} invert />
        )}
      </div>
      {resourceState && !hideStateKpi && (
        <div className={`insight-drawer__kpi insight-drawer__kpi--${stateTone(resourceState)}`}>
          <span className="insight-drawer__kpi-label">State</span>
          <span className="insight-drawer__kpi-value">{resourceState}</span>
        </div>
      )}
      {totalSavings > 0 && (
        <div className="insight-drawer__kpi insight-drawer__kpi--savings">
          <span className="insight-drawer__kpi-label">Savings</span>
          <span className="insight-drawer__kpi-value">
            {formatCurrency(totalSavings, { currency, decimals: 0 })}
          </span>
        </div>
      )}
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
  focusSection = null,
}) {
  const { isAdmin } = useAuth();
  const { subscription } = useContext(AppCtx);
  const location = useLocation();
  const embeddedInHub = location.pathname.startsWith('/action-centre');
  const { width: drawerWidth, onResizeStart } = useResizableDrawerWidth();
  const [metricsTimespan, onMetricsTimespanChange] = usePersistedMetricTimespan(
    'finops-drawer-metrics-timespan',
  );
  const [navCollapsed, toggleNavCollapsed] = usePersistedDrawerNavCollapsed();
  const [localTags, setLocalTags] = useState(null);
  const [activeSection, setActiveSection] = useState(() => focusSectionToTab(focusSection));
  const closeBtnRef = useRef(null);
  const flowBodyRef = useRef(null);
  const navScrollRef = useRef(null);
  const scrollSpyLockRef = useRef(false);

  const stopDrawerWheelBubble = useCallback((event) => {
    event.stopPropagation();
  }, []);

  const scrollToSection = useCallback((sectionId) => {
    setActiveSection(sectionId);
    scrollSpyLockRef.current = true;
    const scrollRoot = flowBodyRef.current;
    const panelId = sanitizeDrawerDomId(sectionId);
    const el = document.getElementById(`drawer-section-${panelId}`);
    if (scrollRoot && el) {
      const rootRect = scrollRoot.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      const targetTop = scrollRoot.scrollTop + (elRect.top - rootRect.top) - 10;
      scrollRoot.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
    }
    window.setTimeout(() => {
      scrollSpyLockRef.current = false;
    }, 700);
  }, []);

  useEffect(() => {
    setLocalTags(null);
    setActiveSection(focusSectionToTab(focusSection));
  }, [resource?.id, resource?.resource_id, focusSection]);

  useEffect(() => {
    closeBtnRef.current?.focus({ preventScroll: true });
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousFocus = document.activeElement;
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      if (previousFocus && typeof previousFocus.focus === 'function') {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, [onClose]);

  const resolved = useMemo(() => {
    if (!resource) return null;
    const rid = normalizeArmId(resource.id || resource.resource_id || '');
    const name = resolveResourceDisplayName(resource);
    const typeLabel = resourceLabelForRow(resource) || title || 'Resource';
    const rowIcon = iconForRow(resource, { apiPath, fallback: iconKey });
    return { rid, name, typeLabel, rowIcon };
  }, [resource, apiPath, iconKey, title]);

  const {
    byResourceId,
    savingsByResource,
    indexReady: findingsIndexReady,
  } = useFindingsIndex(subscription);

  const indexFindings = useMemo(
    () => (resolved?.rid ? byResourceId.get(resolved.rid) || [] : []),
    [byResourceId, resolved?.rid],
  );

  const displayFindings = useMemo(() => {
    const ready = findingsIndexReady || indexReady;
    const propFindings = Array.isArray(findings) ? findings : [];
    const source = ready && indexFindings.length
      ? indexFindings
      : (propFindings.length ? propFindings : indexFindings);
    const resolvedFindings = resource
      ? resolveDrawerResourceFindings(resource, source, { indexReady: ready })
      : [];
    return filterDrawerFindings(resolvedFindings, resource);
  }, [resource, findings, indexFindings, findingsIndexReady, indexReady]);

  const rid = resolved?.rid || '';
  const shouldLoadBundle = Boolean(rid && subscription);
  useResourceAnalysisOnOpen({
    subscriptionId: subscription,
    resourceId: rid,
    enabled: shouldLoadBundle,
  });
  const {
    data: drawerBundle,
    isLoading: drawerBundleLoading,
    isFetching: drawerBundleFetching,
    isError: drawerBundleError,
    error: drawerBundleErrorDetail,
  } = useDrawerResourceBundle({
    subscriptionId: subscription,
    resourceId: rid,
    timespan: metricsTimespan,
    enabled: shouldLoadBundle,
  });
  const bundleMetrics = drawerBundle?.metrics;
  const bundleAnalysis = drawerBundle?.advanced_analysis ?? null;
  const bundlePending = drawerBundleLoading || (drawerBundleFetching && !drawerBundle);
  const drawerBundleErrorMessage = drawerBundleError
    ? getErrorMessage(drawerBundleErrorDetail, 'Could not load metrics for this resource.')
    : null;

  const costEnrichedResource = useMemo(() => {
    const bundleCost = drawerBundle?.cost;
    if (!resource) return null;
    if (!bundleCost || typeof bundleCost !== 'object') return resource;
    return { ...resource, ...bundleCost };
  }, [resource, drawerBundle?.cost]);

  const mergedResource = useMemo(
    () => enrichDrawerResource(costEnrichedResource || resource, { apiPath, metricsData: bundleMetrics }),
    [costEnrichedResource, resource, apiPath, bundleMetrics],
  );

  const { items: optimizationActions } = useOptimizationActions(
    subscription,
    {},
    { limit: ACTION_INDEX_LIMIT, infinite: false },
  );
  const resourceActions = useMemo(
    () => optimizationActions.filter(
      (action) => normalizeArmId(action.resource_id) === rid,
    ),
    [optimizationActions, rid],
  );
  const proposedActions = useMemo(
    () => resourceActions.filter((a) => (a.workflow_status || 'proposed') === 'proposed'),
    [resourceActions],
  );

  const inventoryContext = useMemo(() => {
    const row = mergedResource || resource;
    if (!row) return null;
    const canonicalFromPath = syncTypesForApiPath(apiPath)[0] || null;
    const base = {
      sku: toDisplayText(row.sku) || null,
      resourceGroup: toDisplayText(row.resourceGroup || row.resource_group) || null,
      location: toDisplayText(row.location) || null,
      state: toDisplayText(row.state) || null,
      armType: toDisplayText(row.type) || null,
      canonicalType: canonicalFromPath || row.type || null,
      liveMetricsShown: !suppressLiveMetrics,
    };
    return enrichInventoryContext(base, row, apiPath);
  }, [mergedResource, resource, apiPath, suppressLiveMetrics]);

  const drawerResource = mergedResource || resource;

  const {
    byResourceId: advisorByResourceId,
    indexReady: advisorIndexReady,
    isLoading: advisorIndexLoading,
  } = useAdvisorIndex(subscription);
  const advisorRecommendations = useMemo(
    () => lookupAdvisorForResource(advisorByResourceId, drawerResource),
    [advisorByResourceId, drawerResource],
  );
  const subscriptionHasAdvisor = advisorByResourceId.size > 0;

  const totalCost = resourceTotalCost(costEnrichedResource || resource);
  const costTrend = resourceCostTrend(costEnrichedResource || resource);

  const resourceState = toDisplayText(drawerResource?.state || drawerResource?._state);
  const PropertiesPanel = resolvePropertiesPanel(drawerResource, apiPath);
  const propertyGroups = useDrawerPropertyGroups({
    resource: drawerResource,
    apiPath,
    inventoryProperties: bundleMetrics?.inventory_properties,
    metricsData: bundleMetrics,
  });
  const hasPropertiesSection = Boolean(PropertiesPanel || propertyGroups.length > 0);
  const hideStateKpi = shouldHideStateKpi(drawerResource, apiPath);
  const displayTags = useMemo(
    () => localTags ?? drawerResource?.tags ?? {},
    [localTags, drawerResource?.tags],
  );
  const resourceGroup = toDisplayText(drawerResource?.resourceGroup || drawerResource?.resource_group);
  const resourceLocation = drawerResource?.location
    ? humanizeAzureRegion(drawerResource.location)
    : '';
  const headerMetaChips = useMemo(() => {
    const chips = [];
    if (subscription) {
      chips.push({ key: 'subscription', label: 'Subscription', value: subscription });
    }
    if (resourceGroup && resourceGroup !== '—') {
      chips.push({ key: 'resource-group', label: 'Resource group', value: resourceGroup });
    }
    if (resourceLocation && resourceLocation !== '—') {
      chips.push({ key: 'location', label: 'Location', value: resourceLocation });
    }
    return chips;
  }, [subscription, resourceGroup, resourceLocation]);

  const emptyMessage = isAdmin
    ? 'No open findings for this resource. Sync and analyze from Sync center to generate findings.'
    : 'No open findings for this resource yet. Check Action centre for subscription-wide opportunities.';

  const totalSavings = useMemo(
    () => resolveResourceSavings(
      drawerResource,
      displayFindings,
      savingsByResource.get(rid) || 0,
      { indexReady: findingsIndexReady || indexReady, savingsByResource },
    ),
    [drawerResource, displayFindings, savingsByResource, rid, findingsIndexReady, indexReady],
  );
  const hasNodePools = drawerResource?._pools?.length > 0;
  const hasAnalysisInsights = useMemo(() => {
    const ins = bundleAnalysis?.insights;
    const trends = bundleAnalysis?.trends;
    return Boolean(
      ins?.headline
      || ins?.workload?.length
      || ins?.dependencies?.length
      || ins?.cost?.length
      || trends?.cpu_trend
      || trends?.memory_trend
      || trends?.cost_vs_prev_month_pct != null,
    );
  }, [bundleAnalysis]);

  const capabilities = useMemo(
    () => getDrawerCapabilities(drawerResource, {
      apiPath,
      rid,
      subscription,
      hasNodePools,
      advisorCount: advisorRecommendations.length,
    }),
    [
      drawerResource, apiPath, rid, subscription, hasNodePools,
      advisorRecommendations.length,
    ],
  );

  const hasCostSection = useMemo(() => {
    if (capabilities.billing) return false;
    return totalCost > 0;
  }, [capabilities.billing, totalCost]);

  const canonicalType = useMemo(
    () => resolveCanonicalType(drawerResource, apiPath),
    [drawerResource, apiPath],
  );

  const drawerSections = useMemo(
    () => buildDrawerSections({
      resolved,
      capabilities,
      displayFindings,
      displayTags,
      drawerResource,
      bundleMetrics,
      bundleAnalysis,
      bundlePending,
      hasAnalysisInsights,
      hasCostSection,
      hasPropertiesSection,
      advisorRecommendations,
      proposedActions,
      totalCost,
      apiPath,
    }),
    [
      resolved, capabilities, displayTags, drawerResource,
      displayFindings, advisorRecommendations,
      proposedActions, hasAnalysisInsights, bundlePending, hasCostSection,
      hasPropertiesSection, bundleMetrics, bundleAnalysis, totalCost, apiPath,
    ],
  );

  const drawerVisible = Boolean(resource && resolved);
  useBodyScrollLock(drawerVisible);

  useEffect(() => {
    const target = focusSectionToTab(focusSection);
    if (!target) return;
    scrollToSection(target);
  }, [resource?.id, resource?.resource_id, focusSection, scrollToSection]);

  useEffect(() => {
    if (!drawerSections.some((section) => section.id === activeSection)) {
      setActiveSection(drawerSections[0]?.id || 'overview');
    }
  }, [drawerSections, activeSection]);

  const flowPanelContent = useMemo(() => {
    if (!resolved) return null;

    function sectionPanel(sectionId) {
      if (sectionId === 'overview') {
        return (
          <DrawerFlowSection id="overview" title="Overview" subtitle="Key properties">
            {capabilities.overviewNote && (
              <p className="insight-drawer__context-note">{capabilities.overviewNote}</p>
            )}
            <DrawerOverviewKpiStrip
              totalCost={totalCost}
              costTrend={costTrend}
              currency={currency}
              resourceState={resourceState}
              hideStateKpi={hideStateKpi}
              totalSavings={totalSavings}
            />
            <ResourceDrawerOverview
              resource={drawerResource}
              apiPath={apiPath}
              inventoryProperties={bundleMetrics?.inventory_properties}
              metricsData={bundleMetrics}
              groupFilter={['identity', 'status']}
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'actions' && proposedActions.length > 0) {
        return (
          <DrawerFlowSection
            id="actions"
            title="Proposed actions"
            subtitle={`${proposedActions.length} ready to act`}
            badge={proposedActions.length}
          >
            <ul className="insight-drawer__action-list insight-drawer__action-list--cards">
              {proposedActions.map((action) => (
                <li key={action.id}>
                  <DrawerProposedActionItem
                    action={action}
                    findings={displayFindings}
                    currency={currency}
                    subscriptionId={subscription}
                    isAdmin={isAdmin}
                    onNavigate={onClose}
                    embeddedInHub={embeddedInHub}
                  />
                </li>
              ))}
            </ul>
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'findings' && (displayFindings.length > 0 || capabilities.billing)) {
        return (
          <DrawerFlowSection
            id="findings"
            title={capabilities.billing ? 'Spend' : 'Findings'}
            subtitle={capabilities.billing ? 'Billing commitment' : `${displayFindings.length} open findings`}
            badge={displayFindings.length}
          >
            {displayFindings.length > 0 ? (
              <DrawerFindingsList
                findings={displayFindings}
                emptyMessage={emptyMessage}
                currency={currency}
                resourceTypeLabel={resolved.typeLabel}
                resourceId={rid}
                inventoryContext={inventoryContext}
                resourceRow={drawerResource}
                monthlyResourceCost={resourceTotalCost(resource, currency)}
                subscriptionId={subscription}
                markPrimary={isCosmosResource(drawerResource, apiPath)}
              />
            ) : (
              <DrawerEmpty>
                {totalCost > 0
                  ? `${formatCurrency(totalCost, { currency })} recorded for this billing commitment. Review utilization in Savings planner — rightsizing does not apply here.`
                  : 'No spend recorded for this billing commitment in the current period.'}
              </DrawerEmpty>
            )}
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'properties' && hasPropertiesSection) {
        return (
          <DrawerFlowSection
            id="properties"
            title="Properties"
            subtitle="Configuration and technical details"
          >
            {PropertiesPanel && (
              <PropertiesPanel
                resource={drawerResource}
                metricsData={bundleMetrics}
                metricsLoading={bundlePending}
                metricsError={drawerBundleError ? drawerBundleErrorDetail : null}
                timespan={metricsTimespan}
                onTimespanChange={onMetricsTimespanChange}
              />
            )}
            {propertyGroups.length > 0 && (
              <DrawerEssentialsGroups groups={propertyGroups} />
            )}
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'metrics' && capabilities.showMetrics) {
        return (
          <DrawerFlowSection
            id="metrics"
            title="Metrics"
            subtitle="Azure Monitor utilization"
            loading={bundlePending && !bundleMetrics && !suppressLiveMetrics}
          >
            {rid && suppressLiveMetrics && children && (
              <div className="insight-drawer__metrics-block" id="drawer-vm-metrics">
                {children}
              </div>
            )}
            {rid && !suppressLiveMetrics && (
              <ResourceAzureMetrics
                resourceId={rid}
                enabled
                embedded
                sectionTitle=""
                timespan={metricsTimespan}
                onTimespanChange={onMetricsTimespanChange}
                prefetchedData={bundleMetrics}
                prefetchedLoading={bundlePending}
                prefetchedError={drawerBundleError ? drawerBundleErrorDetail : null}
                hideInventoryProperties
              />
            )}
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'cost-drivers' && hasCostDriversContent(bundleMetrics)) {
        return (
          <DrawerFlowSection
            id="cost-drivers"
            title="Cost drivers"
            subtitle="Meters and signals driving spend"
            loading={bundlePending && !bundleMetrics}
          >
            {rid && (
              <ResourceCostDrivingSignals
                resourceId={rid}
                enabled
                metricsData={bundleMetrics}
                metricsLoading={bundlePending}
                timespan={metricsTimespan}
                onTimespanChange={onMetricsTimespanChange}
                bare
              />
            )}
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'trends') {
        return (
          <DrawerFlowSection
            id="trends"
            title="Trends"
            subtitle="Utilization trends over time"
            loading={bundlePending && !bundleMetrics && !bundleAnalysis}
          >
            <ResourceDrawerTrends
              resource={drawerResource}
              resourceId={rid}
              subscriptionId={subscription}
              apiPath={apiPath}
              canonicalType={canonicalType}
              metricsData={bundleMetrics}
              analysisData={bundleAnalysis}
              findings={displayFindings}
              timespan={metricsTimespan}
              onTimespanChange={onMetricsTimespanChange}
              loading={bundlePending}
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'cost' && hasCostSection) {
        return (
          <DrawerFlowSection
            id="cost"
            title="Cost"
            subtitle="Spend trend"
            loading={bundlePending && !bundleMetrics}
          >
            <ResourceDrawerCostSection
              resource={drawerResource}
              resourceId={rid}
              subscriptionId={subscription}
              currency={currency}
              totalCost={totalCost}
              analysisData={bundleAnalysis}
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'analysis' && capabilities.showAnalysis && hasAnalysisInsights) {
        return (
          <DrawerFlowSection
            id="analysis"
            title="Insights"
            subtitle="Workload, cost, and dependency signals"
            loading={bundlePending && !bundleAnalysis}
          >
            <AdvancedResourceSection
              resourceId={rid}
              subscriptionId={subscription}
              currency={currency}
              prefetchedData={bundleAnalysis}
              prefetchedLoading={bundlePending}
              prefetchedError={drawerBundleError ? drawerBundleErrorDetail : null}
              bare
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'advisor' && capabilities.showAdvisor) {
        return (
          <DrawerFlowSection
            id="advisor"
            title="Advisor"
            subtitle={`${advisorRecommendations.length} Advisor findings`}
            badge={advisorRecommendations.length}
          >
            <AdvisorResourceSection
              recommendations={advisorRecommendations}
              indexReady={advisorIndexReady}
              isLoading={advisorIndexLoading}
              currency={currency}
              subscriptionHasAdvisor={subscriptionHasAdvisor}
              bare
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'tags' && capabilities.showTags) {
        return (
          <DrawerFlowSection id="tags" title="Tags" subtitle="Resource tags" badge={Object.keys(displayTags).length}>
            <TagEditor
              resourceId={rid}
              subscriptionId={subscription}
              tags={displayTags}
              onUpdated={setLocalTags}
            />
          </DrawerFlowSection>
        );
      }

      if (sectionId === 'pools' && capabilities.showPools) {
        return (
          <DrawerFlowSection
            id="pools"
            title="Node pools"
            subtitle={`${drawerResource._pools.length} node pools`}
            badge={drawerResource._pools.length}
          >
            {capabilities.poolsNote && (
              <p className="insight-drawer__context-note">{capabilities.poolsNote}</p>
            )}
            <AksNodePoolsTable
              pools={drawerResource._pools}
              resourceId={rid}
              subscriptionId={subscription}
              timespan={metricsTimespan}
            />
          </DrawerFlowSection>
        );
      }

      return null;
    }

    return drawerSections
      .map((section) => {
        const panel = sectionPanel(section.id);
        return panel ? <React.Fragment key={section.id}>{panel}</React.Fragment> : null;
      })
      .filter(Boolean);
  }, [
    resolved, drawerSections, capabilities, PropertiesPanel, drawerResource,
    bundleMetrics, bundlePending, drawerBundleError, drawerBundleErrorDetail, metricsTimespan,
    onMetricsTimespanChange, apiPath, rid, proposedActions, currency, displayFindings,
    emptyMessage, inventoryContext, resource, totalCost,
    suppressLiveMetrics, children, bundleAnalysis, subscription, advisorRecommendations,
    advisorIndexReady, advisorIndexLoading, subscriptionHasAdvisor, displayTags,
    hasAnalysisInsights, hasCostSection, embeddedInHub, costTrend, resourceState, hideStateKpi, totalSavings,
    canonicalType, isAdmin, onClose, propertyGroups, hasPropertiesSection,
  ]);

  useEffect(() => {
    const root = flowBodyRef.current;
    if (!root) return undefined;

    const sectionNodes = root.querySelectorAll('[data-drawer-section]');
    if (!sectionNodes.length) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (scrollSpyLockRef.current) return;
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const topId = visible[0]?.target?.getAttribute('data-drawer-section');
        if (topId) {
          setActiveSection((current) => (current === topId ? current : topId));
        }
      },
      {
        root,
        rootMargin: '-8% 0px -62% 0px',
        threshold: [0, 0.15, 0.35, 0.6],
      },
    );

    sectionNodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [flowPanelContent, drawerSections, resource?.id, resource?.resource_id]);

  useEffect(() => {
    const navRoot = navScrollRef.current;
    if (!navRoot) return;
    const panelId = sanitizeDrawerDomId(activeSection);
    const btn = navRoot.querySelector(`#drawer-tab-${panelId}`);
    if (!btn) return;
    const navRect = navRoot.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    if (btnRect.top < navRect.top + 4) {
      navRoot.scrollTop += btnRect.top - navRect.top - 4;
    } else if (btnRect.bottom > navRect.bottom - 4) {
      navRoot.scrollTop += btnRect.bottom - navRect.bottom + 4;
    }
  }, [activeSection, drawerSections]);

  if (!drawerVisible) return null;

  const { name, typeLabel, rowIcon } = resolved;
  const resourceHubLink = !embeddedInHub && rid
    ? actionCentreHubLink(rid, { sectionId: activeSection })
    : null;
  const hasFlowContent = Array.isArray(flowPanelContent) && flowPanelContent.length > 0;
  const flowBody = hasFlowContent
    ? flowPanelContent
    : <DrawerLoadingState />;

  return (
    <ModalPortal>
    <div className="insight-drawer-overlay" onClick={onClose} role="presentation">
      <aside
        className={[
          'insight-drawer',
          'insight-drawer--spa',
          'insight-drawer--v2',
          navCollapsed ? 'insight-drawer--collapsed-nav' : 'insight-drawer--expanded-nav',
          drawerWidth >= 520 ? 'insight-drawer--expanded' : '',
        ].filter(Boolean).join(' ')}
        style={{ width: `${drawerWidth}px`, maxWidth: '100vw' }}
        onClick={(e) => e.stopPropagation()}
        onWheel={stopDrawerWheelBubble}
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
        <header className="insight-drawer__header insight-drawer__header--compact">
          <div className="insight-drawer__header-accent" aria-hidden />
          <div className="insight-drawer__header-inner">
            <div className="insight-drawer__header-main">
              <div className="insight-drawer__title-row">
                <div className="insight-drawer__title-icon">
                  <AssetIcon iconKey={rowIcon} size={18} />
                </div>
                <div className="insight-drawer__title-block">
                  <h2 id="insight-drawer-title" className="insight-drawer__title">
                    {resourceHubLink ? (
                      <Link
                        to={resourceHubLink}
                        className="insight-drawer__title-link"
                        onClick={onClose}
                      >
                        {name}
                      </Link>
                    ) : name}
                  </h2>
                  <p className="insight-drawer__sub">{typeLabel}</p>
                  {headerMetaChips.length > 0 && (
                    <ul className="insight-drawer__meta-chips" aria-label="Resource context">
                      {headerMetaChips.map((chip) => (
                        <li key={chip.key} className="insight-drawer__meta-chip">
                          <span className="insight-drawer__meta-chip-label">{chip.label}</span>
                          <span className="insight-drawer__meta-chip-value" title={chip.value}>
                            {chip.value}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
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

        {drawerBundleErrorMessage && (
          <p className="alert alert--warning insight-drawer__bundle-error" role="status">
            {drawerBundleErrorMessage}
          </p>
        )}

        <div className="insight-drawer__shell insight-drawer__shell--flow">
          <ResourceInsightDrawerNav
            ref={navScrollRef}
            sections={drawerSections}
            activeSection={activeSection}
            onNavigate={scrollToSection}
            expanded={!navCollapsed}
            collapsed={navCollapsed}
            onToggleCollapse={toggleNavCollapsed}
          />

          <div
            ref={flowBodyRef}
            className="insight-drawer__body insight-drawer__body--flow insight-drawer__body--flow-v2"
          >
            {flowBody}
          </div>
        </div>

        {!embeddedInHub && (
          <footer className="insight-drawer__footer">
            <Link
              to={rid ? (actionCentreHubLink(rid, { sectionId: activeSection }) || "/action-centre") : "/action-centre"}
              className="btn btn-secondary btn-sm"
              onClick={onClose}
            >
              <ExternalLink size={13} /> Open in hub
            </Link>
          </footer>
        )}
      </aside>
    </div>
    </ModalPortal>
  );
}
