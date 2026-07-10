import React from 'react';
import { Link } from 'react-router-dom';
import { Flame, ArrowRight } from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import { SAVINGS_SCOPE, SAVINGS_METRIC_SUB } from '../../config/savingsScope';
import { wasteHeatmapLink } from '../../utils/wasteHeatmapLinks';

function CategoryRow({ label, count, savings, currency, href }) {
  if (!count) return null;
  return (
    <Link to={href} className="hub-waste-preview__row">
      <span className="hub-waste-preview__row-label">{label}</span>
      <span className="hub-waste-preview__row-meta">
        {count.toLocaleString()} finding{count !== 1 ? 's' : ''}
        {savings > 0 && (
          <>
            {' · '}
            {formatCurrency(savings, { currency, decimals: 0 })}
          </>
        )}
      </span>
      <ArrowRight size={14} aria-hidden />
    </Link>
  );
}

/**
 * Overview strip linking Optimization hub to the waste heatmap.
 */
export default function HubWastePreview({
  idleSummary,
  idleSweep,
  loading,
  currency = 'CAD',
}) {
  const totalFindings = idleSummary?.total_idle_findings ?? idleSweep?.total_idle_findings ?? 0;
  const totalSavings = idleSummary?.total_estimated_savings_usd
    ?? idleSweep?.total_estimated_savings_usd
    ?? 0;
  const byCategory = idleSweep?.by_category || {};
  const byCategorySavings = idleSweep?.by_category_savings || {};
  const databaseCount = byCategory.Database ?? 0;
  const databaseSavings = byCategorySavings.Database ?? 0;

  const topRules = (idleSummary?.top_rules ?? []).slice(0, 3);

  return (
    <section className="hub-rich-strip card hub-waste-preview" aria-labelledby="hub-waste-preview-title">
      <header className="hub-rich-strip__head hub-waste-preview__head">
        <div className="hub-waste-preview__title">
          <Flame size={16} aria-hidden />
          <div>
            <h3 id="hub-waste-preview-title">Idle & waste heatmap</h3>
            <p className="text-muted text-sm">{SAVINGS_SCOPE.wasteHeatmap.description}</p>
          </div>
        </div>
        <Link to="/waste-heatmap" className="btn btn--ghost btn--sm">
          Open waste heatmap
          <ArrowRight size={14} />
        </Link>
      </header>

      {loading ? (
        <p className="text-muted text-sm hub-waste-preview__loading">Loading waste signals…</p>
      ) : totalFindings > 0 ? (
        <>
          <div className="hub-waste-preview__stats">
            <div className="hub-waste-preview__stat">
              <span className="hub-waste-preview__stat-value">{totalFindings.toLocaleString()}</span>
              <span className="hub-waste-preview__stat-label">Idle findings</span>
            </div>
            <div className="hub-waste-preview__stat hub-waste-preview__stat--savings">
              <span className="hub-waste-preview__stat-value">
                {formatCurrency(totalSavings, { currency, decimals: 0 })}
              </span>
              <span className="hub-waste-preview__stat-label">
                Est. savings/mo · {SAVINGS_METRIC_SUB.waste}
              </span>
            </div>
            {databaseCount > 0 && (
              <div className="hub-waste-preview__stat">
                <span className="hub-waste-preview__stat-value">{databaseCount.toLocaleString()}</span>
                <span className="hub-waste-preview__stat-label">Database waste</span>
              </div>
            )}
          </div>

          <div className="hub-waste-preview__categories">
            <CategoryRow
              label="Database"
              count={databaseCount}
              savings={databaseSavings}
              currency={currency}
              href={wasteHeatmapLink({ category: 'Database' })}
            />
            {Object.entries(byCategory)
              .filter(([cat]) => cat !== 'Database')
              .sort((a, b) => (b[1] || 0) - (a[1] || 0))
              .slice(0, 3)
              .map(([cat, count]) => (
                <CategoryRow
                  key={cat}
                  label={cat}
                  count={count}
                  savings={byCategorySavings[cat] ?? 0}
                  currency={currency}
                  href={wasteHeatmapLink({ category: cat })}
                />
              ))}
          </div>

          {topRules.length > 0 && (
            <div className="hub-waste-preview__rules">
              <span className="hub-waste-preview__rules-label">Top waste rules</span>
              <div className="hub-category-chips">
                {topRules.map((rule) => (
                  <Link
                    key={rule.rule_id}
                    to={wasteHeatmapLink({ ruleId: rule.rule_id })}
                    className="hub-category-chip hub-category-chip--link"
                  >
                    {rule.title ?? rule.rule_id}
                    <strong>{rule.count}</strong>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="hub-waste-preview__empty">
          <p>No idle or waste findings yet. Run optimization analysis to populate Redis, PostgreSQL, and other idle patterns.</p>
          <Link to="/admin/optimization" className="btn btn-secondary btn-sm">
            Open optimization center
            <ArrowRight size={14} />
          </Link>
        </div>
      )}
    </section>
  );
}
