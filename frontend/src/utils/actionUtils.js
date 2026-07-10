/** Optimization action display helpers. */

import { isArmResourceId, shortArmResourceLabel } from './armResourceLinks';
import { armResourceTypeFromId } from './resourceAdvisorUtils';
import { resourceGroupLabelForAction } from './optimizationGrouping';

export const ACTION_INDEX_LIMIT = 500;
export const ACTION_PAGE_SIZE = 50;

function isPathLike(value) {
  const text = String(value || '').trim();
  return text.includes('/') || text.includes('\\');
}

function lastPathSegment(value) {
  const text = String(value || '').trim().replace(/\\/g, '/');
  if (!text) return '';
  const parts = text.split('/').filter(Boolean);
  return decodeURIComponent(parts[parts.length - 1] || '');
}

/** Readable resource title for actions table and drawers. */
export function actionResourceDisplayName(action) {
  const name = String(action?.resource_name || '').trim();
  const resourceId = String(action?.resource_id || '').trim();

  if (name && !isPathLike(name) && name.length <= 80) {
    return name;
  }

  if (isArmResourceId(resourceId)) {
    return shortArmResourceLabel(resourceId);
  }

  const fromId = lastPathSegment(resourceId);
  if (fromId) return fromId;

  if (name) return lastPathSegment(name) || name;

  return 'Unknown resource';
}

/** Compact resource type label (never a full ARM path). */
export function actionResourceTypeLabel(action) {
  const type = String(action?.resource_type || '').trim();
  if (type && !isPathLike(type) && type.length <= 64) {
    return type.replace(/\//g, ' · ');
  }

  const fromArm = armResourceTypeFromId(action?.resource_id);
  if (fromArm && fromArm !== 'Unknown') return fromArm;

  if (type && !isPathLike(type)) return type;

  return fromArm || '—';
}

/** Secondary line under the resource title (type + resource group). */
export function actionResourceMetaLine(action) {
  const typeLabel = actionResourceTypeLabel(action);
  const group = resourceGroupLabelForAction(action);
  if (group && group !== '—') return `${typeLabel} · ${group}`;
  return typeLabel;
}

const ACTION_LABELS = {
  resize_down: 'Resize down',
  keep: 'Keep',
  downgrade_disk: 'Downgrade disk',
  investigate: 'Investigate',
  buy_reservation: 'Buy reservation',
  manual_review: 'Manual review',
};

const WORKFLOW_LABELS = {
  proposed: 'Proposed',
  approved: 'Approved',
  executed: 'Executed',
  rejected: 'Rejected',
  deferred: 'Deferred',
};

const CONFIDENCE_TONES = {
  High: 'high',
  Medium: 'medium',
  Low: 'low',
  'Manual review': 'manual',
};

export function actionTypeLabel(actionType) {
  if (!actionType) return '—';
  return ACTION_LABELS[actionType] || String(actionType).replace(/_/g, ' ');
}

export function workflowStatusLabel(status) {
  if (!status) return 'Proposed';
  return WORKFLOW_LABELS[status] || status;
}

/** Normalize ARM resource IDs for distinct savings rollups. */
export function normalizeActionResourceId(actionOrId) {
  const value = typeof actionOrId === 'string'
    ? actionOrId
    : actionOrId?.resource_id;
  return String(value || '').trim().toLowerCase();
}

/**
 * Sum estimated savings once per resource (max when duplicates exist).
 */
export function sumDistinctActionSavings(
  actions,
  { field = 'estimated_monthly_savings', fallbackId = 'id' } = {},
) {
  const byResource = new Map();
  for (const action of actions || []) {
    const key = normalizeActionResourceId(action) || String(action?.[fallbackId] || '');
    if (!key) continue;
    const amount = Number(action?.[field]) || 0;
    byResource.set(key, Math.max(byResource.get(key) || 0, amount));
  }
  return [...byResource.values()].reduce((sum, value) => sum + value, 0);
}

export function countDistinctActionResources(actions, { fallbackId = 'id' } = {}) {
  const keys = new Set();
  for (const action of actions || []) {
    const key = normalizeActionResourceId(action) || String(action?.[fallbackId] || '');
    if (key) keys.add(key);
  }
  return keys.size;
}

export function confidenceTone(confidence) {
  return CONFIDENCE_TONES[confidence] || 'muted';
}

export function actionMonthlySavings(action) {
  return action?.estimated_monthly_savings ?? null;
}

export function uniqueActionTypes(items = []) {
  return [...new Set(items.map((a) => a.action_type).filter(Boolean))].sort();
}

export function uniqueResourceTypes(items = []) {
  return [...new Set(items.map((a) => a.resource_type).filter(Boolean))].sort();
}
