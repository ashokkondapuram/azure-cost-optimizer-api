/** Unified budget API — Azure snapshots + custom app budgets. */
import api from './client';

export async function fetchSubscriptionBudgets(subscriptionId) {
  const { data } = await api.get(`/budgets/${encodeURIComponent(subscriptionId)}`);
  return data;
}

export async function createBudget(payload) {
  const { data } = await api.post('/budgets/', payload);
  return data;
}

export async function updateBudget(subscriptionId, name, payload) {
  const { data } = await api.patch(
    `/budgets/${encodeURIComponent(subscriptionId)}/${encodeURIComponent(name)}`,
    payload,
  );
  return data;
}

export async function deleteBudget(subscriptionId, name) {
  await api.delete(
    `/budgets/${encodeURIComponent(subscriptionId)}/${encodeURIComponent(name)}`,
  );
}

/** Normalize API budgets for Budget Manager cards. */
export function mapBudgetForManager(row) {
  return {
    id: row.id,
    name: row.name,
    scope: row.scope || 'subscription',
    amount: row.amount ?? row.monthly_limit ?? 0,
    spent: row.spent ?? row.currentSpend ?? row.current_spend ?? 0,
    period: row.period || 'monthly',
    threshold: row.threshold ?? (row.alert_thresholds?.[row.alert_thresholds.length - 1]) ?? 80,
    currency: row.currency || 'CAD',
    source: row.source || 'azure',
    status: row.status,
  };
}
