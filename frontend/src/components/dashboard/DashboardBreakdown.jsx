import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  categoryHoverInsight,
  categoryInsight,
  categoryRows,
  severityInsight,
  severityRows,
} from '../../utils/dashboardV2Utils';

export default function DashboardBreakdown({ summary }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('severity');

  const severity = useMemo(() => severityRows(summary), [summary]);
  const categories = useMemo(() => categoryRows(summary), [summary]);
  const severityText = useMemo(() => severityInsight(severity), [severity]);
  const categoryText = useMemo(() => categoryInsight(categories), [categories]);
  const [categoryInsightText, setCategoryInsightText] = useState(categoryText);

  useEffect(() => {
    setCategoryInsightText(categoryText);
  }, [categoryText]);

  const goActionCentre = () => navigate('/action-centre');

  const onSeverityKeyDown = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      goActionCentre();
    }
  };

  return (
    <div className="panel">
      <div className="panel-head panel-head--inset panel-head--split">
        <h2 className="section-title section-title--bar">Findings breakdown</h2>
        <Link className="link link--sm" to="/action-centre">
          Filter in action centre →
        </Link>
      </div>
      <div className="breakdown-tabs" role="tablist" aria-label="Breakdown view">
        <button
          type="button"
          className={`breakdown-tab${activeTab === 'severity' ? ' active' : ''}`}
          role="tab"
          aria-selected={activeTab === 'severity'}
          aria-controls="tab-severity"
          id="tab-btn-severity"
          onClick={() => setActiveTab('severity')}
        >
          Severity
        </button>
        <button
          type="button"
          className={`breakdown-tab${activeTab === 'category' ? ' active' : ''}`}
          role="tab"
          aria-selected={activeTab === 'category'}
          aria-controls="tab-category"
          id="tab-btn-category"
          onClick={() => setActiveTab('category')}
        >
          Category
        </button>
      </div>

      <div
        className={`breakdown-panel${activeTab === 'severity' ? ' active' : ''}`}
        id="tab-severity"
        role="tabpanel"
        aria-labelledby="tab-btn-severity"
        hidden={activeTab !== 'severity'}
      >
        <p className="breakdown-insight">{severityText}</p>
        <div className="severity-stack" aria-hidden="true">
          {severity.map((row) => (
            <span
              key={row.key}
              className={`severity-stack__seg severity-stack__seg--${row.className}`}
              style={{ width: `${row.pct}%` }}
            />
          ))}
        </div>
        <div className="severity-grid">
          {severity.map((row) => (
            <div
              key={row.key}
              className={`severity-card severity-card--${row.className}`}
              role="button"
              tabIndex={0}
              onClick={goActionCentre}
              onKeyDown={onSeverityKeyDown}
            >
              <span className="severity-card__count">{row.count}</span>
              <span className="severity-card__label">{row.label}</span>
              <span className="severity-card__pct">{row.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      <div
        className={`breakdown-panel${activeTab === 'category' ? ' active' : ''}`}
        id="tab-category"
        role="tabpanel"
        aria-labelledby="tab-btn-category"
        hidden={activeTab !== 'category'}
      >
        <p className="breakdown-insight" id="breakdown-insight-category">
          {categoryInsightText}
        </p>
        <div className="category-chart category-chart--compact">
          {categories.map((row) => (
            <div
              key={row.key}
              className="category-row"
              role="button"
              tabIndex={0}
              onClick={goActionCentre}
              onKeyDown={onSeverityKeyDown}
              onMouseEnter={() => setCategoryInsightText(categoryHoverInsight(row))}
              onMouseLeave={() => setCategoryInsightText(categoryText)}
              onFocus={() => setCategoryInsightText(categoryHoverInsight(row))}
              onBlur={() => setCategoryInsightText(categoryText)}
            >
              <span className="category-label">
                <span className="cat-dot" style={{ '--cat-color': row.color }} />
                {row.label}
              </span>
              <div className="category-track">
                <div
                  className="category-fill"
                  style={{ width: `${row.widthPct}%`, '--cat-color': row.color }}
                />
              </div>
              <span className="category-count">{row.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
