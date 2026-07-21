import React from 'react';
import {
  formatInsightCurrency,
  skuBadgeClass,
  shouldShowTargetSku,
  isSkuDeleteAction,
} from '../../utils/insightCanvasUtils';
import { toDisplayText } from '../../utils/formatDisplay';
import { resourceBilledMtd, resourceRetailMonthly, resourceRetailCurrency } from '../../utils/costCurrency';

const RETAIL_TOOLTIP = 'Catalog pricing from Azure Retail Prices — estimated monthly, not your invoice.';

function SkuSpecList({ specs, deltaFrom }) {
  if (!specs?.length) return null;
  const fromMap = deltaFrom ? Object.fromEntries(deltaFrom.map((s) => [s.label, s.value])) : null;
  return (
    <ul className="ic-sku-specs">
      {specs.map((s) => {
        const fromVal = fromMap?.[s.label];
        const changed = fromMap && fromVal != null && fromVal !== s.value;
        return (
          <li key={s.label} className="ic-sku-spec">
            <span className="ic-sku-spec__label">{s.label}</span>
            <span className="ic-sku-spec__vals">
              {changed ? (
                <>
                  <span className="ic-sku-spec__from">{toDisplayText(fromVal)}</span>
                  <span className="ic-sku-spec__arrow" aria-hidden="true">→</span>
                  <span className="ic-sku-spec__to">{toDisplayText(s.value)}</span>
                </>
              ) : (
                <span className="ic-sku-spec__same">{toDisplayText(s.value)}</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function SkuCostBlock({ billedMtd, retailMonthly, retailCurrency, currency }) {
  return (
    <div className="ic-sku-cost-single">
      {billedMtd > 0 && (
        <>
          <span className="ic-sku-cost-single__label">Billed MTD</span>
          <span className="ic-sku-cost-single__value" title="Month to date (billed)">
            {formatInsightCurrency(billedMtd, currency, 2)}
          </span>
        </>
      )}
      {retailMonthly > 0 && (
        <>
          <span className="ic-sku-cost-single__label ic-sku-cost-single__label--retail" title={RETAIL_TOOLTIP}>
            Retail estimate
          </span>
          <span className="ic-sku-cost-single__value ic-sku-cost-single__value--retail">
            {formatInsightCurrency(retailMonthly, retailCurrency || currency, 2)}
            <span className="ic-sku-cost-single__suffix">/mo</span>
          </span>
        </>
      )}
      {billedMtd <= 0 && retailMonthly <= 0 && (
        <>
          <span className="ic-sku-cost-single__label">Monthly cost</span>
          <span className="ic-sku-cost-single__value">—</span>
        </>
      )}
    </div>
  );
}

export default function InsightSkuPanel({ data }) {
  const sku = data?.sku;
  if (!sku) return <aside className="ic-sku-panel" aria-label="Deployment" />;

  const current = sku.current || {};
  const showTarget = shouldShowTargetSku(sku);
  const isDelete = isSkuDeleteAction(sku);
  const billedMtd = resourceBilledMtd(data.row || {}) || Number(data.billedMtd || 0);
  const retailMonthly = resourceRetailMonthly(data.row || {}) || Number(current.monthlyCost || data.retailMonthly || 0);
  const retailCurrency = resourceRetailCurrency(data.row || {}, data.currency);
  const currentCost = retailMonthly || billedMtd;
  const targetCost = showTarget
    ? (sku.target?.monthlyCost ?? Math.max(0, currentCost - (data.savings || 0)))
    : 0;
  const metaParts = [current.tier, current.size, current.region].filter((v) => v && v !== '—');

  return (
    <aside className="ic-sku-panel" aria-label="Deployment">
      <div className="ic-sku-panel__head">
        <h2 className="ic-sku-panel__title">Deployment</h2>
        {showTarget && (
          <span className={`ic-sku-badge ${skuBadgeClass(sku.changeType)}`}>
            {sku.changeType || data.category}
          </span>
        )}
      </div>

      <div className="ic-sku-card ic-sku-card--current">
        <div className="ic-sku-card__head">
          <span className="ic-sku-badge ic-sku-badge--current">Current</span>
        </div>
        <span className="ic-sku-block__name">{current.name}</span>
        <span className="ic-sku-block__meta">{metaParts.join(' · ') || 'As deployed today'}</span>
        <SkuCostBlock
          billedMtd={billedMtd}
          retailMonthly={retailMonthly}
          retailCurrency={retailCurrency}
          currency={data.currency}
        />
        {(current.specs || []).length > 0 && (
          <div className="ic-sku-card__section">
            <span className="ic-sku-card__section-label">Key specs</span>
            <SkuSpecList specs={current.specs} />
          </div>
        )}
      </div>

      {isDelete && (
        <p className="ic-sku-no-replacement">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          No replacement — this resource will be removed.
        </p>
      )}

      {showTarget && !isDelete && (
        <>
          <div className="ic-sku-divider" aria-hidden="true" />
          <div className="ic-sku-card ic-sku-card--recommended">
            <div className="ic-sku-card__head">
              <span className="ic-sku-badge ic-sku-badge--recommended">Recommended</span>
            </div>
            <span className="ic-sku-block__name">{sku.target?.name}</span>
            <span className="ic-sku-block__meta">
              {[sku.target?.tier, sku.target?.size, sku.target?.region].filter((v) => v && v !== '—').join(' · ') || 'After change'}
            </span>
            <SkuCostBlock
              billedMtd={0}
              retailMonthly={targetCost}
              retailCurrency={retailCurrency}
              currency={data.currency}
            />
            {(sku.target?.specs || []).length > 0 && (
              <div className="ic-sku-card__section">
                <span className="ic-sku-card__section-label">Key specs</span>
                <SkuSpecList specs={sku.target.specs} deltaFrom={current.specs} />
              </div>
            )}
            {data.savings > 0 && (
              <div className="ic-sku-savings">
                <span className="ic-sku-savings__label">Est. savings</span>
                <span className="ic-sku-savings__value">
                  {formatInsightCurrency(data.savings, data.currency, 0)}
                  /mo
                </span>
                {data.savingsPct > 0 && (
                  <span className="ic-sku-savings__pct">
                    {data.savingsPct}
                    % reduction
                  </span>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
