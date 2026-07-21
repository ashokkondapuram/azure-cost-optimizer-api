import React from 'react';
import { RefreshCw } from 'lucide-react';
import useSubscriptionLabel from '../../hooks/useSubscriptionLabel';
import PageHeader from '../PageHeader';
import { SubscriptionRequired, QueryErrorState } from '../QueryStates';
import { AdvSourceChips, AdvWarningsBanner } from './AdvUI';
import AdvancedToolHero from './AdvancedToolHero';

/** Subscription from sidebar context — shared by advanced tool pages. */
export function useAdvancedSubscription() {
  const { subscription, subscriptionLabel, subscriptionOptions } = useSubscriptionLabel();
  return { subscription, subscriptionLabel, subscriptionOptions };
}

/**
 * Shared chrome for API-backed advanced tool pages:
 * page shell, header, subscription bar, refresh, error state.
 */
export default function AdvancedToolLayout({
  title,
  subtitle,
  pageScope,
  subtitleSuffix = '',
  iconKey,
  iconRoute,
  children,
  onRefresh,
  loading = false,
  error = null,
  errorTitle = 'Failed to load data',
  headerActions,
  accent,
  metaItems,
  sources,
  sourceLabels,
  warnings,
  onDismissWarnings,
  hideWarnings = false,
  hero,
  hasHeroBand = false,
}) {
  const { subscription, subscriptionLabel } = useAdvancedSubscription();
  const hasHero = Boolean((hero && accent) || hasHeroBand);
  const showBuiltInHero = Boolean(hero && accent);

  return (
    <div className={`page-shell adv-page${accent ? ` adv-page--${accent}` : ''}${hasHero ? ' adv-page--has-hero' : ''}`}>
      <PageHeader
        title={title}
        subtitle={subtitle}
        pageScope={pageScope}
        subtitleSuffix={subtitleSuffix}
        iconKey={iconKey}
        iconRoute={iconRoute}
      >
        {headerActions}
        {subscription && onRefresh && (
          <button
            type="button"
            className="btn btn-secondary btn-sm adv-refresh-btn"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'adv-spin' : ''} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      </PageHeader>

      {subscription && (
        <div className="adv-context-strip">
          <div className="adv-subscription-bar">
            <span className="adv-subscription-bar__label">Subscription</span>
            <span className="adv-subscription-bar__value">{subscriptionLabel}</span>
          </div>
          {metaItems?.length > 0 && (
            <div className="adv-meta-bar adv-meta-bar--inline">
              {metaItems.map((item) => (
                <span key={item} className="adv-meta-bar__item">{item}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {!subscription && <SubscriptionRequired />}

      {subscription && error && (
        <QueryErrorState error={error} onRetry={onRefresh} title={errorTitle} />
      )}

      {subscription && !error && (
        <div className="adv-page-content adv-section-enter">
          {showBuiltInHero && (
            <AdvancedToolHero
              accent={accent}
              eyebrow={hero.eyebrow}
              subtitle={hero.subtitle ?? subscriptionLabel}
              scopeNote={hero.scopeNote}
              metrics={hero.metrics}
              actions={hero.actions}
              footer={hero.footer}
              isLoading={hero.isLoading ?? (loading && !hero.metrics?.length)}
              skeletonMetrics={hero.skeletonMetrics ?? 4}
            />
          )}
          {!hideWarnings && warnings?.length > 0 && (
            <AdvWarningsBanner warnings={warnings} onDismiss={onDismissWarnings} />
          )}
          {(sources || sourceLabels) && (
            <AdvSourceChips sources={sources} labels={sourceLabels} />
          )}
          {children}
        </div>
      )}
    </div>
  );
}
