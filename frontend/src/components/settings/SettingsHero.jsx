import React from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import PageHero from '../layout/PageHero';
import { toDisplayText } from '../../utils/formatDisplay';

export default function SettingsHero({
  runtimeStatus,
  subscriptionLabel,
  onReload,
  isReloading,
}) {
  const deployment = runtimeStatus?.deployment;
  const database = runtimeStatus?.database;
  const ai = runtimeStatus?.ai;
  const onAppService = deployment?.is_app_service;

  const metrics = [
    {
      label: 'Deployment',
      value: onAppService ? 'Azure Web App' : 'Self-hosted',
      tone: onAppService ? 'success' : 'default',
      sub: deployment?.site_name || undefined,
    },
    {
      label: 'Database',
      value: database?.active_url ? 'Connected' : 'Not configured',
      tone: database?.active_url ? 'success' : 'warning',
    },
    {
      label: 'AI analysis',
      value: ai?.configured ? 'Configured' : ai?.enabled ? 'Incomplete' : 'Off',
      tone: ai?.configured ? 'success' : ai?.enabled ? 'warning' : 'default',
      sub: ai?.deployment || undefined,
    },
  ];

  const subtitle = subscriptionLabel
    ? `${toDisplayText(subscriptionLabel)} · Azure, database, and platform configuration`
    : 'Azure, database, and platform configuration';

  return (
    <PageHero
      variant="settings-hero"
      eyebrow="Administration"
      title="Settings"
      subtitle={subtitle}
      metrics={metrics}
      actions={[
        { id: 'api', label: 'API explorer', href: '/admin/api-explorer' },
      ]}
    >
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={onReload}
        disabled={isReloading}
      >
        <RefreshCw size={14} className={isReloading ? 'spin' : ''} />
        Reload credentials
      </button>
      <Link to="/admin/optimization" className="btn btn-ghost btn-sm">Sync center</Link>
    </PageHero>
  );
}
