import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, LineChart, Server, Zap } from 'lucide-react';
import { LOGIN_FEATURES } from '../../config/appRegistry';

const FEATURE_ICONS = {
  cost: { icon: LineChart, color: '#0ea5e9' },
  inventory: { icon: Server, color: '#6366f1' },
  optimize: { icon: Zap, color: '#38bdf8' },
};

const FEATURE_PREVIEWS = {
  cost: {
    eyebrow: 'Cost explorer',
    metric: '$124,580',
    metricLabel: 'MTD spend',
    detail: 'Across 12 subscriptions',
    bars: [38, 62, 48, 74, 58, 88, 66, 92, 71],
    chips: ['↓ 8% vs last month', '3 budgets on track'],
  },
  inventory: {
    eyebrow: 'Resource catalog',
    metric: '2,847',
    metricLabel: 'Synced resources',
    detail: 'Updated from Azure ARM',
    rows: [
      { label: 'Virtual machines', value: '412', tone: 'sky' },
      { label: 'AKS clusters', value: '28', tone: 'violet' },
      { label: 'Storage accounts', value: '156', tone: 'amber' },
      { label: 'SQL servers', value: '44', tone: 'rose' },
    ],
  },
  optimize: {
    eyebrow: 'Optimization hub',
    metric: '$18,240',
    metricLabel: 'Est. savings/mo',
    detail: 'Engine findings and Advisor merged into actions',
    rows: [
      { label: 'Open findings', value: '47', tone: 'amber' },
      { label: 'Proposed actions', value: '12', tone: 'sky' },
      { label: 'Approved actions', value: '6', tone: 'violet' },
      { label: 'Resources scored', value: '1,284', tone: 'teal' },
    ],
  },
};

const ROTATE_MS = 6500;

function LoginPreviewPanel({ featureId }) {
  const preview = FEATURE_PREVIEWS[featureId] || FEATURE_PREVIEWS.cost;

  return (
    <div className="login-preview" key={featureId}>
      <div className="login-preview__chrome" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="login-preview__body">
        <p className="login-preview__eyebrow">{preview.eyebrow}</p>
        <div className="login-preview__metric">
          <span className="login-preview__metric-value">{preview.metric}</span>
          <span className="login-preview__metric-label">{preview.metricLabel}</span>
        </div>
        <p className="login-preview__detail">{preview.detail}</p>

        {preview.bars && (
          <div className="login-preview__chart" aria-hidden>
            {preview.bars.map((height, index) => (
              <span
                key={index}
                className="login-preview__bar"
                style={{
                  '--bar-height': `${height}%`,
                  '--bar-delay': `${index * 0.06}s`,
                }}
              />
            ))}
          </div>
        )}

        {preview.chips && (
          <div className="login-preview__chips">
            {preview.chips.map((chip) => (
              <span key={chip} className="login-preview__chip">{chip}</span>
            ))}
          </div>
        )}

        {preview.rows && (
          <ul className="login-preview__rows">
            {preview.rows.map((row) => (
              <li key={row.label} className={`login-preview__row login-preview__row--${row.tone}`}>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function LoginFeatureShowcase({ className = '' }) {
  const [activeId, setActiveId] = useState(LOGIN_FEATURES[0]?.id || 'cost');
  const [paused, setPaused] = useState(false);
  const resumeTimerRef = useRef(null);

  const pauseAutoRotate = useCallback(() => {
    setPaused(true);
    if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current);
    resumeTimerRef.current = setTimeout(() => setPaused(false), 12000);
  }, []);

  useEffect(() => () => {
    if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current);
  }, []);

  useEffect(() => {
    if (paused) return undefined;
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) return undefined;

    const timer = setInterval(() => {
      setActiveId((current) => {
        const index = LOGIN_FEATURES.findIndex((f) => f.id === current);
        const next = LOGIN_FEATURES[(index + 1) % LOGIN_FEATURES.length];
        return next?.id || current;
      });
    }, ROTATE_MS);

    return () => clearInterval(timer);
  }, [paused]);

  const selectFeature = (id) => {
    setActiveId(id);
    pauseAutoRotate();
  };

  return (
    <div
      className={`login-showcase ${className}`.trim()}
      data-paused={paused ? '' : undefined}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false);
      }}
    >
      <div className="login-showcase__features" role="tablist" aria-label="Operations workspace">
        {LOGIN_FEATURES.map(({ id, label, desc }, index) => {
          const { icon: Icon, color } = FEATURE_ICONS[id] || FEATURE_ICONS.cost;
          const active = activeId === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`login-feature-tab-${id}`}
              aria-selected={active}
              aria-controls="login-feature-preview"
              tabIndex={active ? 0 : -1}
              className={`login-showcase__feature login-hero__item login-hero__item--${index + 4}${active ? ' login-showcase__feature--active' : ''}`}
              style={{ '--feature-color': color }}
              onClick={() => selectFeature(id)}
            >
              <span className="login-hero__feature-icon">
                <Icon size={16} aria-hidden />
              </span>
              <span className="login-hero__feature-copy">
                <strong>{label}</strong>
                <span>{desc}</span>
              </span>
              <ArrowRight size={14} className="login-showcase__feature-arrow" aria-hidden />
              <span className="login-showcase__feature-progress" aria-hidden />
            </button>
          );
        })}
      </div>

      <div
        id="login-feature-preview"
        role="tabpanel"
        aria-labelledby={`login-feature-tab-${activeId}`}
        className="login-showcase__preview login-hero__item login-hero__item--6"
      >
        <LoginPreviewPanel featureId={activeId} />
      </div>
    </div>
  );
}
