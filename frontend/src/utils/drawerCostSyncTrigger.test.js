import {
  resetDrawerCostSyncSession,
  hasAttemptedDrawerCostSync,
  markDrawerCostSyncAttempted,
} from './drawerCostSyncSession';
import { shouldAutoSyncDrawerCost } from './drawerCostSyncTrigger';

describe('drawerCostSyncSession', () => {
  beforeEach(() => {
    resetDrawerCostSyncSession();
  });

  it('tracks attempted subscriptions per session', () => {
    expect(hasAttemptedDrawerCostSync('Sub-1')).toBe(false);
    markDrawerCostSyncAttempted('Sub-1');
    expect(hasAttemptedDrawerCostSync('sub-1')).toBe(true);
    expect(hasAttemptedDrawerCostSync('Sub-2')).toBe(false);
  });
});

describe('shouldAutoSyncDrawerCost', () => {
  const emptyPayload = {
    sync_required: true,
    points: [{ date: '2026-07-10', cost: 0 }],
  };

  it('returns true when spend trend is empty and sync is required', () => {
    expect(shouldAutoSyncDrawerCost({
      subscriptionId: 'sub-1',
      resourceId: '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
      dailyPayload: emptyPayload,
    })).toBe(true);
  });

  it('returns false when session already attempted sync', () => {
    expect(shouldAutoSyncDrawerCost({
      subscriptionId: 'sub-1',
      resourceId: '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
      dailyPayload: emptyPayload,
      sessionAttempted: true,
    })).toBe(false);
  });

  it('returns false when spend data already exists', () => {
    expect(shouldAutoSyncDrawerCost({
      subscriptionId: 'sub-1',
      resourceId: '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
      dailyPayload: {
        sync_required: false,
        points: [{ date: '2026-07-10', cost: 4.5 }],
      },
    })).toBe(false);
  });

  it('returns false while query is loading', () => {
    expect(shouldAutoSyncDrawerCost({
      subscriptionId: 'sub-1',
      resourceId: '/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
      dailyPayload: emptyPayload,
      isLoading: true,
    })).toBe(false);
  });
});
