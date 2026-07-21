import React, { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { formatCategoryLabel, formatSeverityLabel } from '../../utils/taxonomy';
import { formatIsoCurrency, sevClassName } from '../../utils/dashboardV2Utils';

function rankClass(index) {
  if (index === 0) return 'opportunity-item--rank1';
  if (index === 1) return 'opportunity-item--rank2';
  if (index === 2) return 'opportunity-item--rank3';
  return '';
}

export default function DashboardTopOpportunities({ recommendations, currency }) {
  const navigate = useNavigate();

  const items = useMemo(() => {
    const raw = recommendations?.items || [];
    return raw.slice(0, 3).map((item) => ({
      resource_name: item.resource_name,
      rule_name: item.rule_name || item.recommendation,
      category: item.category,
      estimated_savings_usd: item.estimated_savings_usd,
      severity: item.severity,
    }));
  }, [recommendations]);

  const topThreeSavings = items.reduce(
    (sum, item) => sum + Number(item.estimated_savings_usd || 0),
    0,
  );

  const onItemKeyDown = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      navigate('/action-centre');
    }
  };

  return (
    <div className="panel">
      <div className="panel-head panel-head--split">
        <div>
          <h2 className="section-title section-title--bar">Top opportunities</h2>
          <p className="panel-sub">
            {formatIsoCurrency(topThreeSavings, currency, { decimals: 0 })}/mo from top 3 findings
          </p>
        </div>
        <Link className="link" to="/action-centre?hasAction=1">View all →</Link>
      </div>
      <ul className="opportunity-list opportunity-list--rich">
        {items.length === 0 ? (
          <li className="opportunity-item opportunity-item--empty">
            <div className="opportunity-body">
              <strong>No ranked opportunities yet</strong>
              <span>Run analysis to populate savings findings.</span>
            </div>
          </li>
        ) : items.map((item, index) => (
          <li
            key={`${item.resource_name}-${index}`}
            className={`opportunity-item ${rankClass(index)}`}
            tabIndex={0}
            role="button"
            onClick={() => navigate('/action-centre')}
            onKeyDown={onItemKeyDown}
          >
            <div className="opportunity-rank">{index + 1}</div>
            <div className="opportunity-body">
              <strong>{item.resource_name}</strong>
              <span>
                {item.rule_name}
                {' · '}
                {formatCategoryLabel(item.category)}
              </span>
            </div>
            <div className="opportunity-savings">
              {formatIsoCurrency(item.estimated_savings_usd, currency, { decimals: 0 })}/mo
            </div>
            <span className={sevClassName(item.severity)}>
              {formatSeverityLabel(item.severity)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
