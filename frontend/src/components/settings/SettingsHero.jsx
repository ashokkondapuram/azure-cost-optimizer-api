import React from 'react';
import { RefreshCw } from 'lucide-react';
import PageHero from '../layout/PageHero';
import { formatPageSubtitle } from '../../utils/subscriptionDisplay';

export default function SettingsHero({
  runtimeStatus,
  subscriptionLabel,
  onReload,
  isReloading,
}) {
  const deployment = runtimeStatus?.deployment;
  const database = runtimeStatus?.database;
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
  ];

  const subtitle = formatPageSubtitle('settings', subscriptionLabel);

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
    </PageHero>
  );
}
