/** Human-readable labels for app user roles. */
export function formatUserRole(role) {
  if (role === 'superuser') return 'Superuser';
  if (role === 'admin') return 'Admin';
  if (role === 'viewer') return 'Viewer';
  return role || 'User';
}
