/** App Service row enrichment — plans have ARM sku; web apps inherit plan tier from properties. */

import { toDisplayText } from './formatDisplay';

function appServiceKindLabel(kind) {
  const text = String(kind || '').toLowerCase();
  if (text.includes('functionapp')) return 'Function';
  if (text.includes('workflowapp')) return 'Logic App';
  if (text.includes('static')) return 'Static';
  if (text.includes('linux')) return 'Linux';
  if (text.includes('app')) return 'Web';
  return '';
}

export function formatAppServicePlanSku(row) {
  const top = row?.sku;
  if (top != null && top !== '') {
    return typeof top === 'object' ? (top.name || top.tier || '') : String(top);
  }
  const details = row?.skuDetails || {};
  const name = details.name || details.size || details.tier;
  const tier = details.tier;
  const capacity = details.capacity;
  if (!name && !tier) return '';
  const parts = [];
  if (name) parts.push(String(name));
  if (tier && String(tier) !== String(name)) parts.push(String(tier));
  if (capacity != null && capacity !== '') {
    const n = Number(capacity);
    if (!Number.isNaN(n)) parts.push(`${n} worker${n === 1 ? '' : 's'}`);
  }
  return parts.join(' · ');
}

export function formatAppServiceWebappSku(row) {
  const top = row?.sku;
  if (top != null && top !== '') {
    return typeof top === 'object' ? (top.name || top.tier || '') : String(top);
  }
  const props = row?.properties || {};
  const details = row?.skuDetails || {};
  const planSku = details.plan_sku || details.planSku;
  const planId = props.serverFarmId || details.app_service_plan_id || details.appServicePlanId;
  const planName = details.plan_name || details.planName || (planId ? String(planId).split('/').pop() : '');
  let planPart = '';
  if (planSku && planName) planPart = `${planSku} · ${planName}`;
  else planPart = planSku || planName || '';
  const kindLabel = appServiceKindLabel(props.kind || details.kind);
  if (kindLabel && planPart) return `${kindLabel} · ${planPart}`;
  return kindLabel || planPart || '';
}

export function enrichAppServicePlanRow(row) {
  const sku = formatAppServicePlanSku(row);
  return { ...row, sku: sku || row.sku || '' };
}

export function enrichAppServiceWebappRow(row) {
  const sku = formatAppServiceWebappSku(row);
  return { ...row, sku: sku || row.sku || '' };
}

export function appServicePlanDisplaySku(row) {
  return toDisplayText(formatAppServicePlanSku(enrichAppServicePlanRow(row)));
}

export function appServiceWebappDisplaySku(row) {
  return toDisplayText(formatAppServiceWebappSku(enrichAppServiceWebappRow(row)));
}
