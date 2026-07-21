const attemptedSubscriptions = new Set();

export function drawerCostSyncSessionKey(subscriptionId) {
  return String(subscriptionId || '').trim().toLowerCase();
}

export function hasAttemptedDrawerCostSync(subscriptionId) {
  const key = drawerCostSyncSessionKey(subscriptionId);
  return key ? attemptedSubscriptions.has(key) : false;
}

export function markDrawerCostSyncAttempted(subscriptionId) {
  const key = drawerCostSyncSessionKey(subscriptionId);
  if (key) attemptedSubscriptions.add(key);
}

/** Test helper — clears in-memory session guard. */
export function resetDrawerCostSyncSession() {
  attemptedSubscriptions.clear();
}
