import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Save, RefreshCw, Cloud, Database, Settings2, Boxes, CheckCircle2, AlertTriangle,
  Trash2, Users, Sparkles, Activity, LayoutGrid,
} from 'lucide-react';
import { AppCtx } from '../App';
import Toggle from '../components/Toggle';
import { LoadingState, QueryErrorState } from '../components/QueryStates';
import { getErrorMessage } from '../api/errors';
import { toDisplayText } from '../utils/formatDisplay';
import {
  fetchAllSettings,
  fetchSettingsStatus,
  saveAzureSettings,
  saveDatabaseSettings,
  saveApplicationSettings,
  saveKubernetesSettings,
  saveAiSettings,
  testAzureSettings,
  testDatabaseSettings,
  testAiSettings,
  applyDatabaseSettings,
  reloadSettings,
} from '../api/settings';
import { clearDatabaseData } from '../api/azure';
import UsersPanel from '../components/settings/UsersPanel';
import NavAccessPanel from '../components/settings/NavAccessPanel';
import DataFreshnessPanel from '../components/settings/DataFreshnessPanel';
import SettingsHero from '../components/settings/SettingsHero';
import { useAuth } from '../context/AuthContext';

const TAB_SECTIONS = [
  {
    id: 'access',
    label: 'Access',
    tabs: [
      { id: 'users', label: 'Users', Icon: Users },
      { id: 'nav-access', label: 'Sidebar access', Icon: LayoutGrid, superuserOnly: true },
    ],
  },
  {
    id: 'connections',
    label: 'Connections',
    tabs: [
      { id: 'azure', label: 'Azure connection', Icon: Cloud },
      { id: 'database', label: 'Database', Icon: Database },
    ],
  },
  {
    id: 'platform',
    label: 'Platform',
    tabs: [
      { id: 'application', label: 'Application', Icon: Settings2 },
      { id: 'kubernetes', label: 'Kubernetes agent', Icon: Boxes },
    ],
  },
  {
    id: 'system',
    label: 'System',
    tabs: [
      { id: 'runtime', label: 'Runtime status', Icon: Activity },
      { id: 'ai', label: 'AI connection', Icon: Sparkles },
    ],
  },
  {
    id: 'maintenance',
    label: 'Maintenance',
    tabs: [{ id: 'data', label: 'Data management', Icon: Trash2 }],
  },
];

const TAB_META = {
  users: {
    title: 'Users',
    description: 'Manage accounts, roles, and access to this application.',
  },
  'nav-access': {
    title: 'Sidebar access',
    description: 'Control which sidebar panels admins and viewers can see.',
  },
  azure: {
    title: 'Azure connection',
    description: 'Authentication and credentials used to sync Azure inventory and costs.',
  },
  database: {
    title: 'Database',
    description: 'PostgreSQL connection for inventory, costs, and optimization findings.',
  },
  application: {
    title: 'Application',
    description: 'CORS, logging, timeouts, and general runtime behavior.',
  },
  kubernetes: {
    title: 'Kubernetes agent',
    description: 'Token and settings for the in-cluster utilization agent.',
  },
  runtime: {
    title: 'Runtime status',
    description: 'Deployment, database, and platform health at a glance.',
  },
  ai: {
    title: 'AI connection',
    description: 'Azure OpenAI settings for AI-enriched recommendations after analysis.',
  },
  data: {
    title: 'Data management',
    description: 'Clear synced data and refresh inventory from Azure.',
  },
};

function SourceBadge({ source }) {
  const cls =
    source === 'database' ? 'badge badge-info'
      : source === 'environment' ? 'badge badge-medium'
      : 'badge';
  return <span className={`${cls} source-badge`}>{source}</span>;
}

function FieldRow({ label, source, hint, children }) {
  return (
    <div className="setting-field">
      <div className="setting-field__label">
        {label}
        {source && <SourceBadge source={source} />}
      </div>
      {children}
      {hint && <div className="setting-field__hint">{hint}</div>}
    </div>
  );
}

