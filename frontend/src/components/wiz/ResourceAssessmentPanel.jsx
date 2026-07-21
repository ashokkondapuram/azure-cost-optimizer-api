import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Shield, AlertCircle } from 'lucide-react';
import { fetchResourceAssessment } from '../../api/pipeline';
import { formatDateTime } from '../../utils/format';
import { toDisplayText } from '../../utils/formatDisplay';
import WizRadialGauge from './charts/WizRadialGauge';

const CLASS_TONE = {
  best: 'wiz-pill wiz-pill--ok',
  good: 'wiz-pill wiz-pill--ok',
  fair: 'wiz-pill wiz-pill--warn',
  poor: 'wiz-pill wiz-pill--warn',
  worst: 'wiz-pill',
};

function ScoreBadge({ score, classification }) {
  const cls = CLASS_TONE[String(classification || '').toLowerCase()] || 'wiz-pill';
  return (
    <span className={cls}>
      {score != null ? `${Math.round(score)}` : '—'}
      {classification ? ` · ${classification}` : ''}
    </span>
  );
}

export default function ResourceAssessmentPanel({
  resourceId,
  compact = false,
  defaultOpen = true,
  hideTitle = false,
}) {
  const rid = resourceId || '';
  const { data, isLoading, isError } = useQuery({
    queryKey: ['resource-assessment', rid],
    queryFn: () => fetchResourceAssessment(rid),
    enabled: Boolean(rid),
    staleTime: 60_000,
    retry: false,
  });

  if (!rid) return null;

  if (isLoading) {
    return (
      <section className="wiz-assessment wiz-assessment--loading">
        {!hideTitle && <div className="wiz-impact-banner__label">Assessment</div>}
        <p className="text-muted text-sm" style={{ margin: 0 }}>Loading assessment data…</p>
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="wiz-assessment wiz-assessment--empty">
        {!hideTitle && <div className="wiz-impact-banner__label">Assessment</div>}
        <p className="text-muted text-sm" style={{ margin: 0 }}>
          No pipeline assessment yet. Sync inventory and run the assessment pipeline.
        </p>
      </section>
    );
  }

  const dq = data.data_quality || {};
  const matched = dq.matchedConditions || [];
  const investigate = dq.matchedInvestigateRules || [];
  const missing = dq.missing_normalized_input || [];
  const requiredKeys = dq.required_metric_keys || [];

  return (
    <section className={`wiz-assessment${compact ? ' wiz-assessment--compact' : ''}`}>
      {!hideTitle && (
        <header className="wiz-assessment__head">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Shield size={14} aria-hidden />
            <h3 style={{ margin: 0, fontSize: compact ? '0.85rem' : '0.92rem' }}>Assessment</h3>
          </div>
          <ScoreBadge score={data.score ?? dq.score} classification={data.classification ?? dq.classification} />
        </header>
      )}
      {hideTitle && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.35rem' }}>
          <ScoreBadge score={data.score ?? dq.score} classification={data.classification ?? dq.classification} />
        </div>
      )}

      <div className="wiz-assessment__gauge">
        <WizRadialGauge
          title="Data quality score"
          value={data.score ?? dq.score ?? 0}
          max={100}
          label={data.classification ?? dq.classification ?? 'quality'}
          fill={(data.score ?? dq.score ?? 0) >= 70 ? '#22c55e' : '#eab308'}
          height={compact ? 140 : 160}
        />
      </div>

      <div className="wiz-detail__meta-grid" style={{ marginTop: '0.65rem' }}>
        <div className="wiz-meta-item">
          <label>Pipeline stage</label>
          <span>{toDisplayText(data.pipeline_stage) || '—'}</span>
        </div>
        <div className="wiz-meta-item">
          <label>Assessment file</label>
          <span style={{ fontSize: '0.78rem', wordBreak: 'break-all' }}>
            {data.assessment_file ? data.assessment_file.split('/').pop() : '—'}
          </span>
        </div>
        <div className="wiz-meta-item">
          <label>Metrics fresh</label>
          <span>{data.metrics_fresh_at ? formatDateTime(data.metrics_fresh_at) : '—'}</span>
        </div>
        <div className="wiz-meta-item">
          <label>Cost fresh</label>
          <span>{data.cost_fresh_at ? formatDateTime(data.cost_fresh_at) : '—'}</span>
        </div>
        {dq.bestConditionsMatched != null && (
          <div className="wiz-meta-item">
            <label>Conditions matched</label>
            <span>{dq.bestConditionsMatched}</span>
          </div>
        )}
        {dq.required_metric_keys?.length > 0 && (
          <div className="wiz-meta-item">
            <label>Required metrics</label>
            <span>{requiredKeys.length} keys</span>
          </div>
        )}
      </div>

      {missing.length > 0 && (
        <div className="wiz-assessment__alert" role="status">
          <AlertCircle size={14} aria-hidden />
          <span>
            Missing inputs:
            {' '}
            {missing.slice(0, 6).join(', ')}
            {missing.length > 6 ? ` +${missing.length - 6} more` : ''}
          </span>
        </div>
      )}

      {matched.length > 0 && (
        <div style={{ marginTop: '0.65rem' }}>
          <div className="wiz-impact-banner__label">Matched conditions</div>
          <div className="wiz-pill-row" style={{ marginTop: '0.35rem' }}>
            {matched.slice(0, defaultOpen ? 12 : 6).map((item) => (
              <span key={item} className="wiz-pill wiz-pill--ok">{item}</span>
            ))}
          </div>
        </div>
      )}

      {investigate.length > 0 && (
        <div style={{ marginTop: '0.65rem' }}>
          <div className="wiz-impact-banner__label">Investigate rules</div>
          <div className="wiz-pill-row" style={{ marginTop: '0.35rem' }}>
            {investigate.slice(0, 8).map((item) => (
              <span key={item} className="wiz-pill wiz-pill--warn">{item}</span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
