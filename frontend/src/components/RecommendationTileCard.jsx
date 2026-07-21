import React from 'react';
import { ChevronDown } from 'lucide-react';
import SeverityChip, { severityAccentClass } from './visual/SeverityChip';
import RecommendationHelpTooltip from './RecommendationHelpTooltip';
import RecommendationDetailCard from './RecommendationDetailCard';
import { formatCurrency } from '../utils/format';
import { resolveFindingPreviewText } from '../utils/actionNarrativeUtils';
import { toDisplayText } from '../utils/formatDisplay';

function truncateText(text, maxLen = 72) {
  const value = toDisplayText(text);
  if (!value) return '';
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1).trim()}…`;
}

export default function RecommendationTileCard({
  finding,
  currency = 'CAD',
  expanded = false,
  onToggle,
  resourceTypeLabel = '',
  hideSeverity = false,
  subscriptionId,
  onStatusChange,
  statusPending = false,
  allowResolve = true,
  showStatus = true,
  inventoryContext = null,
  monthlyResourceCost = 0,
}) {
  const f = finding;
  const savingsUsd = Number(f.estimated_savings_usd) > 0;
  const resourceHint = resourceTypeLabel || f.resource_name || '';
  const previewText = resolveFindingPreviewText(f);
  const detailId = `rec-tile-detail-${f.id}`;

  const handleToggle = () => {
    onToggle?.(f.id);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleToggle();
    }
  };

  return (
    <article
      className={`rec-tile-card${expanded ? ' rec-tile-card--expanded' : ''} ${severityAccentClass(f.severity).replace('rec-detail-card', 'rec-tile-card')}`}
      data-finding-id={f.id}
    >
      <button
        type="button"
        className="rec-tile-card__face"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-expanded={expanded}
        aria-controls={detailId}
      >
        <div className="rec-tile-card__top">
          {!hideSeverity && (
            <SeverityChip severity={f.severity} size={11} />
          )}
          {savingsUsd && (
            <span className={`rec-tile-card__savings${f.estimated_savings_usd > 500 ? ' rec-tile-card__savings--high' : ''}`}>
              {formatCurrency(f.estimated_savings_usd, { currency, decimals: 0 })}/mo
            </span>
          )}
        </div>
        <span className="rec-tile-card__title">
          <RecommendationHelpTooltip
            finding={f}
            compact
            detailHint={expanded ? 'Details below' : 'Select to view details'}
          >
            {f.rule_name}
          </RecommendationHelpTooltip>
        </span>
        {resourceHint && (
          <span className="rec-tile-card__hint">{resourceHint}</span>
        )}
        {!expanded && previewText && (
          <span className="rec-tile-card__preview">{truncateText(previewText)}</span>
        )}
        <ChevronDown
          size={14}
          className={`rec-tile-card__chevron${expanded ? ' rec-tile-card__chevron--open' : ''}`}
          aria-hidden
        />
      </button>

      {expanded && (
        <div
          id={detailId}
          className="rec-tile-card__detail"
          role="region"
          aria-label={`${f.rule_name} details`}
        >
          <RecommendationDetailCard
            finding={f}
            currency={currency}
            subscriptionId={subscriptionId}
            onStatusChange={onStatusChange}
            statusPending={statusPending}
            allowResolve={allowResolve}
            showStatus={showStatus}
            hideSeverity={hideSeverity}
            compact
            bodyOnly
            inventoryContext={inventoryContext}
            monthlyResourceCost={monthlyResourceCost}
          />
        </div>
      )}
    </article>
  );
}
