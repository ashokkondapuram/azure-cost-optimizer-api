import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RecommendationHelpTooltip from './RecommendationHelpTooltip';

const FINDING = {
  rule_name: 'Disk oversize',
  recommendation: 'Downgrade to Standard SSD to reduce cost.',
  pillar: 'cost',
  severity: 'HIGH',
};

function renderTooltip(props = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <RecommendationHelpTooltip finding={FINDING} detailHint="View details in drawer" {...props}>
        Downgrade to Standard SSD
      </RecommendationHelpTooltip>,
    );
  });
  return {
    container,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
      document.body.innerHTML = '';
    },
  };
}

describe('RecommendationHelpTooltip', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders headline text and a keyboard-focusable help trigger', () => {
    const { container, unmount } = renderTooltip();

    expect(container.textContent).toContain('Downgrade to Standard SSD');
    const trigger = container.querySelector('.rec-help__trigger');
    expect(trigger).not.toBeNull();
    expect(trigger.getAttribute('aria-label')).toContain('Downgrade to Standard SSD');
    expect(trigger.getAttribute('aria-label')).toContain('Cost');
    expect(trigger.getAttribute('aria-label')).toContain('High');
    unmount();
  });

  it('shows a portaled tooltip on focus with meta and hint', async () => {
    const { container, unmount } = renderTooltip();
    const slot = container.querySelector('.rec-help');
    slot.getBoundingClientRect = () => ({
      top: 40,
      left: 20,
      bottom: 60,
      right: 180,
      width: 160,
      height: 20,
    });

    await act(async () => {
      container.querySelector('.rec-help__trigger').focus();
      await new Promise((resolve) => { setTimeout(resolve, 150); });
    });

    const flyout = document.body.querySelector('.rec-help-flyout');
    expect(flyout).not.toBeNull();
    expect(flyout.textContent).toContain('Downgrade to Standard SSD to reduce cost.');
    expect(flyout.textContent).toContain('Cost');
    expect(flyout.textContent).toContain('High');
    expect(flyout.textContent).toContain('View details in drawer');
    expect(flyout.getAttribute('role')).toBe('tooltip');

    unmount();
  });

  it('renders children only when finding has no message', () => {
    const { container, unmount } = renderTooltip({ finding: null });

    expect(container.textContent).toBe('Downgrade to Standard SSD');
    expect(container.querySelector('.rec-help__trigger')).toBeNull();
    unmount();
  });
});
