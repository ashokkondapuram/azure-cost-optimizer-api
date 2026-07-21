import {
  formatPageSubtitle,
  formatSubscriptionOptionLabel,
  isSubscriptionGuid,
  resolveSubscriptionLabel,
} from './subscriptionDisplay';

describe('subscriptionDisplay', () => {
  const subId = '93ca908b-5732-440d-b712-f6d7951951c0';

  it('detects subscription guids', () => {
    expect(isSubscriptionGuid(subId)).toBe(true);
    expect(isSubscriptionGuid('Prod')).toBe(false);
  });

  it('uses display name when it is not a guid', () => {
    const label = resolveSubscriptionLabel(subId, [
      { subscriptionId: subId, displayName: 'PNC Dev v2' },
    ]);
    expect(label).toBe('PNC Dev v2');
  });

  it('falls back when display name is the raw subscription id', () => {
    const label = resolveSubscriptionLabel(subId, [
      { subscriptionId: subId, displayName: subId },
    ]);
    expect(label).toBe('This subscription');
    expect(label).not.toContain('93ca908b-5732');
  });

  it('formats page subtitles with subscription scope', () => {
    expect(formatPageSubtitle('dashboard', 'PNC Dev v2')).toBe(
      'PNC Dev v2 — cost, health, and optimization at a glance.',
    );
    expect(formatPageSubtitle('dashboard', 'This subscription')).toBe(
      'This subscription — cost, health, and optimization at a glance.',
    );
  });

  it('formats subscription picker labels', () => {
    expect(formatSubscriptionOptionLabel({
      subscriptionId: subId,
      displayName: 'PNC Dev v2',
    })).toBe('PNC Dev v2 (93ca908b…)');
  });
});
