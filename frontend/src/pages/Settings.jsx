import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Save, RefreshCw, Cloud, Database, Settings2, Boxes, CheckCircle2, AlertTriangle,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import Toggle from '../components/Toggle';
import { LoadingState, QueryErrorState } from '../components/QueryStates';
import { getErrorMessage } from '../api/errors';
import {
  fetchAllSettings,
  fetchSettingsStatus,
  saveAzureSettings,
  saveDatabaseSettings,
  saveApplicationSettings,
  saveKubernetesSettings,
  testAzureSettings,
  testDatabaseSettings,
  applyDatabaseSettings,
  reloadSettings,
} from '../api/settings';
import { PAGE_ICONS } from '../config/assetIcons';

const TABS = [
  { id: 'azure', label: 'Azure connection', Icon: Cloud },
  { id: 'database', label: 'Database', Icon: Database },
  { id: 'application', label: 'Application', Icon: Settings2 },
  { id: 'kubernetes', label: 'Kubernetes agent', Icon: Boxes },
];

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

function RuntimeStatus({ status }) {
  if (!status) return null;
  const { database, cors, encryption, deployment, azure } = status;
  const onAppService = deployment?.is_app_service;

  return (
    <div className="settings-runtime card" style={{ marginBottom: '1rem', padding: '1rem 1.1rem' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.65rem', fontSize: '0.88rem' }}>Runtime status</div>
      {onAppService && (
        <div className="alert alert--success" style={{ marginBottom: '0.85rem' }}>
          <CheckCircle2 size={16} className="alert__icon" />
          <span>
            Running on Azure Web App <strong>{deployment.site_name}</strong>.
            Azure auth: <strong>{azure?.auth_mode || 'managed_identity'}</strong>.
            {deployment.managed_identity_available
              ? ' Managed identity endpoint detected.'
              : ' Enable managed identity on the Web App.'}
          </span>
        </div>
      )}
      <div className="settings-runtime__grid">
        <div>
          <div className="settings-runtime__label">Database</div>
          <div className="settings-runtime__value">Active: {database.active_url}</div>
          <div className="settings-runtime__hint">{database.note}</div>
        </div>
        <div>
          <div className="settings-runtime__label">CORS</div>
          <div className="settings-runtime__value">{cors.active_origins.join(', ') || 'None'}</div>
          <div className="settings-runtime__hint">Updates apply immediately after save.</div>
        </div>
        <div>
          <div className="settings-runtime__label">Secret encryption</div>
          <div className="settings-runtime__value">{encryption.enabled ? 'Enabled' : 'Not configured'}</div>
          <div className="settings-runtime__hint">{encryption.message}</div>
        </div>
      </div>
    </div>
  );
}

function StatusBanner({ type, message }) {
  if (!message) return null;
  const isSuccess = type === 'success';
  return (
    <div className={`alert ${isSuccess ? 'alert--success' : 'alert--danger'}`} role="status">
      {isSuccess ? <CheckCircle2 size={16} className="alert__icon" /> : <AlertTriangle size={16} className="alert__icon" />}
      <span>{message}</span>
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
              <span className="badge badge-success" style={{ marginLeft: 6 }}>Recommended</span>
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

const FORM_MAP = {
  azure: AzureForm,
  database: DatabaseForm,
  application: ApplicationForm,
  kubernetes: KubernetesForm,
};

const SAVE_MAP = {
  azure: saveAzureSettings,
  database: saveDatabaseSettings,
  application: saveApplicationSettings,
  kubernetes: saveKubernetesSettings,
};

const TEST_MAP = {
  azure: testAzureSettings,
  database: testDatabaseSettings,
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
  const qc = useQueryClient();
  const [tab, setTab] = useState('azure');
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

  return (
    <div>
      <PageHeader
        title="Settings"
        iconKey={PAGE_ICONS.settings}
        subtitle="Store Azure, database, and deployment configuration in the database"
      >
        <button type="button" className="btn btn-secondary" onClick={() => reloadMut.mutate()} disabled={reloadMut.isPending}>
          <RefreshCw size={14} className={reloadMut.isPending ? 'spin' : ''} /> Reload Azure credentials
        </button>
      </PageHeader>

      <RuntimeStatus status={runtimeStatus} />

      <div className={`alert ${isAppService ? 'alert--success' : 'alert--warning'}`} style={{ marginBottom: '1rem' }}>
        {isAppService ? <CheckCircle2 size={16} className="alert__icon" /> : <AlertTriangle size={16} className="alert__icon" />}
        <span>
          {isAppService ? (
            <>
              This app is deployed on <strong>Azure Web App</strong>. Azure API access uses <strong>managed identity</strong> by default.
              Enable identity in the portal and assign <strong>Reader</strong> and <strong>Cost Management Reader</strong> on your subscription.
              Set <strong>SETTINGS_ENCRYPTION_KEY</strong> to encrypt any secrets stored in the database.
            </>
          ) : (
            <>
              Enter your <strong>Azure app credentials</strong> on the Azure tab or your <strong>database username and password</strong> on the Database tab.
              Values are saved to the database and encrypted when <strong>SETTINGS_ENCRYPTION_KEY</strong> is set.
            </>
          )}
        </span>
      </div>

      {isLoading && <LoadingState message="Loading settings…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}

      {!isLoading && !isError && (
        <>
          <div className="settings-tabs" role="tablist" aria-label="Settings categories">
            {TABS.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className={`settings-tab${tab === id ? ' settings-tab--active' : ''}`}
                onClick={() => { setTab(id); setSaveMsg(''); setTestMsg({ type: '', text: '' }); }}
              >
                <Icon size={15} /> {label}
              </button>
            ))}
          </div>

          <div className="card settings-panel">
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
          </div>
        </>
      )}
    </div>
  );
}
