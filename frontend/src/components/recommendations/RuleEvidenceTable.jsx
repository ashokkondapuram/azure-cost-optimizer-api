import React from 'react';

/** Signal / value / threshold rows for one recommendation. */
export default function RuleEvidenceTable({ rows = [], factors = [], compact = false }) {
  if (!rows?.length && !factors?.length) {
    return (
      <p className="rec-evidence-empty">
        No supporting signals available for this recommendation.
      </p>
    );
  }

  return (
    <>
      {rows?.length > 0 && (
        <ul className={`rec-evidence-table${compact ? ' rec-evidence-table--compact' : ''}`}>
          {rows.map((row) => (
            <li
              key={`${row.label}-${row.value}`}
              className={`rec-evidence-table__row rec-evidence-table__row--${row.status || 'muted'}`}
            >
              <span className="rec-evidence-table__label">{row.label}</span>
              <span className="rec-evidence-table__value">{row.value}</span>
              {row.threshold ? (
                <span className="rec-evidence-table__threshold">
                  Threshold:
                  {' '}
                  {row.threshold}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {factors?.length > 0 && (
        <ul className="rec-evidence-factors">
          {factors.map((factor) => (
            <li key={factor}>{factor}</li>
          ))}
        </ul>
      )}
    </>
  );
}
