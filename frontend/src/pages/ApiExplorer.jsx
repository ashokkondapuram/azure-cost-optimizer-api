import React, { useContext, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import SwaggerUI from 'swagger-ui-react';
import 'swagger-ui-react/swagger-ui.css';
import { KeyRound, Database, Layers } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import { PAGE_ICONS } from '../config/assetIcons';
import { fetchApiExplorerContext, fetchOpenApiSpec } from '../api/apiExplorer';
import { getStoredToken, hasActiveSession } from '../api/tokenStorage';
import { freshnessLabel, formatSyncTime } from '../utils/syncFreshness';
import { prepareExplorerSpec } from '../utils/openApiDefaults';
import { createAzureProxyInterceptor } from '../utils/azureProxy';

function maskToken(token) {
  if (!token || token.length < 12) return '—';
  return `••••${token.slice(-8)}`;
}

export default function ApiExplorer() {
  const { subscription } = useContext(AppCtx);
  const navigate = useNavigate();
  const sessionToken = getStoredToken();
  const sessionActive = hasActiveSession();

  useEffect(() => {
    if (!sessionActive) {
      const next = `${window.location.pathname}${window.location.search}`;
      const loginPath = next && next !== '/login'
        ? `/login?next=${encodeURIComponent(next)}`
        : '/login';
      navigate(loginPath, { replace: true });
    }
  }, [sessionActive, navigate]);

  const { data: context } = useQuery({
    queryKey: ['api-explorer-context'],
    queryFn: fetchApiExplorerContext,
    staleTime: 30_000,
  });

  const { data: openApiSpec, isLoading: specLoading, isError: specError } = useQuery({
    queryKey: ['openapi-spec'],
    queryFn: fetchOpenApiSpec,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const tokenCache = context?.azure_token_cache || {};
  const activeSubscriptionId = subscription || context?.subscription_id || null;
  const subscriptionMeta = context?.subscription || null;

  const proxyConfig = openApiSpec?.['x-proxy-config'];

  const specWithDefaults = useMemo(
    () => prepareExplorerSpec(openApiSpec, activeSubscriptionId),
    [openApiSpec, activeSubscriptionId],
  );

  const requestInterceptor = useMemo(
    () => createAzureProxyInterceptor(proxyConfig, {
      getSessionToken: getStoredToken,
      subscriptionId: activeSubscriptionId,
    }),
    [proxyConfig, activeSubscriptionId],
  );

  const onComplete = useMemo(() => (system) => {
    const token = getStoredToken();
    if (!token || !system?.authActions?.authorize) return;
    system.authActions.authorize({
      BearerAuth: {
        name: 'BearerAuth',
        schema: { type: 'http', scheme: 'bearer' },
        value: token,
      },
    });
  }, []);

  return (
    <div className="page-shell api-explorer-page">
      <PageHeader
        title="API explorer"
        iconKey={PAGE_ICONS.settings}
        subtitle="Azure management.azure.com endpoints (proxied with managed identity token)"
      />

      <PageHero
        variant="api-explorer-hero"
        eyebrow="Developer tools"
        title="Interactive API explorer"
        subtitle="Try Azure ARM endpoints through the app proxy with your session token."
        metrics={[
          {
            label: 'Session',
            value: sessionActive ? 'Active' : 'Sign in required',
            tone: sessionActive ? 'success' : 'warning',
          },
          {
            label: 'Azure token cache',
            value: tokenCache.cached ? freshnessLabel(tokenCache.freshness) : 'Empty',
            tone: tokenCache.cached ? 'success' : 'default',
          },
          {
            label: 'Subscription',
            value: subscriptionMeta?.display_name || activeSubscriptionId?.slice(0, 8) || 'None',
            tone: activeSubscriptionId ? 'default' : 'warning',
          },
        ]}
        actions={[
          { id: 'settings', label: 'Settings', href: '/settings' },
        ]}
      />

      <section className="page-section card api-explorer-auth">
        <div className="api-explorer-auth__grid">
          <div className="api-explorer-auth__item">
            <KeyRound size={18} aria-hidden />
            <div>
              <span className="api-explorer-auth__label">App session (JWT)</span>
              <span className={`api-explorer-auth__value${sessionActive ? ' api-explorer-auth__value--ok' : ''}`}>
                {sessionActive ? `Active · ${maskToken(sessionToken)}` : 'Sign in required'}
              </span>
              <span className="api-explorer-auth__hint">
                Try it out shows management.azure.com URLs; requests are proxied through this app.
              </span>
            </div>
          </div>
          <div className="api-explorer-auth__item">
            <Database size={18} aria-hidden />
            <div>
              <span className="api-explorer-auth__label">Azure token cache (PostgreSQL)</span>
              <span className="api-explorer-auth__value">
                {tokenCache.cached
                  ? freshnessLabel(tokenCache.freshness)
                  : 'Not cached'}
              </span>
              {tokenCache.expires_at && (
                <span className="api-explorer-auth__hint">
                  Expires {formatSyncTime(tokenCache.expires_at)}
                </span>
              )}
              <span className="api-explorer-auth__hint">
                Used server-side for Azure ARM calls — not sent from the browser.
              </span>
            </div>
          </div>
          <div className="api-explorer-auth__item">
            <Layers size={18} aria-hidden />
            <div>
              <span className="api-explorer-auth__label">Subscription (autofill)</span>
              <span className={`api-explorer-auth__value${activeSubscriptionId ? ' api-explorer-auth__value--ok' : ''}`}>
                {activeSubscriptionId
                  ? (subscriptionMeta?.display_name || activeSubscriptionId)
                  : 'No subscription available'}
              </span>
              {activeSubscriptionId && (
                <span className="api-explorer-auth__hint">
                  <code className="api-explorer-code">{activeSubscriptionId}</code>
                  {subscriptionMeta?.source === 'managed_identity' && ' · from managed identity'}
                  {subscriptionMeta?.source === 'default_subscription_id' && ' · from default setting'}
                  {subscription && ' · sidebar selection'}
                </span>
              )}
              <span className="api-explorer-auth__hint">
                Prefilled in ARM path and query parameters when required.
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="card api-explorer-swagger">
        {specLoading && <p className="api-explorer-auth__hint">Loading API schema…</p>}
        {specError && (
          <p className="api-explorer-auth__error">Could not load OpenAPI schema. Admin access required.</p>
        )}
        {specWithDefaults && (
          <SwaggerUI
            key={activeSubscriptionId || 'no-sub'}
            spec={specWithDefaults}
            docExpansion="none"
            defaultModelsExpandDepth={-1}
            displayOperationId={false}
            displayRequestDuration
            filter
            tryItOutEnabled
            persistAuthorization={false}
            requestInterceptor={requestInterceptor}
            onComplete={onComplete}
            operationsSorter="alpha"
          />
        )}
      </section>
    </div>
  );
}
