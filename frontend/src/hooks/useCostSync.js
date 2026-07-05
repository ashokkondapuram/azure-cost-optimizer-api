import { useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { syncCosts } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { useToast } from '../context/ToastContext';

/**
 * Trigger Azure Cost Management → DB sync and invalidate related React Query caches.
 *
 * @param {object} options
 * @param {string} options.subscription - Azure subscription ID
 * @param {string[][]} [options.invalidateKeys] - queryKey prefixes to invalidate on success
 */
export default function useCostSync({ subscription, invalidateKeys = [] }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [lastChanges, setLastChanges] = useState(null);

  const sync = useCallback(async () => {
    if (!subscription) return null;
    setSyncing(true);
    setMessage('');
    setError(false);
    try {
      const result = await syncCosts({ subscription_id: subscription });
      await Promise.all(
        invalidateKeys.map((key) =>
          queryClient.invalidateQueries({ queryKey: key }),
        ),
      );
      queryClient.invalidateQueries({ queryKey: ['cost-changes', subscription] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-overview', subscription] });
      queryClient.invalidateQueries({ queryKey: ['resources-from-cost', subscription] });

      const counts = result?.synced || {};
      const changes = counts.changes || null;
      setLastChanges(changes);

      const apiRows = counts.api_rows ?? counts.blob_rows ?? 0;
      const mtdRows = counts.mtd_rows ?? 0;
      const mtdMonth = counts.mtd_month;
      const services = counts.cost_by_service ?? 0;
      const resourceTypes = counts.cost_by_resource_type ?? 0;
      const resources = counts.cost_by_resource ?? 0;

      if (apiRows === 0 && services === 0 && resourceTypes === 0 && resources === 0) {
        showToast(
          'Fetch finished but Azure Cost Management returned no cost data for this subscription. '
          + 'Confirm Cost Management Reader access and that usage exists for the current period.',
          { variant: 'error' },
        );
        setError(true);
      } else if (services === 0 && resourceTypes === 0 && resources === 0 && mtdRows === 0) {
        showToast(
          'Cost Management returned data but no month-to-date rows were saved. '
          + 'Usage may not be available for the current billing period yet.',
          { variant: 'warning' },
        );
        setError(true);
      } else {
        const monthNote = mtdMonth ? ` (${mtdMonth})` : '';
        let msg = (
          `Synced ${apiRows.toLocaleString()} daily rows · `
          + `${mtdRows.toLocaleString()} MTD rows${monthNote} · `
          + `saved ${services.toLocaleString()} services, `
          + `${resourceTypes.toLocaleString()} resource types, `
          + `${resources.toLocaleString()} resources`
        );
        if (changes?.has_previous) {
          const delta = changes.total_delta_billing ?? 0;
          const sign = delta >= 0 ? '+' : '';
          msg += ` · MTD increased ${sign}${delta.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} since last fetch`;
        }
        showToast(msg, { variant: 'success' });
      }
      setMessage('');
      return result;
    } catch (err) {
      const msg = getErrorMessage(err, 'Cost fetch failed. Please try again.');
      showToast(msg, { variant: 'error' });
      setMessage('');
      setError(true);
      throw err;
    } finally {
      setSyncing(false);
    }
  }, [subscription, invalidateKeys, queryClient, showToast]);

  const clearMessage = useCallback(() => {
    setMessage('');
    setError(false);
  }, []);

  return { sync, syncing, message, error, clearMessage, lastChanges };
}
