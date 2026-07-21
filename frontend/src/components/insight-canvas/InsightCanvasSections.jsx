import React, { useState } from 'react';
import { formatInsightCurrency, isMajorProperty, CANVAS_SECTION_DEFS } from '../../utils/insightCanvasUtils';
import { toDisplayText } from '../../utils/formatDisplay';
import { formatEvidenceRow } from '../../utils/evidenceUtils';
import { formatCurrency } from '../../utils/format';
import RuleEvidenceTable from '../recommendations/RuleEvidenceTable';
import RecommendationEvidenceList from '../recommendations/RecommendationEvidenceList';
import AksNodePoolsTable from '../../it-services/containers-aks/components/AksNodePoolsTable';

function EvidenceMetricViz({ metric }) {
  if (!metric?.label) return null;
  const pct = metric.pct != null ? Math.min(100, Math.max(0, metric.pct)) : null;
  return (
    <div className="ic-metric-viz ic-metric-viz--evidence">
      <span className="ic-metric-viz__label">{metric.label}</span>
      <span className="ic-metric-viz__value">{metric.value}</span>
      {pct != null && (
        <div className="ic-metric__track">
          <div
            className="ic-metric__fill"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function EvidenceGroupList({ groups }) {
  if (!groups?.length) return null;
  return (
    <div className="ic-evidence-list">
      {groups.map((group) => (
        <div key={group.key} className="ic-evidence-group">
          <h4 className="ic-evidence-group__label">{group.label}</h4>
          {group.rows.map((rawRow, index) => {
            const row = formatEvidenceRow(rawRow);
            if (!row) return null;
            const hint = row.detail || rawRow?.hint;
            return (
              <div
                key={`${group.key}-${row.label || index}`}
                className={`ic-evidence-row${row.major ? ' ic-evidence-row--major' : ''}`}
              >
                <span className="ic-evidence-row__label">{row.label}</span>
                <span className="ic-evidence-row__value">{row.value}</span>
                {hint && (
                  <span className="ic-evidence-row__hint">{hint}</span>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function InsightRowList({ items }) {
  if (!items?.length) return null;
  return (
    <ul className="ic-bullet-list">
      {items.map((item, index) => {
        const row = formatEvidenceRow(item);
        if (!row) return null;
        const key = row.label || `insight-${index}`;
        return (
          <li
            key={key}
            className={row.tone ? `ic-insight-row ic-insight-row--${row.tone}` : 'ic-insight-row'}
          >
            {row.label ? (
              <>
                <strong>{row.label}</strong>
                {row.value ? `: ${row.value}` : null}
              </>
            ) : (
              row.value
            )}
            {row.detail && (
              <span className="ic-insight-row__detail">{row.detail}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EvidencePanel({
  groups,
  overflowGroups,
  overflowCount,
  primaryMetric,
  ruleEvidence,
  evidenceFactors,
}) {
  const [expanded, setExpanded] = useState(false);
  const hasRuleEvidence = ruleEvidence?.length > 0;
  const hasEvidence = groups?.length > 0 || hasRuleEvidence;

  if (!hasEvidence) {
    return (
      <p className="ic-lead ic-lead--muted">
        No supporting evidence for this finding.
      </p>
    );
  }

  return (
    <>
      {hasRuleEvidence ? (
        <RuleEvidenceTable rows={ruleEvidence} factors={evidenceFactors} />
      ) : (
        <EvidenceGroupList groups={groups} />
      )}
      {!hasRuleEvidence && overflowCount > 0 && (
        <>
          <button
            type="button"
            className="ic-evidence-more btn btn-ghost btn-sm"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? 'Show less' : `View ${overflowCount} more`}
          </button>
          {expanded && <EvidenceGroupList groups={overflowGroups} />}
        </>
      )}
      <EvidenceMetricViz metric={primaryMetric} />
    </>
  );
}

function CostEnvelope({ envelope, labels, currency }) {
  if (!envelope) return null;
  const billedLabel = labels?.billed_mtd || 'Billed month-to-date';
  const retailLabel = labels?.retail_monthly || 'Retail monthly estimate';
  return (
    <div className="ic-cost-envelope">
      <div className="ic-cost-envelope__row">
        <span className="ic-cost-envelope__label">{billedLabel}</span>
        <span className="ic-cost-envelope__value">
          {formatCurrency(envelope.billed_mtd, { currency, decimals: 2 })}
        </span>
      </div>
      <div className="ic-cost-envelope__row">
        <span className="ic-cost-envelope__label">{retailLabel}</span>
        <span className="ic-cost-envelope__value">
          {formatCurrency(envelope.retail_monthly, {
            currency: envelope.retail_currency || currency,
            decimals: 2,
          })}
        </span>
        {envelope.retail_source && (
          <span className="ic-cost-envelope__source">{envelope.retail_source}</span>
        )}
      </div>
    </div>
  );
}

function InstanceGrid({ instances, metricsLoading = false, metricsError = false }) {
  if (!instances?.length) {
    if (metricsLoading) {
      return <p className="ic-lead ic-lead--muted">Loading instance metrics…</p>;
    }
    if (metricsError) {
      return <p className="ic-lead ic-lead--muted">Metrics unavailable</p>;
    }
    return null;
  }
  return (
    <div className="ic-table-wrap">
      <table className="ic-table">
        <thead>
          <tr>
            <th>Instance</th>
            <th>Size</th>
            <th>State</th>
            <th>Zone</th>
            <th>CPU</th>
            <th>Memory</th>
          </tr>
        </thead>
        <tbody>
          {instances.map((instance) => (
            <tr key={instance.name}>
              <td>{instance.name}</td>
              <td>{instance.size || '—'}</td>
              <td>{instance.powerState || '—'}</td>
              <td>{instance.zone || '—'}</td>
              <td className={instance.metricsUnavailable ? 'ic-muted' : undefined}>
                {instance.cpu || '—'}
              </td>
              <td className={instance.metricsUnavailable ? 'ic-muted' : undefined}>
                {instance.memory || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function metricFillTone(pct) {
  if (pct == null || Number.isNaN(Number(pct))) return '';
  const n = Number(pct);
  if (n >= 80) return ' ic-metric__fill--danger';
  if (n >= 50) return ' ic-metric__fill--warn';
  if (n < 10) return ' ic-metric__fill--idle';
  return ' ic-metric__fill--ok';
}

function MetricGrid({ metrics }) {
  if (!metrics?.length) return null;
  return (
    <div className="ic-metrics-grid">
      {metrics.map((m) => {
        const width = m.pct != null ? Math.min(100, Math.max(0, m.pct)) : 0;
        const showBar = m.pct != null;
        return (
          <div key={m.label} className="ic-metric">
            <div className="ic-metric__row">
              <span className="ic-metric__label">{m.label}</span>
              <span className="ic-metric__value">{toDisplayText(m.value)}</span>
            </div>
            {showBar && (
              <div className="ic-metric__track">
                <div
                  className={`ic-metric__fill${metricFillTone(m.pct)}`}
                  style={{ width: `${width}%` }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PropertyGridItems({ items, keyPrefix = 'prop' }) {
  return (items || []).map((item, index) => {
    const displayValue = toDisplayText(item.value);
    return (
      <div
        key={`${keyPrefix}-${item.label}-${index}`}
        className={`ac-prop-item ac-prop-item--compact${isMajorProperty(item) ? ' ac-prop-item--major ic-prop--major' : ''}`}
      >
        <dt className="ac-prop-item__label">{item.label}</dt>
        <dd className="ac-prop-item__value" title={displayValue}>{displayValue}</dd>
      </div>
    );
  });
}

function PropertyGroups({ groups, profileType }) {
  const visible = (groups || []).filter((g) => g.items?.length > 0);
  if (!visible.length) return null;

  const isDisk = profileType === 'disk';

  if (!isDisk && visible.length === 1 && visible[0].flat) {
    return (
      <dl className="ac-prop-grid ac-prop-grid--compact ic-prop-grid--flat">
        <PropertyGridItems items={visible[0].items} />
      </dl>
    );
  }

  return visible.map((g) => (
    <div key={g.title || 'properties'} className="ic-prop-group">
      {g.title ? <h4 className="ic-prop-group__title">{g.title}</h4> : null}
      <dl className={`ac-prop-grid ac-prop-grid--compact${isDisk ? ' ac-prop-grid--flat2' : ''}`}>
        <PropertyGridItems items={g.items} keyPrefix={g.title || 'properties'} />
      </dl>
    </div>
  ));
}

function CostRows({ items, currency }) {
  if (!items?.length) return <p className="ic-lead ic-lead--muted">No cost breakdown available.</p>;
  return (
    <div className="ic-cost-rows">
      {items.map((item) => (
        <div key={item.label} className="ic-cost-row">
          <span className="ic-cost-row__label">{item.label}</span>
          <span className="ic-cost-row__vals">
            <span className="ic-cost-row__current">
              {formatInsightCurrency(item.current, currency, 0)}
            </span>
            {item.projected != null && (
              <>
                <span className="ic-cost-row__arrow">→</span>
                <span className="ic-cost-row__projected">
                  {formatInsightCurrency(item.projected, currency, 0)}
                </span>
              </>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

function SectionBlock({ sectionId, data }) {
  const sev = `ic-sev--${data.severityKey}`;

  switch (sectionId) {
    case 'summary': {
      const sevClass = `ic-sev--${data.severityKey}`;
      const showState = data.profile?.showState !== false;
      const stateTile = showState && data.state && data.state !== '—' ? (
        <div className="ic-tile ic-tile--kpi ic-tile--kpi-state">
          <span className="ic-kpi__label">State</span>
          <span className="ic-kpi__value ic-kpi__value--sm">{data.state}</span>
        </div>
      ) : (
        <div className="ic-tile ic-tile--kpi ic-tile--muted">
          <span className="ic-kpi__label">Workflow</span>
          <span className="ic-kpi__value ic-kpi__value--sm">{data.workflow}</span>
        </div>
      );

      return (
        <>
          <div className="ic-bento ic-bento--kpis ic-bento--kpis-summary">
            <div className="ic-tile ic-tile--kpi ic-tile--kpi-savings">
              <span className="ic-kpi__label">Est. savings</span>
              <span className="ic-kpi__value">
                {data.savings > 0
                  ? `${formatCurrency(data.savings, { currency: data.currency, decimals: 0 })}/mo`
                  : '—'}
              </span>
              {data.savingsPct > 0 && (
                <span className="ic-kpi__trend">
                  {data.savingsPct}
                  % of current spend
                </span>
              )}
            </div>
            <div className={`ic-tile ic-tile--kpi ic-tile--kpi-severity ${sevClass}`}>
              <span className="ic-kpi__label">Severity</span>
              <span className="ic-kpi__value ic-kpi__sev">{data.severity}</span>
            </div>
            {stateTile}
            <div className="ic-tile ic-tile--kpi ic-tile--muted">
              <span className="ic-kpi__label">Payback</span>
              <span className="ic-kpi__value ic-kpi__value--sm">{data.payback}</span>
            </div>
          </div>
          <div className="ic-tile ic-tile--muted ic-tile--analysis-meta">
            <span className="ic-tile__eyebrow">Analysis</span>
            <div className="ic-meta-rows">
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Category</span>
                <span className="ic-meta-row__value">{data.category}</span>
              </div>
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Source</span>
                <span className="ic-meta-row__value">
                  <span className={`source-tag source-tag--${data.sourceKey}`}>{data.source}</span>
                </span>
              </div>
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Rule</span>
                <span className="ic-meta-row__value">
                  <code className="ic-rule">{data.rule}</code>
                </span>
              </div>
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Analyzed</span>
                <span className="ic-meta-row__value">{data.analyzed}</span>
              </div>
            </div>
          </div>
        </>
      );
    }
    case 'recommendation':
      if (data.recommendationItems?.length > 1) {
        return (
          <RecommendationEvidenceList
            items={data.recommendationItems}
            currency={data.currency}
            resourceName={data.title}
            className="ic-rec-evidence-list"
          />
        );
      }
      return (
        <div className="ic-bento ic-bento--hero">
          <article className={`ic-tile ic-tile--hero ic-rec-hero ${sev}`}>
            <span className="ic-tile__eyebrow">Recommendation</span>
            <h2 className="ic-tile__title">{data.recTitle}</h2>
            {data.rationale && (
              <p className="ic-tile__desc">{data.rationale}</p>
            )}
            {data.related?.length > 0 && (
              <ul className="ic-related-list">
                {data.related.map((r) => (
                  <li key={r.title} className="ic-related-item">
                    <span className={`sev sev-${r.sev}`}>{r.sev}</span>
                    <span>{r.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>
          <article className="ic-tile ic-tile--evidence">
            <span className="ic-tile__eyebrow">Evidence</span>
            <EvidencePanel
              groups={data.evidenceGroups}
              overflowGroups={data.evidenceOverflowGroups}
              overflowCount={data.evidenceOverflowCount}
              primaryMetric={data.primaryEvidenceMetric}
              ruleEvidence={data.ruleEvidence}
              evidenceFactors={data.evidenceFactors}
            />
          </article>
        </div>
      );
    case 'metrics':
      return (
        <div className="ic-tile ic-tile--metrics">
          <div className="ic-tile__head-row">
            <span className="ic-tile__eyebrow">Azure Monitor · 7 days</span>
            <span className="ic-timespan">7 days</span>
          </div>
          {data.metricsLoading && !data.metrics?.length ? (
            <p className="ic-lead ic-lead--muted">Loading metrics…</p>
          ) : data.metrics?.length ? (
            <MetricGrid metrics={data.metrics} />
          ) : (
            <p className="ic-lead ic-lead--muted">Metrics load when analysis has run for this resource.</p>
          )}
        </div>
      );
    case 'trends':
      return (
        <div className="ic-tile ic-tile--trends">
          <span className="ic-tile__eyebrow">Utilization trends</span>
          {data.trends?.length ? (
            <div className="ic-trend-rows">
              {data.trends.map((t) => (
                <div key={t.label} className={`ic-trend-row ic-trend-row--${t.tone || 'muted'}`}>
                  <span className="ic-trend-row__label">{t.label}</span>
                  <span className="ic-trend-row__value">{t.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="ic-lead ic-lead--muted">Trend summary appears when utilization history is available.</p>
          )}
        </div>
      );
    case 'cost':
      return (
        <div className="ic-tile">
          <div className="ic-cost-intro">
            <span className="ic-tile__eyebrow">Cost breakdown</span>
          </div>
          <CostEnvelope
            envelope={data.costEnvelope}
            labels={data.costFieldLabels}
            currency={data.currency}
          />
          <CostRows items={data.costBreakdown?.items} currency={data.currency} />
        </div>
      );
    case 'insights':
      return (
        <div className="ic-tile">
          {data.insights?.headline ? (
            <p className="ic-lead">{data.insights.headline}</p>
          ) : (
            <p className="ic-lead ic-lead--muted">Workload insights appear when the analysis engine provides them.</p>
          )}
          {data.insights?.workload?.length > 0 && (
            <>
              <h4 className="ic-subtitle">Workload</h4>
              <InsightRowList items={data.insights.workload} />
            </>
          )}
          {data.insights?.dependencies?.length > 0 && (
            <>
              <h4 className="ic-subtitle">Dependencies</h4>
              <InsightRowList items={data.insights.dependencies} />
            </>
          )}
          {data.insights?.cost?.length > 0 && (
            <>
              <h4 className="ic-subtitle">Cost signals</h4>
              <InsightRowList items={data.insights.cost} />
            </>
          )}
        </div>
      );
    case 'pools':
      return (
        <div className="ic-tile ic-tile--pools">
          {data.metricsLoading && !data.nodePools?.length ? (
            <p className="ic-lead ic-lead--muted">Loading node pool metrics…</p>
          ) : data.nodePools?.length ? (
            <>
              {data.metricsLoading && (
                <p className="ic-lead ic-lead--muted ic-status-note">Loading pool utilization…</p>
              )}
              {data.metricsError && !data.metricsLoading && (
                <p className="ic-lead ic-lead--muted ic-status-note">Metrics unavailable for some pools</p>
              )}
              <AksNodePoolsTable
                pools={data.nodePools}
                resourceId={data.resourceId}
                subscriptionId={data.subscriptionId}
                timespan={data.metricsTimespan || 'P7D'}
                compact
                emptyMessage="No node pool data synced yet. Run inventory sync to load agent pool profiles."
              />
            </>
          ) : (
            <p className="ic-lead ic-lead--muted">Node pool metrics appear for AKS clusters.</p>
          )}
        </div>
      );
    case 'instances':
      return (
        <div className="ic-tile ic-tile--instances">
          <InstanceGrid
            instances={data.instances}
            metricsLoading={data.metricsLoading}
            metricsError={data.metricsError}
          />
          {!data.instances?.length && !data.metricsLoading && !data.metricsError && (
            <p className="ic-lead ic-lead--muted">
              Instance metrics appear when Azure Monitor or scale set inventory is available.
            </p>
          )}
        </div>
      );
    case 'properties': {
      const groups = data.canvasPropertyGroups?.length
        ? data.canvasPropertyGroups
        : data.propertyGroups;
      if (!groups?.length) return null;
      return (
        <div className="ic-tile ic-tile--properties">
          <PropertyGroups groups={groups} profileType={data.profileType} />
        </div>
      );
    }
    case 'advisor':
      return (
        <div className="ic-tile">
          <span className="ic-tile__eyebrow">Azure Advisor</span>
          {data.advisor?.length ? (
            <div className="ic-advisor-list">
              {data.advisor.map((a) => (
                <div key={a.title} className="ic-advisor-row">
                  <span className="ic-advisor-row__title">{a.title}</span>
                  <span className="ic-advisor-row__impact">
                    {a.impact}
                    {' '}
                    impact
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="ic-lead ic-lead--muted">No Advisor recommendations for this resource.</p>
          )}
        </div>
      );
    case 'tags':
      return (
        <div className="ic-tile">
          {data.tags?.length ? (
            <div className="ic-tag-chips">
              {data.tags.map((t) => (
                <span key={t} className="ic-tag-chip">{t}</span>
              ))}
            </div>
          ) : (
            <p className="ic-lead ic-lead--muted">No tags on this resource.</p>
          )}
        </div>
      );
    case 'history':
      return (
        <div className="ic-bento ic-bento--pair">
          <div className="ic-tile ic-tile--muted">
            <span className="ic-tile__eyebrow">Finding history</span>
            <div className="ic-meta-rows">
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Last analyzed</span>
                <span className="ic-meta-row__value">{data.analyzed}</span>
              </div>
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Previous action</span>
                <span className="ic-meta-row__value">{data.prevAction}</span>
              </div>
              <div className="ic-meta-row">
                <span className="ic-meta-row__label">Created</span>
                <span className="ic-meta-row__value">{data.created}</span>
              </div>
            </div>
          </div>
          <div className="ic-tile ic-tile--muted">
            <span className="ic-tile__eyebrow">Timeline</span>
            <ol className="ic-timeline">
              {(data.timeline || []).map((t) => (
                <li key={t} className="ic-timeline__item">
                  <span className="ic-timeline__dot" aria-hidden="true" />
                  <span className="ic-timeline__text" dangerouslySetInnerHTML={{ __html: t }} />
                </li>
              ))}
            </ol>
          </div>
        </div>
      );
    default:
      return null;
  }
}

export default function InsightCanvasSections({ data }) {
  const sections = data?.sections || [];
  const profileType = data?.profileType || 'vm';
  let metricsTrendsCombined = false;

  return (
    <div className="ic-canvas" id="ic-canvas">
      {sections.map((sectionId) => {
        const def = CANVAS_SECTION_DEFS[sectionId] || { label: sectionId };
        const anchor = `section-${sectionId}`;

        if (sectionId === 'metrics' && sections.includes('trends') && ['vm', 'vmss', 'database'].includes(profileType)) {
          if (metricsTrendsCombined) return null;
          metricsTrendsCombined = true;
          return (
            <section key={sectionId} className="ic-section" id={anchor} aria-labelledby={`heading-${anchor}`}>
              <h2 className="ic-section__label" id={`heading-${anchor}`}>
                {def.label}
                {' '}
                & trends
              </h2>
              <div className="ic-bento ic-bento--metrics-wide">
                <SectionBlock sectionId="metrics" data={data} />
                <SectionBlock sectionId="trends" data={data} />
              </div>
            </section>
          );
        }

        if (sectionId === 'trends' && metricsTrendsCombined) return null;

        if (sectionId === 'pools' && profileType === 'kubernetes') {
          return (
            <section key={sectionId} className="ic-section" id={anchor} aria-labelledby={`heading-${anchor}`}>
              <h2 className="ic-section__label" id={`heading-${anchor}`}>{def.label}</h2>
              <div className="ic-bento ic-bento--stack">
                <SectionBlock sectionId={sectionId} data={data} />
              </div>
            </section>
          );
        }

        return (
          <section key={sectionId} className="ic-section" id={anchor} aria-labelledby={`heading-${anchor}`}>
            <h2 className="ic-section__label" id={`heading-${anchor}`}>{def.label}</h2>
            <SectionBlock sectionId={sectionId} data={data} />
          </section>
        );
      })}
    </div>
  );
}
