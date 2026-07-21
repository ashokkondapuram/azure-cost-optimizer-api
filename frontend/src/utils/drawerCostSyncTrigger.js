import { fetchDashboardSyncStatus, syncCosts } from '../api/azure';
import { buildResourceSpendTrendChart, hasSpendTrendData } from './drawerResourceCostTrend';

const POLL_INTERVAL_MS = 2500;
const SYNC_TIMEOUT_MS = 300_000;

export function shouldAutoSyncDrawerCost({
  enabled = true,
  subscriptionId,
  resourceId,
  isLoading = false,
  dailyPayload = null,
  sessionAttempted = false,
}) {
  if (!enabled || !subscriptionId || !resourceId || isLoading || !dailyPayload) return false;
  if (sessionAttempted) return false;
  if (!dailyPayload.sync_required) return false;
  return !hasSpendTrendData(buildResourceSpendTrendChart(dailyPayload.points));
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason || new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(signal.reason || new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

export async function waitForCostSyncCompletion(subscriptionId, baselineSyncedAt, options = {}) {
  const { signal } = options;
  const deadline = Date.now() + SYNC_TIMEOUT_MS;

  while (Date.now() < deadline) {
    await sleep(POLL_INTERVAL_MS, signal);
    const status = await fetchDashboardSyncStatus({ subscription_id: subscriptionId }, { signal });
    const pending = Boolean(status?.cost?.pending);
    const lastSyncedAt = status?.cost?.last_synced_at || null;
    if (!pending && lastSyncedAt && lastSyncedAt !== baselineSyncedAt) {
      return status;
    }
  }

  throw new Error('Cost sync is still running. Refresh in a minute to see updated spend trends.');
}

/**
 * Trigger subscription cost sync for the drawer spend trend.
 * Admins POST to /costs/sync; all users wait for background worker completion.
 */
export async function triggerDrawerCostSync({ subscriptionId, isAdmin = false, signal } = {}) {
  if (!subscriptionId) {
    throw new Error('Subscription is required to sync spend history.');
  }

  const baseline = await fetchDashboardSyncStatus({ subscription_id: subscriptionId }, { signal });
  const baselineSyncedAt = baseline?.cost?.last_synced_at || null;

  if (isAdmin) {
    const result = await syncCosts({ subscription_id: subscriptionId, signal });
    if (!(result?.async || result?.httpStatus === 202)) {
      return result;
    }
  }

  return waitForCostSyncCompletion(subscriptionId, baselineSyncedAt, { signal });
}
