import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LayoutGrid, RefreshCw, Save } from 'lucide-react';
import Toggle from '../Toggle';
import { LoadingState, QueryErrorState } from '../QueryStates';
import { fetchNavAccessPolicy, saveNavAccessPolicy } from '../../api/settings';
import { getErrorMessage } from '../../api/errors';
import {
  NAV_ACCESS_GROUPS,
  NAV_ACCESS_SUBGROUPS,
  navSectionId,
} from '../../utils/navAccess';

function StatusBanner({ type, message }) {
  if (!message) return null;
  return (
    <div className={`alert ${type === 'success' ? 'alert--success' : 'alert--danger'}`} role="status">
      <span>{message}</span>
    </div>
  );
}

function roleLabel(role) {
  if (role === 'admin') return 'Admin';
  if (role === 'viewer') return 'Viewer';
  return role;
}

function childSectionIds(groupId) {
  return (NAV_ACCESS_SUBGROUPS[groupId] || []).map((entry) => entry.sectionId);
}

function panelIdsForGroup(catalog, groupId) {
  return catalog
    .filter((panel) => panel.group === groupId && panel.kind !== 'section')
    .map((panel) => panel.id);
}

export default function NavAccessPanel() {
  const qc = useQueryClient();
  const [activeRole, setActiveRole] = useState('admin');
  const [draft, setDraft] = useState(null);
  const [banner, setBanner] = useState({ type: '', text: '' });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['nav-access-policy'],
    queryFn: fetchNavAccessPolicy,
  });

  const roles = draft ?? data?.roles ?? {};
  const catalog = data?.catalog ?? [];

  const panelsByGroup = useMemo(() => {
    const grouped = {};
    NAV_ACCESS_GROUPS.forEach((g) => { grouped[g.id] = []; });
    catalog.forEach((panel) => {
      if (panel.kind === 'section') return;
      const group = panel.group || 'overview';
      if (!grouped[group]) grouped[group] = [];
      grouped[group].push(panel);
    });
    return grouped;
  }, [catalog]);

  const saveMut = useMutation({
    mutationFn: () => saveNavAccessPolicy(roles),
    onSuccess: (payload) => {
      setDraft(null);
      setBanner({ type: 'success', text: 'Sidebar access saved.' });
      qc.setQueryData(['nav-access-policy'], payload);
      qc.invalidateQueries({ queryKey: ['nav-access'] });
    },
    onError: (err) => setBanner({ type: 'error', text: getErrorMessage(err, 'Could not save sidebar access.') }),
  });

  const updateRoleConfig = (role, updater) => {
    setDraft((prev) => {
      const base = prev ?? data?.roles ?? {};
      const roleCfg = { ...(base[role] || {}) };
      updater(roleCfg);
      return { ...base, [role]: roleCfg };
    });
  };

  const setPanelVisible = (role, panelId, visible) => {
    updateRoleConfig(role, (roleCfg) => {
      roleCfg[panelId] = visible;
    });
  };

  const setSectionVisible = (role, sectionId, visible) => {
    updateRoleConfig(role, (roleCfg) => {
      roleCfg[sectionId] = visible;
      if (!visible) {
        const groupId = sectionId.replace(/^section:/, '').split(':')[0];
        const isCategory = sectionId === navSectionId(groupId);

        if (isCategory) {
          childSectionIds(groupId).forEach((childId) => {
            roleCfg[childId] = false;
          });
          panelIdsForGroup(catalog, groupId).forEach((panelId) => {
            roleCfg[panelId] = false;
          });
          return;
        }

        const subgroupId = sectionId.split(':').pop();
        catalog
          .filter((panel) => panel.group === groupId && panel.subgroup === subgroupId)
          .forEach((panel) => {
            roleCfg[panel.id] = false;
          });
      }
    });
  };

  const resetRole = (role) => {
    const defaults = data?.defaults?.[role];
    if (!defaults) return;
    setDraft((prev) => ({
      ...(prev ?? data?.roles ?? {}),
      [role]: { ...defaults },
    }));
  };

  if (isLoading) return <LoadingState message="Loading sidebar access…" />;
  if (isError) return <QueryErrorState error={error} onRetry={refetch} title="Could not load sidebar access" />;

  const managedRoles = ['admin', 'viewer'];

  return (
    <div className="settings-form-stack">
      <p className="setting-field__hint" style={{ marginTop: 0 }}>
        Control sidebar visibility by category, subcategory, or individual panel. Superusers always have full access.
        Hiding a category hides everything inside it.
      </p>

      <StatusBanner type={banner.type} message={banner.text} />

      <div className="settings-panel__actions" style={{ marginBottom: '0.75rem', gap: '0.5rem', display: 'flex', flexWrap: 'wrap' }}>
        {managedRoles.map((role) => (
          <button
            key={role}
            type="button"
            className={`btn btn-sm ${activeRole === role ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveRole(role)}
          >
            <LayoutGrid size={14} />
            {roleLabel(role)}
          </button>
        ))}
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => resetRole(activeRole)}
        >
          <RefreshCw size={14} />
          Reset {roleLabel(activeRole)} to defaults
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
        >
          <Save size={14} />
          {saveMut.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>

      {NAV_ACCESS_GROUPS.map((group) => {
        const panels = panelsByGroup[group.id] || [];
        const subgroups = NAV_ACCESS_SUBGROUPS[group.id] || [];
        const categorySectionId = navSectionId(group.id);
        const categoryVisible = Boolean(roles?.[activeRole]?.[categorySectionId]);
        if (!panels.length) return null;

        return (
          <div key={group.id} className="card settings-nav-access__group" style={{ marginBottom: '1rem' }}>
            <div className="settings-nav-access__group-head">
              <h3 className="settings-card__title">{group.label}</h3>
              <Toggle
                checked={categoryVisible}
                onChange={(checked) => setSectionVisible(activeRole, categorySectionId, checked)}
                label={`Show ${group.label} category for ${roleLabel(activeRole)}`}
              />
            </div>

            {subgroups.length > 0 && (
              <div className="settings-nav-access__subgroups" role="group" aria-label={`${group.label} subcategories`}>
                {subgroups.map((subgroup) => (
                  <label key={subgroup.sectionId} className="settings-nav-access__subgroup">
                    <Toggle
                      checked={categoryVisible && Boolean(roles?.[activeRole]?.[subgroup.sectionId])}
                      onChange={(checked) => setSectionVisible(activeRole, subgroup.sectionId, checked)}
                      label={`Show ${subgroup.label} for ${roleLabel(activeRole)}`}
                      disabled={!categoryVisible}
                    />
                    <span>{subgroup.label}</span>
                  </label>
                ))}
              </div>
            )}

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Panel</th>
                    <th style={{ width: 120 }}>Visible</th>
                  </tr>
                </thead>
                <tbody>
                  {panels.map((panel) => {
                    const subgroup = subgroups.find((entry) => entry.id === panel.subgroup);
                    const subgroupVisible = !subgroup || Boolean(roles?.[activeRole]?.[subgroup.sectionId]);
                    const rowEnabled = categoryVisible && subgroupVisible && !panel.superuser_only;
                    return (
                      <tr key={panel.id} className={rowEnabled ? '' : 'settings-nav-access__row--muted'}>
                        <td>
                          <span style={{ fontWeight: 500 }}>{panel.label}</span>
                          {panel.admin_only && (
                            <span className="badge badge-muted" style={{ marginLeft: 8 }}>Admin default</span>
                          )}
                          {panel.superuser_only && (
                            <span className="badge badge-muted" style={{ marginLeft: 8 }}>Superuser only</span>
                          )}
                          {subgroup && (
                            <span className="badge badge-muted" style={{ marginLeft: 8 }}>{subgroup.label}</span>
                          )}
                        </td>
                        <td>
                          <Toggle
                            checked={rowEnabled && Boolean(roles?.[activeRole]?.[panel.id])}
                            onChange={(checked) => setPanelVisible(activeRole, panel.id, checked)}
                            label={`Show ${panel.label} for ${roleLabel(activeRole)}`}
                            disabled={!rowEnabled}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
