import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { History } from 'lucide-react';
import { fetchFindingActivity } from '../api/azure';
import { formatDateTime } from '../utils/format';
import { StatusBadge } from './FindingBadges';

function activitySummary(item) {
  if (item.action === 'status_change') {
    const from = item.from_status || 'unknown';
    const to = item.to_status || 'unknown';
    return (
      <>
        Status changed from <StatusBadge status={from} /> to <StatusBadge status={to} />
      </>
    );
  }
  return item.note || item.action;
}

export default function ActivityTimeline({ findingId, subscriptionId, enabled = true }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['finding-activity', subscriptionId, findingId],
    queryFn: () => fetchFindingActivity(findingId, subscriptionId),
    enabled: enabled && !!findingId && !!subscriptionId,
    staleTime: 30_000,
  });

  const items = data?.items || [];

  if (!enabled || !findingId) return null;

  return (
    <section className="activity-timeline" aria-label="Activity log">
      <h4 className="activity-timeline__title">
        <History size={14} aria-hidden />
        Activity
      </h4>
      {isLoading && <p className="activity-timeline__empty">Loading activity…</p>}
      {isError && <p className="activity-timeline__empty">Could not load activity.</p>}
      {!isLoading && !isError && items.length === 0 && (
        <p className="activity-timeline__empty">No activity recorded yet.</p>
      )}
      {items.length > 0 && (
        <ol className="activity-timeline__list">
          {items.map((item) => (
            <li key={item.id} className="activity-timeline__item">
              <div className="activity-timeline__body">{activitySummary(item)}</div>
              <div className="activity-timeline__meta">
                {item.user_name && <span>{item.user_name}</span>}
                {item.created_at && (
                  <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
