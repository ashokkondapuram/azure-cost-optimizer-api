import React from 'react';
import RuleEvidenceTable from './recommendations/RuleEvidenceTable';
import { buildRecommendationEvidenceRows } from '../utils/recommendationEvidence';

/** Structured evidence rows for the insight drawer — signal, value, threshold only. */
export default function DrawerFindingEvidence({ finding, row = null, metrics = null }) {
  const evidenceRows = buildRecommendationEvidenceRows(finding, { row, metrics });
  const factors = Array.isArray(finding?.evidence?.evidence_factors)
    ? finding.evidence.evidence_factors
    : [];

  if (!evidenceRows.length && !factors.length) return null;

  return (
    <div className="drawer-evidence">
      <RuleEvidenceTable rows={evidenceRows} factors={factors} compact />
    </div>
  );
}
