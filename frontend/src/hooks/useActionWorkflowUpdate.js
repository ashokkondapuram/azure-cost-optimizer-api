import { useMutation, useQueryClient } from '@tanstack/react-query';
import { updateOptimizationAction } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { useToast } from '../context/ToastContext';
import { workflowStatusLabel } from '../utils/actionUtils';

export default function useActionWorkflowUpdate(subscriptionId) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const mutation = useMutation({
    mutationFn: ({ actionId, body }) => updateOptimizationAction(actionId, body, subscriptionId),
    onSuccess: (_updated, vars) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-actions'] });
      queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
      queryClient.invalidateQueries({ queryKey: ['findings-index'] });
      queryClient.invalidateQueries({ queryKey: ['findings-summary'] });
      const status = vars.body?.workflow_status;
      if (status) {
        showToast(`Action marked ${workflowStatusLabel(status).toLowerCase()}`, { variant: 'success' });
      } else if (vars.body?.note) {
        showToast('Note saved', { variant: 'success' });
      }
    },
    onError: (err) => showToast(getErrorMessage(err), { variant: 'error' }),
  });

  const updateAction = (actionId, body, options = {}) => {
    if (!subscriptionId || !actionId) return;
    mutation.mutate({ actionId, body }, options);
  };

  return {
    updateAction,
    isPending: mutation.isPending,
    pendingActionId: mutation.variables?.actionId || null,
  };
}