function RuntimeStatusCompact({ status }) {
  if (!status) return null;
  const { database, cors, deployment, azure, ai } = status;
  const onAppService = deployment?.is_app_service;
  const corsOrigins = cors?.active_origins || [];
  const corsTitle = corsOrigins.join(', ') || undefined;

  const items = [
    {
      key: 'host',
      label: 'Host',
      value: onAppService ? (deployment?.site_name || 'App Service') : 'Self-hosted',
      tone: onAppService ? 'ok' : 'muted',
    },
    {
      key: 'auth',
      label: 'Azure auth',
      value: (azure?.auth_mode || 'managed identity').replace(/_/g, ' '),
      tone: 'ok',
    },
    {
      key: 'database',
      label: 'Database',
      value: database?.active_url ? 'Connected' : 'Not configured',
      tone: database?.active_url ? 'ok' : 'warn',
    },
    {
      key: 'cors',
      label: 'CORS',
      value: corsOrigins.length
        ? `${corsOrigins.length} origin${corsOrigins.length === 1 ? '' : 's'}`
        : 'None',
      tone: corsOrigins.length ? 'ok' : 'muted',
      title: corsTitle,
    },
    {
      key: 'ai',
      label: 'AI analysis',
      value: ai?.configured
        ? (ai.deployment || 'Configured')
        : ai?.enabled
          ? 'Incomplete'
          : 'Off',
      tone: ai?.configured ? 'ok' : ai?.enabled ? 'warn' : 'muted',
    },
  ];

  return (
    <div className="settings-runtime-compact">
      <div className="settings-runtime-compact__grid">
        {items.map((item) => (
          <div
            key={item.key}
            className={`settings-runtime-compact__chip settings-runtime-compact__chip--${item.tone}`}
            title={item.title}
          >
            <span className="settings-runtime-compact__chip-label">{item.label}</span>
            <span className="settings-runtime-compact__chip-value">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusBanner({ type, message }) {
  if (!message) return null;
  const text = toDisplayText(message);
  if (text === '—') return null;
  const isSuccess = type === 'success';
  return (
    <div className={`alert ${isSuccess ? 'alert--success' : 'alert--danger'}`} role="status">
      {isSuccess ? <CheckCircle2 size={16} className="alert__icon" /> : <AlertTriangle size={16} className="alert__icon" />}
      <span>{text}</span>
    </div>
  );
}

function AuthMethodPicker({ value, onChange, isAppService }) {
  const options = [
    {
      value: 'managed_identity',
      label: 'Managed identity',
      description: isAppService
        ? 'Recommended for Azure Web App — uses the app identity'
        : 'System- or user-assigned identity on Azure',
      recommended: true,
    },
    {
      value: 'service_principal',
      label: 'App credentials',
      description: 'Tenant ID, client ID, and client secret',
    },
    {
      value: 'default_credential',
      label: 'Local dev',
      description: 'Azure CLI (`az login`) or default chain',
    },
  ];

  return (
    <div className="auth-method-picker" role="radiogroup" aria-label="Azure authentication method">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          className={`auth-method-picker__option${value === opt.value ? ' auth-method-picker__option--active' : ''}`}
          onClick={() => onChange(opt.value)}
        >
          <span className="auth-method-picker__label">
            {opt.label}
            {opt.recommended && isAppService && (
              <span className="badge badge-low" style={{ marginLeft: 6 }}>Recommended</span>
            )}
          </span>
          <span className="auth-method-picker__desc">{opt.description}</span>
        </button>
      ))}
    </div>
  );
}

function CredentialFields({ data, onChange, secretKey, secretLabel, secretPlaceholder }) {
  const secretSet = data[`${secretKey}_set`];
  return (
    <>
      <FieldRow label="Tenant ID" source={data.tenant_id_source}>
        <input
          type="text"
          value={data.tenant_id || ''}
          onChange={(e) => onChange('tenant_id', e.target.value)}
          placeholder="00000000-0000-0000-0000-000000000000"
          autoComplete="off"
        />
      </FieldRow>
      <FieldRow label="Client ID" source={data.client_id_source}>
        <input
          type="text"
          value={data.client_id || ''}
          onChange={(e) => onChange('client_id', e.target.value)}
          placeholder="App registration client ID"
          autoComplete="off"
        />
      </FieldRow>
      <FieldRow
        label={secretLabel}
        source={data[`${secretKey}_source`]}
        hint={secretSet ? 'A value is stored. Leave blank to keep it.' : 'Required.'}
      >
        <input
          type="password"
          value={data[secretKey] || ''}
          onChange={(e) => onChange(secretKey, e.target.value)}
          placeholder={secretSet ? '••••••••' : secretPlaceholder}
          autoComplete="new-password"
        />
      </FieldRow>
    </>
  );
}

function AzureForm({ data, onChange, isAppService }) {
  const mode = data.auth_mode || (isAppService ? 'managed_identity' : 'service_principal');

  return (
    <div className="settings-form-stack">
      <AuthMethodPicker
        value={mode}
        onChange={(next) => onChange('auth_mode', next)}
        isAppService={isAppService}
      />

      {mode === 'managed_identity' && (
        <>
          {isAppService && (
            <div className="alert alert--success">
              <CheckCircle2 size={16} className="alert__icon" />
              <span>
                This Web App will call Azure APIs as its <strong>managed identity</strong>.
                Enable identity under <em>Identity</em> in the Azure portal, then assign RBAC roles
                (Reader, Cost Management Reader) on your subscription.
              </span>
            </div>
          )}
          <div className="settings-grid">
            <FieldRow
              label="User-assigned identity client ID"
              source={data.client_id_source}
              hint="Leave blank for system-assigned identity. Set only if you enabled a user-assigned identity on the Web App."
            >
            <input
              type="text"
              value={data.client_id || ''}
              onChange={(e) => onChange('client_id', e.target.value)}
              placeholder="Optional user-assigned identity client ID"
              autoComplete="off"
            />
          </FieldRow>
          </div>
        </>
      )}

      {mode === 'service_principal' && (
        <div className="settings-grid">
          <CredentialFields
            data={data}
            onChange={onChange}
            secretKey="client_secret"
            secretLabel="Client secret"
            secretPlaceholder="App registration client secret"
          />
        </div>
      )}

      {mode === 'default_credential' && (
        <div className="setting-field">
          <div className="setting-field__hint">
            No credentials are stored. Run <code>az login</code> locally or rely on the default Azure credential chain.
          </div>
        </div>
      )}

      <div className="settings-grid">
        <FieldRow label="Default subscription ID" source={data.default_subscription_id_source}>
          <input
            type="text"
            value={data.default_subscription_id || ''}
            onChange={(e) => onChange('default_subscription_id', e.target.value)}
            placeholder="Optional default subscription"
            autoComplete="off"
          />
        </FieldRow>
      </div>
    </div>
  );
}

function parseDatabaseUrl(raw) {
  if (!raw?.trim()) return null;
  try {
    const normalized = raw.trim().replace(/^postgres(ql)?:\/\//i, 'http://');
    const url = new URL(normalized);
    return {
      dialect: 'postgresql',
      host: url.hostname,
      port: url.port ? Number(url.port) : 5432,
      database: url.pathname.replace(/^\//, ''),
      username: decodeURIComponent(url.username || ''),
      password: decodeURIComponent(url.password || ''),
    };
  } catch {
    return null;
  }
}

function DatabaseForm({ data, onChange, isAppService }) {
  const [connectionString, setConnectionString] = useState('');

  const applyConnectionString = () => {
    const parsed = parseDatabaseUrl(connectionString);
    if (!parsed) return;
    Object.entries(parsed).forEach(([key, value]) => onChange(key, value));
  };

  return (
    <div className="settings-form-stack">
      {isAppService && (
        <div className="alert alert--success">
          <CheckCircle2 size={16} className="alert__icon" />
          <span>
            On Azure Web App, set <strong>DATABASE_URL</strong> or a <strong>PostgreSQL connection string</strong> in
            App Service configuration. The app reads it at startup — you do not need to store DB credentials here unless
            you want to override the connection string.
          </span>
        </div>
      )}
      <div className="setting-field">
        <div className="setting-field__label">Connection string (optional)</div>
        <input
          type="text"
          value={connectionString}
          onChange={(e) => setConnectionString(e.target.value)}
          placeholder="postgresql://user:password@host:5432/azure_cost_db"
          autoComplete="off"
        />
        <div className="setting-field__hint">
          Paste a PostgreSQL URL to fill the fields below, or enter each field manually.
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          style={{ marginTop: '0.5rem' }}
          onClick={applyConnectionString}
          disabled={!connectionString.trim()}
        >
          Parse connection string
        </button>
      </div>

      <div className="settings-grid">
        <FieldRow label="Dialect" source={data.dialect_source}>
          <select value={data.dialect || 'postgresql'} onChange={(e) => onChange('dialect', e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="sqlite">SQLite</option>
          </select>
        </FieldRow>
        <FieldRow label="Host" source={data.host_source}>
          <input type="text" value={data.host || ''} onChange={(e) => onChange('host', e.target.value)} placeholder="localhost" autoComplete="off" />
        </FieldRow>
        <FieldRow label="Port" source={data.port_source}>
          <input type="number" value={data.port ?? 5432} onChange={(e) => onChange('port', Number(e.target.value))} />
        </FieldRow>
        <FieldRow label="Database name" source={data.database_source}>
          <input type="text" value={data.database || ''} onChange={(e) => onChange('database', e.target.value)} placeholder="azure_cost_db" autoComplete="off" />
        </FieldRow>
        <FieldRow label="Username" source={data.username_source}>
          <input type="text" value={data.username || ''} onChange={(e) => onChange('username', e.target.value)} autoComplete="off" />
        </FieldRow>
        <FieldRow
          label="Password"
          source={data.password_source}
          hint={data.password_set ? 'A password is stored. Leave blank to keep the current value.' : undefined}
        >
          <input type="password" value={data.password || ''} onChange={(e) => onChange('password', e.target.value)} autoComplete="new-password" />
        </FieldRow>
        <FieldRow label="SSL mode" source={data.ssl_mode_source}>
          <select value={data.ssl_mode || 'prefer'} onChange={(e) => onChange('ssl_mode', e.target.value)}>
            <option value="disable">Disable</option>
            <option value="prefer">Prefer</option>
            <option value="require">Require</option>
          </select>
        </FieldRow>
      </div>
    </div>
  );
}

function ApplicationForm({ data, onChange }) {
  return (
    <div className="settings-grid">
      <FieldRow label="Environment" source={data.app_env_source}>
        <select value={data.app_env || 'development'} onChange={(e) => onChange('app_env', e.target.value)}>
          <option value="development">Development</option>
          <option value="staging">Staging</option>
          <option value="production">Production</option>
        </select>
      </FieldRow>
      <FieldRow label="CORS allowed origins" source={data.cors_allowed_origins_source} hint="Comma-separated URLs. Restart required after save.">
        <input type="text" value={data.cors_allowed_origins || ''} onChange={(e) => onChange('cors_allowed_origins', e.target.value)} />
      </FieldRow>
      <FieldRow label="Request timeout (seconds)" source={data.request_timeout_seconds_source}>
        <input type="number" value={data.request_timeout_seconds ?? 60} onChange={(e) => onChange('request_timeout_seconds', Number(e.target.value))} />
      </FieldRow>
      <FieldRow label="Log level" source={data.log_level_source}>
        <select value={data.log_level || 'INFO'} onChange={(e) => onChange('log_level', e.target.value)}>
          {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((level) => (
            <option key={level} value={level}>{level}</option>
          ))}
        </select>
      </FieldRow>
    </div>
  );
}

function KubernetesForm({ data, onChange }) {
  return (
    <div className="settings-grid">
      <FieldRow
        label="Agent API token"
        source={data.agent_token_source}
        hint={data.agent_token_set ? 'A token is stored. Leave blank to keep the current value.' : 'Used by the in-cluster utilization agent.'}
      >
        <input type="password" value={data.agent_token || ''} onChange={(e) => onChange('agent_token', e.target.value)} autoComplete="new-password" />
      </FieldRow>
      <FieldRow label="Require agent token" source={data.require_agent_token_source}>
        <Toggle checked={!!data.require_agent_token} onChange={(checked) => onChange('require_agent_token', checked)} label="Require token on K8s endpoints" />
      </FieldRow>
    </div>
  );
}

function AiForm({ data, onChange }) {
  return (
    <div className="settings-grid">
      <FieldRow label="AI recommendations" source={data.ai_enabled_source} hint="AI recommendations run on every analysis when Azure OpenAI is configured. Rule engine supplies evidence; AI writes the recommendation users see.">
        <Toggle checked={data.ai_enabled !== false} onChange={(checked) => onChange('ai_enabled', checked)} label="Use AI recommendations" />
      </FieldRow>
      <FieldRow label="Authentication" source={data.ai_auth_mode_source} hint="Use Azure AD when API keys are disabled on the OpenAI resource. Without an API key, Azure AD is used automatically.">
        <select value={data.ai_auth_mode || 'api_key'} onChange={(e) => onChange('ai_auth_mode', e.target.value)}>
          <option value="api_key">API key</option>
          <option value="azure_ad">Azure AD (managed identity or service principal)</option>
        </select>
      </FieldRow>
      <FieldRow label="OpenAI endpoint" source={data.openai_endpoint_source} hint="Azure OpenAI resource endpoint, e.g. https://your-resource.openai.azure.com">
        <input type="url" value={data.openai_endpoint || ''} onChange={(e) => onChange('openai_endpoint', e.target.value)} placeholder="https://your-resource.openai.azure.com" autoComplete="off" />
      </FieldRow>
      <FieldRow label="Deployment name" source={data.openai_deployment_source}>
        <input type="text" value={data.openai_deployment || ''} onChange={(e) => onChange('openai_deployment', e.target.value)} placeholder="gpt-4o-mini" autoComplete="off" />
      </FieldRow>
      <FieldRow label="API version" source={data.openai_api_version_source}>
        <input type="text" value={data.openai_api_version || '2024-08-01-preview'} onChange={(e) => onChange('openai_api_version', e.target.value)} autoComplete="off" />
      </FieldRow>
      <FieldRow
        label="API key"
        source={data.openai_key_source}
        hint={data.openai_key_set ? 'A key is stored. Leave blank to keep the current value.' : 'Required only when authentication is API key.'}
      >
        <input type="password" value={data.openai_key || ''} onChange={(e) => onChange('openai_key', e.target.value)} autoComplete="new-password" />
      </FieldRow>
      <FieldRow label="Enrich all findings" source={data.ai_enrich_all_findings_source} hint="When off, only the highest-savings findings are sent to the model.">
        <Toggle checked={!!data.ai_enrich_all_findings} onChange={(checked) => onChange('ai_enrich_all_findings', checked)} label="Send every finding to AI" />
      </FieldRow>
      <FieldRow label="Max findings per run" source={data.ai_max_findings_per_run_source}>
        <input type="number" min={1} max={200} value={data.ai_max_findings_per_run ?? 200} onChange={(e) => onChange('ai_max_findings_per_run', Number(e.target.value))} />
      </FieldRow>
      <FieldRow label="Batch size" source={data.ai_batch_size_source} hint="Findings per AI request. Smaller batches use fewer tokens per call and reduce truncation risk.">
        <input type="number" min={1} max={25} value={data.ai_batch_size ?? 10} onChange={(e) => onChange('ai_batch_size', Number(e.target.value))} />
      </FieldRow>
    </div>
  );
}

function DataManagementPanel({ subscription, subscriptionLabel }) {
  const qc = useQueryClient();
  const { reloadSubscriptions } = useContext(AppCtx);
  const [scope, setScope] = useState('subscription');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [resultMsg, setResultMsg] = useState({ type: '', text: '' });

  const clearMut = useMutation({
    mutationFn: () => clearDatabaseData(
      scope === 'subscription' && subscription
        ? { subscription_id: subscription }
        : {},
    ),
    onSuccess: (res) => {
      const deleted = res.deleted || {};
      const total = Object.values(deleted).reduce((sum, n) => sum + (n || 0), 0);
      setResultMsg({
        type: 'success',
        text: `Cleared ${total.toLocaleString()} rows. Run Sync from Azure to reload inventory.`,
      });
      setConfirmOpen(false);
      setConfirmText('');
      qc.invalidateQueries();
      reloadSubscriptions?.();
    },
    onError: (err) => {
      setResultMsg({ type: 'error', text: getErrorMessage(err, 'Could not clear database.') });
      setConfirmOpen(false);
    },
  });

  const canConfirm = confirmText.trim().toUpperCase() === 'CLEAR';
  const scopeLabel = scope === 'subscription' && subscription
    ? `subscription ${subscriptionLabel || subscription}`
    : 'all subscriptions';

  return (
    <div className="settings-form-stack">
      <div className="alert alert--warning">
        <AlertTriangle size={16} className="alert__icon" />
        <span>
          This removes synced Azure inventory, costs, budgets, optimization findings, and run history
          from the local database. User accounts, engine rules, and system settings are kept.
        </span>
      </div>

      <div className="setting-field">
        <div className="setting-field__label">Clear scope</div>
        <div className="auth-method-picker" role="radiogroup" aria-label="Clear scope">
          <button
            type="button"
            role="radio"
            aria-checked={scope === 'subscription'}
            className={`auth-method-picker__option${scope === 'subscription' ? ' auth-method-picker__option--active' : ''}`}
            onClick={() => setScope('subscription')}
            disabled={!subscription}
          >
            <span className="auth-method-picker__label">Current subscription</span>
            <span className="auth-method-picker__desc">
              {subscription
                ? `Clear data for ${subscriptionLabel || subscription}`
                : 'Select a subscription in the sidebar first'}
            </span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={scope === 'all'}
            className={`auth-method-picker__option${scope === 'all' ? ' auth-method-picker__option--active' : ''}`}
            onClick={() => setScope('all')}
          >
            <span className="auth-method-picker__label">All subscriptions</span>
            <span className="auth-method-picker__desc">Clear all synced inventory, costs, and findings</span>
          </button>
        </div>
      </div>

      <div className="setting-field">
        <div className="setting-field__label">Removed</div>
        <ul className="settings-list-hint">
          <li>Resource inventory and per-resource costs</li>
          <li>Cost snapshots and budgets</li>
          <li>Optimization findings, runs, and batch jobs</li>
          <li>Subscription cache</li>
        </ul>
      </div>

      <div className="setting-field">
        <div className="setting-field__label">Preserved</div>
        <ul className="settings-list-hint">
          <li>User accounts and login settings</li>
          <li>Engine rule profiles and thresholds</li>
          <li>Azure connection and application settings</li>
        </ul>
      </div>

      <StatusBanner type={resultMsg.type} message={resultMsg.text} />

      <div className="settings-panel__actions">
        <button
          type="button"
          className="btn btn-danger"
          disabled={scope === 'subscription' && !subscription}
          onClick={() => { setConfirmOpen(true); setConfirmText(''); setResultMsg({ type: '', text: '' }); }}
        >
          <Trash2 size={14} /> Clear database
        </button>
      </div>

      {confirmOpen && (
        <div className="modal-overlay" onClick={() => !clearMut.isPending && setConfirmOpen(false)} role="presentation">
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="clear-db-title"
          >
            <h2 id="clear-db-title" className="modal-title">Clear database?</h2>
            <p style={{ margin: '0 0 1rem', color: 'var(--text2)', lineHeight: 1.5 }}>
              You are about to clear synced data for <strong>{scopeLabel}</strong>.
              This cannot be undone. Type <strong>CLEAR</strong> to confirm.
            </p>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type CLEAR"
              autoComplete="off"
              aria-label="Confirmation text"
            />
            <div className="settings-panel__actions" style={{ marginTop: '1rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmOpen(false)}
                disabled={clearMut.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => clearMut.mutate()}
                disabled={!canConfirm || clearMut.isPending}
              >
                {clearMut.isPending ? <RefreshCw size={14} className="spin" /> : <Trash2 size={14} />}
                Confirm clear
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const FORM_MAP = {
  azure: AzureForm,
  database: DatabaseForm,
  application: ApplicationForm,
  kubernetes: KubernetesForm,
  ai: AiForm,
};

const SAVE_MAP = {
  azure: saveAzureSettings,
  database: saveDatabaseSettings,
  application: saveApplicationSettings,
  kubernetes: saveKubernetesSettings,
  ai: saveAiSettings,
};

const TEST_MAP = {
  azure: testAzureSettings,
  database: testDatabaseSettings,
  ai: testAiSettings,
};

function stripMeta(data) {
  const out = {};
  Object.entries(data || {}).forEach(([key, value]) => {
    if (key.endsWith('_source') || key.endsWith('_set') || key === 'updated_at' || key === 'stored_in_database') {
      return;
    }
    out[key] = value;
  });
  return out;
}

export default function Settings() {
  const { isSuperuser } = useAuth();
  const tabSections = useMemo(
    () => TAB_SECTIONS.map((section) => ({
      ...section,
      tabs: section.tabs.filter((t) => !t.superuserOnly || isSuperuser),
    })),
    [isSuperuser],
  );
  const qc = useQueryClient();
  const { subscription, subscriptionOptions } = useContext(AppCtx);
  const [tab, setTab] = useState('users');
  const [drafts, setDrafts] = useState({});
  const [saveMsg, setSaveMsg] = useState('');
  const [testMsg, setTestMsg] = useState({ type: '', text: '' });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['system-settings'],
    queryFn: fetchAllSettings,
  });

  const { data: runtimeStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['settings-status'],
    queryFn: fetchSettingsStatus,
  });

  useEffect(() => {
    if (!data) return;
    setDrafts({
      azure: stripMeta(data.azure),
      database: stripMeta(data.database),
      application: stripMeta(data.application),
      kubernetes: stripMeta(data.kubernetes),
      ai: stripMeta(data.ai),
    });
  }, [data]);

  const saveMut = useMutation({
    mutationFn: (payload) => SAVE_MAP[tab](payload),
    onSuccess: (res) => {
      setSaveMsg(res.message || 'Settings saved.');
      setTestMsg({ type: '', text: '' });
      qc.invalidateQueries({ queryKey: ['system-settings'] });
      refetchStatus();
    },
    onError: (err) => setSaveMsg(getErrorMessage(err, 'Could not save settings.')),
  });

  const applyDbMut = useMutation({
    mutationFn: applyDatabaseSettings,
    onSuccess: (res) => {
      setSaveMsg(res.message || 'Database connection applied.');
      refetchStatus();
    },
    onError: (err) => setSaveMsg(getErrorMessage(err, 'Could not apply database connection.')),
  });

  const testMut = useMutation({
    mutationFn: () => TEST_MAP[tab](drafts[tab] || {}),
    onSuccess: (res) => setTestMsg({ type: 'success', text: res.message }),
    onError: (err) => setTestMsg({ type: 'error', text: getErrorMessage(err, 'Connection test failed.') }),
  });

  const reloadMut = useMutation({
    mutationFn: reloadSettings,
    onSuccess: (res) => setSaveMsg(res.message),
    onError: (err) => setSaveMsg(getErrorMessage(err, 'Could not reload settings.')),
  });

  const onChange = (field, value) => {
    setDrafts((prev) => ({
      ...prev,
      [tab]: { ...prev[tab], [field]: value },
    }));
    setSaveMsg('');
    setTestMsg({ type: '', text: '' });
  };

  const ActiveForm = FORM_MAP[tab];
  const tabData = data?.[tab] || {};
  const draft = drafts[tab] || {};
  const isAppService = runtimeStatus?.deployment?.is_app_service;
  const subLabel = subscriptionOptions?.find((s) => s.subscriptionId === subscription)?.displayName;

  const activeTabMeta = TAB_META[tab] || { title: 'Settings', description: '' };

  return (
    <div className="settings-page page-shell">
      <SettingsHero
        runtimeStatus={runtimeStatus}
        subscriptionLabel={subLabel}
        onReload={() => reloadMut.mutate()}
        isReloading={reloadMut.isPending}
      />

      {subscription && (
        <DataFreshnessPanel subscription={subscription} subscriptionLabel={subLabel} />
      )}

      {isLoading && <LoadingState message="Loading settings…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}

      {!isLoading && !isError && (
        <div className="settings-layout">
          <nav className="settings-sidebar card" aria-label="Settings categories">
            {tabSections.map((section) => (
              <div key={section.id} className="settings-sidebar__section">
                <div className="settings-sidebar__heading">{section.label}</div>
                {section.tabs.map(({ id, label, Icon }) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={tab === id}
                    className={`settings-sidebar__tab${tab === id ? ' settings-sidebar__tab--active' : ''}`}
                    onClick={() => { setTab(id); setSaveMsg(''); setTestMsg({ type: '', text: '' }); }}
                  >
                    <Icon size={16} aria-hidden />
                    <span>{label}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <div className="settings-main">
            <header className="settings-section-header">
              <h2 className="settings-section-header__title">{activeTabMeta.title}</h2>
              <p className="settings-section-header__desc">{activeTabMeta.description}</p>
            </header>

            <div className="card settings-panel">
              {tab === 'runtime' ? (
                <RuntimeStatusCompact status={runtimeStatus} />
              ) : tab === 'data' ? (
                <DataManagementPanel
                  subscription={subscription}
                  subscriptionLabel={subLabel}
                />
              ) : tab === 'users' ? (
                <UsersPanel />
              ) : tab === 'nav-access' ? (
                <NavAccessPanel />
              ) : (
                <>
                  <ActiveForm
                    data={{ ...tabData, ...draft }}
                    onChange={onChange}
                    isAppService={isAppService}
                  />

                  <StatusBanner type={testMsg.type} message={testMsg.text} />
                  {saveMsg && (
                    <StatusBanner
                      type={/saved|applied|active immediately|reloaded|Already using/i.test(saveMsg) ? 'success' : 'error'}
                      message={saveMsg}
                    />
                  )}

                  <div className="settings-panel__actions">
                    {TEST_MAP[tab] && (
                      <button type="button" className="btn btn-secondary" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
                        <RefreshCw size={14} className={testMut.isPending ? 'spin' : ''} /> Test connection
                      </button>
                    )}
                    {tab === 'database' && (
                      <button type="button" className="btn btn-secondary" onClick={() => applyDbMut.mutate()} disabled={applyDbMut.isPending}>
                        <RefreshCw size={14} className={applyDbMut.isPending ? 'spin' : ''} /> Apply connection
                      </button>
                    )}
                    <button type="button" className="btn btn-primary" onClick={() => saveMut.mutate(draft)} disabled={saveMut.isPending}>
                      <Save size={14} /> Save to database
                    </button>
                  </div>

                  {tabData.updated_at && (
                    <p className="settings-panel__meta">
                      Last saved: {new Date(tabData.updated_at).toLocaleString()}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
