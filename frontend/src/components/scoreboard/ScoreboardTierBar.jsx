import React from 'react';
import { tierLabel, tierTone, tierSummaryEntries } from '../../utils/scoreboardUtils';

export default function ScoreboardTierBar({
  tierSummary = {},
  activeTier = '',
  onTierChange,
  total = 0,
}) {
  const entries = tierSummaryEntries(tierSummary);

  if (!entries.length && !total) return null;

  return (
    <section className="scoreboard-tier-bar" aria-label="Filter by recommendation tier">
      <div className="scoreboard-tier-bar__head">
        <h2 className="scoreboard-tier-bar__title">Recommendation tiers</h2>
        <p className="scoreboard-tier-bar__hint">Select a tier to focus the list</p>
      </div>
      <div className="scoreboard-tier-bar__chips" role="group" aria-label="Tier filters">
        <button
          type="button"
          className={`scoreboard-tier-chip${!activeTier ? ' scoreboard-tier-chip--active' : ''}`}
          aria-pressed={!activeTier}
          onClick={() => onTierChange('')}
        >
          <span className="scoreboard-tier-chip__label">All scored</span>
          <span className="scoreboard-tier-chip__count">{total.toLocaleString()}</span>
        </button>
        {entries.map(({ tier, count }) => {
          const active = activeTier === tier;
          return (
            <button
              key={tier}
              type="button"
              className={`scoreboard-tier-chip scoreboard-tier-chip--${tierTone(tier)}${active ? ' scoreboard-tier-chip--active' : ''}`}
              aria-pressed={active}
              onClick={() => onTierChange(active ? '' : tier)}
            >
              <span className="scoreboard-tier-chip__label">{tierLabel(tier, { short: true })}</span>
              <span className="scoreboard-tier-chip__count">{count.toLocaleString()}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
