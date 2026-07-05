import React from 'react';
import ResourceFindingsSummaryBar from './ResourceFindingsSummaryBar';

export default function ResourceInventoryShell({
  children,
  showFindingsSummary = false,
  summaryRows = [],
  byResourceId,
  savingsByResource,
  currency = 'CAD',
  isAdmin = false,
  getResourceId,
  emptyAdminMessage,
  emptyUserMessage,
  truncated = false,
  findingsLimit = 2000,
  indexReady = false,
}) {
  return (
    <>
      {showFindingsSummary && summaryRows.length > 0 && (
        <ResourceFindingsSummaryBar
          rows={summaryRows}
          byResourceId={byResourceId}
          savingsByResource={savingsByResource}
          currency={currency}
          isAdmin={isAdmin}
          getResourceId={getResourceId}
          emptyAdminMessage={emptyAdminMessage}
          emptyUserMessage={emptyUserMessage}
          truncated={truncated}
          findingsLimit={findingsLimit}
          indexReady={indexReady}
        />
      )}
      {children}
    </>
  );
}
