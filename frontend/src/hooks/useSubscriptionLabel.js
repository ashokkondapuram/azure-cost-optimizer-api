import { useContext, useMemo } from 'react';
import { AppCtx } from '../App';
import { resolveSubscriptionLabel } from '../utils/subscriptionDisplay';

/** Resolved subscription display label from app context (never a raw GUID). */
export default function useSubscriptionLabel() {
  const { subscription, subscriptionOptions } = useContext(AppCtx);

  const subscriptionLabel = useMemo(
    () => resolveSubscriptionLabel(subscription, subscriptionOptions),
    [subscription, subscriptionOptions],
  );

  return { subscription, subscriptionLabel, subscriptionOptions };
}
