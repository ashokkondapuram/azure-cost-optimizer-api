import React, { useMemo } from 'react';
import DrawerEssentialsGroups from './DrawerEssentialsGroups';
import { buildCompleteDrawerEssentials } from '../utils/resourceDrawerUtils';
import { organizeEssentialsIntoGroups } from '../utils/drawerEssentialsGroups';
import {
  dedupeDrawerPropertyGroups,
  isAksAllowedProperty,
  organizeDrawerPropertyGroupsForDisplay,
} from '../utils/insightCanvasUtils';
import { resolveDrawerCanonicalType } from '../utils/drawerTrendMetrics';

const OVERVIEW_GROUP_IDS = new Set(['identity', 'status']);

export default function ResourceDrawerOverview({
  resource,
  apiPath = '',
  inventoryProperties = [],
  metricsData = null,
  groupFilter = null,
}) {
  const essentials = useMemo(
    () => buildCompleteDrawerEssentials(resource, inventoryProperties, { apiPath, metricsData }),
    [resource, inventoryProperties, apiPath, metricsData],
  );

  const groups = useMemo(() => {
    const organized = organizeEssentialsIntoGroups(essentials);
    if (!groupFilter) return organized;
    const allowed = new Set(groupFilter);
    return organized.filter((group) => allowed.has(group.id));
  }, [essentials, groupFilter]);

  if (!groups.length) {
    return <p className="insight-drawer__empty insight-drawer__empty--compact">No properties available for this resource yet.</p>;
  }

  return (
    <div className="insight-drawer__overview insight-drawer__overview--full">
      <DrawerEssentialsGroups groups={groups} />
    </div>
  );
}

export function useDrawerPropertyGroups({
  resource,
  apiPath = '',
  inventoryProperties = [],
  metricsData = null,
} = {}) {
  return useMemo(() => {
    if (!resource) return [];
    const canonicalType = resolveDrawerCanonicalType(resource, apiPath);
    const isAks = canonicalType === 'containers/aks';
    const essentials = buildCompleteDrawerEssentials(resource, inventoryProperties, { apiPath, metricsData });
    const organized = organizeEssentialsIntoGroups(essentials);
    const filtered = organized
      .filter((group) => !OVERVIEW_GROUP_IDS.has(group.id))
      .map((group) => ({
        ...group,
        rows: isAks
          ? group.rows.filter((row) => isAksAllowedProperty(row.label, row.fact_key || row.key))
          : group.rows,
      }))
      .filter((group) => group.rows.length > 0);
    return organizeDrawerPropertyGroupsForDisplay(dedupeDrawerPropertyGroups(filtered));
  }, [resource, inventoryProperties, apiPath, metricsData]);
}
