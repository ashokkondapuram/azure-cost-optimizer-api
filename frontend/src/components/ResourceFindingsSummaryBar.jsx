import React from 'react';
import { formatCurrency } from '../utils/format';
import {
  countOpenFindings,
  countResourcesWithFindings,
  sumResolvedSavingsForRows,
} from '../utils/resourceFindingsUtils';

export default function ResourceFindingsSummaryBar({
  rows,
  byResourceId,
  savingsByResource,
  currency = 'CAD',
  isAdmin = false,
  getResourceId,
  emptyAdminMessage = 'No open findings — sync and analyze in Sync center',
  emptyUserMessage = 'No open findings for this resource type',
  truncated = false,
  findingsLimit = 2000,
  indexReady = false,
}) {
  const options = { indexReady };
  const resourcesWithFindings = countResourcesWithFindings(rows, byResourceId, getResourceId, options);
  const openFindings = countOpenFindings(rows, byResourceId, getResourceId, options);
  const totalSavings = sumResolvedSavingsForRows(rows, byResourceId, savingsByResource, getResourceId, options);

  if (!rows.length) return null;

  return (
    <div className="resource-summary-bar">
      <span>
        {resourcesWithFindings > 0
          ? `${resourcesWithFindings} resource${resourcesWithFindings !== 1 ? 's' : ''} with ${openFindings} open finding${openFindings !== 1 ? 's' : ''}`
          : (isAdmin ? emptyAdminMessage : emptyUserMessage)}
        {truncated && resourcesWithFindings > 0 && (
          <span className="resource-summary-bar__note">
            {' '}· Showing first {findingsLimit.toLocaleString()} indexed findings
          </span>
        )}
      </span>
      {totalSavings > 0 && (
        <span className="resource-summary-bar__savings">
          Est. savings: {formatCurrency(totalSavings, { currency, decimals: 0 })}/mo
        </span>
      )}
    </div>
  );
}
