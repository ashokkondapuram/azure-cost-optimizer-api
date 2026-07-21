import React, { useContext, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { History } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import ActivityTimeline from '../components/ActivityTimeline';
import { SubscriptionRequired } from '../components/QueryStates';

export default function ActivityLog() {
  const { subscription } = useContext(AppCtx);
  const [searchParams, setSearchParams] = useSearchParams();
  const [findingId, setFindingId] = useState(() => searchParams.get('finding') || '');

  const applyFinding = (value) => {
    const trimmed = (value || '').trim();
    setFindingId(trimmed);
    const next = new URLSearchParams(searchParams);
    if (trimmed) next.set('finding', trimmed);
    else next.delete('finding');
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="page activity-log-page">
      <PageHeader
        title="Activity log"
        subtitle="Review status changes and notes for a finding."
        icon={History}
      />

      {!subscription && <SubscriptionRequired />}

      {subscription && (
        <section className="card activity-log-page__search">
          <label className="activity-log-page__label" htmlFor="finding-id">Finding ID</label>
          <div className="activity-log-page__row">
            <input
              id="finding-id"
              className="input"
              value={findingId}
              onChange={(e) => setFindingId(e.target.value)}
              placeholder="Paste a finding ID"
            />
            <button type="button" className="btn btn-primary" onClick={() => applyFinding(findingId)}>
              Load activity
            </button>
          </div>
        </section>
      )}

      {subscription && findingId && (
        <ActivityTimeline
          findingId={findingId}
          subscriptionId={subscription}
        />
      )}
    </div>
  );
}
