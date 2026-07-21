import { useMemo } from 'react';
import { normalizeArmId } from '../utils/findingDedupe';
import { pickPrimaryCosmosFinding } from '../utils/cosmosPrimaryFinding';
import { sortFindingsByPriority } from '../utils/taxonomy';
import { isActionCentreFinding } from '../utils/findingFilters';

function isCosmosFindingList(findings) {
  return findings.length > 0 && findings.every((f) => {
    const rule = String(f.rule_id || '');
    return rule.startsWith('COSMOS_') || rule.startsWith('cosmos_');
  });
}

/** Build resource_id → { findings, savings, topFinding, action } from indexes. */
export default function useResourceRecommendationsIndex({
  byResourceId,
  savingsByResource,
  actions = [],
  indexReady = false,
}) {
  return useMemo(() => {
    const actionsByResource = new Map();
    for (const action of actions) {
      const key = normalizeArmId(action.resource_id);
      if (!key) continue;
      if (!actionsByResource.has(key)) actionsByResource.set(key, []);
      actionsByResource.get(key).push(action);
    }

    const proposedResourceIds = new Set();
    for (const [key, resourceActions] of actionsByResource.entries()) {
      const hasProposed = resourceActions.some(
        (a) => (a.workflow_status || 'proposed') === 'proposed',
      );
      if (hasProposed) proposedResourceIds.add(key);
    }

    const enrich = (resourceId) => {
      const key = normalizeArmId(resourceId);
      let findings = sortFindingsByPriority(byResourceId.get(key) || [])
        .filter(isActionCentreFinding);
      if (isCosmosFindingList(findings)) {
        const primary = pickPrimaryCosmosFinding(findings);
        findings = primary ? [primary] : [];
      }
      const resourceActions = actionsByResource.get(key) || [];
      const proposed = resourceActions.filter((a) => (a.workflow_status || 'proposed') === 'proposed');
      const topAction = resourceActions.sort(
        (a, b) => (b.estimated_monthly_savings || 0) - (a.estimated_monthly_savings || 0),
      )[0];

      return {
        findings,
        findingCount: findings.length,
        savings: savingsByResource.get(key) || 0,
        topFinding: findings[0] || null,
        actions: resourceActions,
        proposedActions: proposed,
        topAction: topAction || null,
        hasRecommendations: findings.length > 0 || proposed.length > 0,
      };
    };

    return {
      enrich,
      indexReady,
      actionsByResource,
      proposedResourceIds,
      hasProposedAction: (rid) => proposedResourceIds.has(normalizeArmId(rid)),
    };
  }, [byResourceId, savingsByResource, actions, indexReady]);
}
