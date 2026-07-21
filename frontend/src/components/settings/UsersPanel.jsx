import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, UserPlus, RefreshCw } from 'lucide-react';
import { createUser, fetchUsers, resetUserPassword } from '../../api/auth';
import { getErrorMessage } from '../../api/errors';
import { formatUserRole } from '../../utils/roleLabels';
import { useAuth } from '../../context/AuthContext';
import { LoadingState, QueryErrorState } from '../QueryStates';

function StatusBanner({ type, message }) {
  if (!message) return null;
  return (
    <div className={`alert ${type === 'success' ? 'alert--success' : 'alert--danger'}`} role="status">
      <span>{message}</span>
    </div>
  );
}

function formatLastLogin(iso) {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

export default function UsersPanel() {
  const qc = useQueryClient();
  const { isSuperuser } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    password: '',
    role: 'viewer',
  });
  const [newPassword, setNewPassword] = useState('');
  const [banner, setBanner] = useState({ type: '', text: '' });

  const { data: users = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ['auth-users'],
    queryFn: fetchUsers,
  });

  const createMut = useMutation({
    mutationFn: () => createUser({
      username: form.username.trim(),
      display_name: form.display_name.trim() || undefined,
      password: form.password,
      role: form.role,
    }),
    onSuccess: () => {
      setBanner({ type: 'success', text: 'User created.' });
      setCreateOpen(false);
      setForm({ username: '', display_name: '', password: '', role: 'viewer' });
      qc.invalidateQueries({ queryKey: ['auth-users'] });
    },
    onError: (err) => setBanner({ type: 'error', text: getErrorMessage(err, 'Could not create user.') }),
  });

  const resetMut = useMutation({
    mutationFn: () => resetUserPassword(resetUser.id, newPassword),
    onSuccess: () => {
      setBanner({ type: 'success', text: `Password updated for ${resetUser.username}.` });
      setResetUser(null);
      setNewPassword('');
      qc.invalidateQueries({ queryKey: ['auth-users'] });
    },
    onError: (err) => setBanner({ type: 'error', text: getErrorMessage(err, 'Could not reset password.') }),
  });

  const canCreate = form.username.trim().length >= 3 && form.password.length >= 8;

  return (
    <div className="settings-form-stack">
      <p className="setting-field__hint" style={{ marginTop: 0 }}>
        Manage sign-in accounts for this application. Viewers can browse synced data and recommendations.
        Admins can sync from Azure, change engine rules, and manage settings. Superusers can also control sidebar access.
      </p>

      <StatusBanner type={banner.type} message={banner.text} />

      {isLoading && <LoadingState message="Loading users…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}

      {!isLoading && !isError && (
        <>
          <div className="settings-panel__actions" style={{ marginBottom: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => { setCreateOpen(true); setBanner({ type: '', text: '' }); }}
            >
              <UserPlus size={14} /> Create user
            </button>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Display name</th>
                  <th>Role</th>
                  <th>Last sign-in</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="text-sm" style={{ fontFamily: 'var(--mono)' }}>{u.username}</td>
                    <td>{u.display_name}</td>
                    <td>
                      <span className={`badge ${u.role === 'admin' || u.role === 'superuser' ? 'badge-info' : ''}`}>
                        {formatUserRole(u.role)}
                      </span>
                    </td>
                    <td className="text-muted text-sm">
                      {formatLastLogin(u.last_login_at)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setResetUser(u);
                          setNewPassword('');
                          setBanner({ type: '', text: '' });
                        }}
                      >
                        <KeyRound size={13} /> Reset password
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {createOpen && (
        <div className="modal-overlay" onClick={() => !createMut.isPending && setCreateOpen(false)} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="create-user-title">
            <h2 id="create-user-title" className="modal-title">Create user</h2>
            <div className="settings-grid" style={{ marginTop: '1rem' }}>
              <div className="setting-field">
                <div className="setting-field__label">Username</div>
                <input
                  type="text"
                  value={form.username}
                  onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                  placeholder="e.g. jane.doe"
                  autoComplete="off"
                />
              </div>
              <div className="setting-field">
                <div className="setting-field__label">Display name</div>
                <input
                  type="text"
                  value={form.display_name}
                  onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                  placeholder="Optional"
                  autoComplete="off"
                />
              </div>
              <div className="setting-field">
                <div className="setting-field__label">Password</div>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                />
              </div>
              <div className="setting-field">
                <div className="setting-field__label">Role</div>
                <select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                  {isSuperuser && <option value="superuser">Superuser</option>}
                </select>
              </div>
            </div>
            <div className="settings-panel__actions" style={{ marginTop: '1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCreateOpen(false)} disabled={createMut.isPending}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => createMut.mutate()}
                disabled={!canCreate || createMut.isPending}
              >
                {createMut.isPending ? <RefreshCw size={14} className="spin" /> : <UserPlus size={14} />}
                Create user
              </button>
            </div>
          </div>
        </div>
      )}

      {resetUser && (
        <div className="modal-overlay" onClick={() => !resetMut.isPending && setResetUser(null)} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="reset-password-title">
            <h2 id="reset-password-title" className="modal-title">Reset password</h2>
            <p style={{ margin: '0 0 1rem', color: 'var(--text2)' }}>
              Set a new password for <strong>{resetUser.username}</strong>.
            </p>
            <div className="setting-field">
              <div className="setting-field__label">New password</div>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete="new-password"
              />
            </div>
            <div className="settings-panel__actions" style={{ marginTop: '1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setResetUser(null)} disabled={resetMut.isPending}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => resetMut.mutate()}
                disabled={newPassword.length < 8 || resetMut.isPending}
              >
                {resetMut.isPending ? <RefreshCw size={14} className="spin" /> : <KeyRound size={14} />}
                Update password
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
