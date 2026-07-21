import React from 'react';
import { LogOut } from 'lucide-react';
import useDashboardCostPeriod from '../../hooks/useDashboardCostPeriod';
import { dashboardCostPeriodLabel } from '../../utils/costTimespanUtils';
import { formatSeatLabel } from '../../utils/roleLabels';

function userInitials(user) {
  const name = String(user?.display_name || user?.username || '').trim();
  if (!name) return '?';
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export default function RailFoot({
  collapsed = false,
  user,
  onLogout,
}) {
  const [costPeriod, onPeriodChange, periodOptions] = useDashboardCostPeriod();

  if (collapsed) {
    return (
      <div className="rail-foot">
        <div className="rail-footer">
          <div
            className="rail-user"
            aria-label={`${user?.display_name || user?.username || 'User'}, ${formatSeatLabel(user?.role)}`}
          >
            <div className="avatar" aria-hidden="true">{userInitials(user)}</div>
          </div>
          <button
            type="button"
            className="rail-sign-out sidebar-footer__logout--icon"
            onClick={onLogout}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    );
  }

  const displayName = user?.display_name || user?.username || 'User';
  const seatLabel = formatSeatLabel(user?.role);

  return (
    <div className="rail-foot">
      <div className="rail-section rail-section--period">
        <label className="rail-section__label" htmlFor="rail-period-select">Cost period</label>
        <div className="period-field">
          <select
            id="rail-period-select"
            className="period-select"
            value={costPeriod}
            onChange={(e) => onPeriodChange(e.target.value)}
            aria-label={`Cost period — ${dashboardCostPeriodLabel(costPeriod, periodOptions)}`}
          >
            {periodOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="rail-footer">
        <div
          className="rail-user"
          aria-label={`${displayName}, ${seatLabel}`}
        >
          <div className="avatar" aria-hidden="true">{userInitials(user)}</div>
          <div className="rail-user__meta">
            <strong>{displayName}</strong>
            <span className="rail-user__seat">{seatLabel}</span>
          </div>
          <div className="rail-user__actions">
            <button
              type="button"
              className="rail-sign-out"
              onClick={onLogout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
