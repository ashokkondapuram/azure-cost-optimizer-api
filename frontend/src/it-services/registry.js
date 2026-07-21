/**
 * Platform registry — wires IT service UI modules into the shared drawer shell.
 *
 * Only services with drawer_ui: true in it-services/<id>/manifest.yaml belong here.
 * All 42 resources have folders — see it-services/catalog.json.
 */

import enabled from './registry.enabled.json';
import * as computeDiskUi from './compute-disk';
import * as containersAksUi from './containers-aks/drawer';

const MODULES_BY_ID = {
  'compute-disk': computeDiskUi,
  'containers-aks': containersAksUi,
};

const IT_SERVICE_UI = enabled.drawer_ui_services
  .map((id) => MODULES_BY_ID[id])
  .filter(Boolean);

export function resolveItServiceUi(resource, apiPath = '') {
  return IT_SERVICE_UI.find((mod) => mod.matchesResource?.(resource, apiPath)) ?? null;
}

export function enrichInventoryContext(base, resource, apiPath = '') {
  let next = { ...base };
  for (const mod of IT_SERVICE_UI) {
    if (mod.enrichInventoryContext) {
      next = mod.enrichInventoryContext(next, resource, apiPath);
    }
  }
  return next;
}

export function shouldSkipOverviewTiles(resource, apiPath = '') {
  return IT_SERVICE_UI.some((mod) => mod.skipOverviewTiles?.(resource, apiPath));
}

export function shouldCollapseMetricsSection(resource, apiPath = '') {
  return IT_SERVICE_UI.some((mod) => mod.collapseMetricsSection?.(resource, apiPath));
}

export function shouldHideStateKpi(resource, apiPath = '') {
  return IT_SERVICE_UI.some((mod) => mod.hideStateKpi?.(resource, apiPath));
}

export function resolveCostDriversDefaultOpen({
  resource,
  apiPath = '',
  findingsCount = 0,
  triggerCount = 0,
}) {
  for (const mod of IT_SERVICE_UI) {
    if (!mod.costDriversDefaultOpen) continue;
    const value = mod.costDriversDefaultOpen({
      resource,
      apiPath,
      findingsCount,
      triggerCount,
    });
    if (mod.matchesResource?.(resource, apiPath)) return value;
  }
  return findingsCount > 0 || triggerCount > 0;
}

export function enrichServiceEvidenceFilter(hideIds, inventoryContext) {
  for (const mod of IT_SERVICE_UI) {
    mod.enrichEvidenceFilter?.(hideIds, inventoryContext);
  }
}

export function resolvePropertiesPanel(resource, apiPath = '') {
  const mod = resolveItServiceUi(resource, apiPath);
  return mod?.PropertiesPanel ?? null;
}
