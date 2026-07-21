/** Human-readable labels for app user roles. */
export function formatUserRole(role) {
  if (role === 'superuser') return 'Superuser';
  if (role === 'admin') return 'Admin';
  if (role === 'viewer') return 'Viewer';
  return role || 'User';
}

/** Seat label for sidebar user footer (Concept v2 style). */
export function formatSeatLabel(role) {
  if (role === 'viewer') return 'View seat';
  if (role === 'admin') return 'Admin seat';
  if (role === 'superuser') return 'Superuser seat';
  if (role) return `${formatUserRole(role)} seat`;
  return 'User seat';
}
