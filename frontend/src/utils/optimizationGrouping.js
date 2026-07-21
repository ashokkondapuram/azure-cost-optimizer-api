/** Shared grouping helpers for optimization hub views. */

import { countDistinctActionResources, normalizeActionResourceId } from './actionUtils';
import { armResourceTypeFromId } from './resourceAdvisorUtils';
import { sumUnifiedSavingsForFindings } from './unifiedSavings';
import { normalizeArmId } from './findingDedupe';

export function resourceGroupFromArmId(resourceId) {
  const rid = String(resourceId || '').trim().toLowerCase();
  const match = rid.match(/\/resourcegroups\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export function resourceTypeLabelForFinding(finding) {
  const canonical = (finding?.resource_type || '').trim();
  if (canonical) {
    return canonical.replace(/\//g, ' · ');
  }
  const fromArm = armResourceTypeFromId(finding?.resource_id);
  if (fromArm && fromArm !== 'Unknown') return fromArm;
  return 'Unknown type';
}

export function resourceGroupLabelForFinding(finding) {
  return (
    finding?.resource_group
    || resourceGroupFromArmId(finding?.resource_id)
    || '—'
  );
}

export function resourceGroupLabelForAction(action) {
  return (
    action?.resource_group
    || resourceGroupFromArmId(action?.resource_id)
    || '—'
  );
}

export function groupByKey(items, keyFn, { savingsField, unifiedEngineSavings = false } = {}) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item) || '—';
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: key,
        items: [],
        savings: 0,
        resourceCount: 0,
        _savingsByResource: new Map(),
      });
    }
    const group = map.get(key);
    group.items.push(item);
    if (savingsField) {
      const resourceKey = normalizeActionResourceId(item) || String(item.id || '');
      if (resourceKey) {
        const amount = Number(item[savingsField]) || 0;
        group._savingsByResource.set(
          resourceKey,
          Math.max(group._savingsByResource.get(resourceKey) || 0, amount),
        );
      }
    }
  }
  const groups = [...map.values()].map((group) => {
    if (unifiedEngineSavings && savingsField) {
      group.savings = sumUnifiedSavingsForFindings(group.items);
      const resources = new Set();
      for (const item of group.items) {
        const key = normalizeArmId(item.resource_id);
        if (key) resources.add(key);
      }
      group.resourceCount = resources.size;
      delete group._savingsByResource;
    } else if (group._savingsByResource) {
      group.savings = [...group._savingsByResource.values()].reduce((sum, value) => sum + value, 0);
      group.resourceCount = group._savingsByResource.size;
      delete group._savingsByResource;
    } else {
      group.resourceCount = countDistinctActionResources(group.items);
    }
    return group;
  });
  groups.sort((a, b) => {
    if (b.savings !== a.savings) return b.savings - a.savings;
    return b.items.length - a.items.length || a.label.localeCompare(b.label);
  });
  return groups;
}

export function groupFindingsByResourceType(findings) {
  return groupByKey(findings, resourceTypeLabelForFinding, {
    savingsField: 'estimated_savings_usd',
    unifiedEngineSavings: true,
  });
}

export function groupFindingsByResourceGroup(findings) {
  return groupByKey(findings, resourceGroupLabelForFinding, {
    savingsField: 'estimated_savings_usd',
    unifiedEngineSavings: true,
  });
}

export function groupAdvisorByResourceType(items) {
  return groupByKey(items, (item) => armResourceTypeFromId(item.resource_id), {
    savingsField: 'potential_savings_monthly',
  });
}

export function groupAdvisorByResourceGroup(items) {
  return groupByKey(items, (item) => resourceGroupFromArmId(item.resource_id) || '—', {
    savingsField: 'potential_savings_monthly',
  });
}

export function groupActionsByResourceType(actions) {
  return groupByKey(actions, (action) => action.resource_type || '—', {
    savingsField: 'estimated_monthly_savings',
  });
}

export function groupActionsByResourceGroup(actions) {
  return groupByKey(actions, resourceGroupLabelForAction, {
    savingsField: 'estimated_monthly_savings',
  });
}

export const OPTIMIZATION_GROUP_BY = [
  { id: 'resource_type', label: 'Resource type' },
  { id: 'resource_group', label: 'Resource group' },
  { id: 'resource', label: 'Resource' },
  { id: 'flat', label: 'Flat list' },
];
