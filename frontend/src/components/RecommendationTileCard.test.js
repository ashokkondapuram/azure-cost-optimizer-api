/* eslint-disable testing-library/no-container, testing-library/no-unnecessary-act, testing-library/no-node-access */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RecommendationTileCard from './RecommendationTileCard';

const FINDING = {
  id: 'finding-1',
  rule_name: 'Disk oversize',
  recommendation: 'Downgrade to Standard SSD to reduce monthly cost.',
  severity: 'HIGH',
  estimated_savings_usd: 120,
  status: 'open',
};

function renderTile(props = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const onToggle = jest.fn();
  act(() => {
    root.render(
      <RecommendationTileCard
        finding={FINDING}
        resourceTypeLabel="Managed disk"
        onToggle={onToggle}
        {...props}
      />,
    );
  });
  return {
    container,
    onToggle,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
      document.body.innerHTML = '';
    },
  };
}

describe('RecommendationTileCard', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders collapsed tile summary with savings and resource hint', () => {
    const { container, unmount } = renderTile();

    expect(container.textContent).toContain('Disk oversize');
    expect(container.textContent).toContain('$120/mo');
    expect(container.textContent).toContain('Managed disk');
    expect(container.querySelector('.rec-tile-card__face')?.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.rec-tile-card__detail')).toBeNull();
    unmount();
  });

  it('expands detail panel on click and supports accordion toggle', () => {
    const { container, onToggle, unmount } = renderTile({ expanded: true });

    expect(container.querySelector('.rec-tile-card__face')?.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('.rec-tile-card__detail')).not.toBeNull();
    expect(container.textContent).toContain('Downgrade to Standard SSD');

    const face = container.querySelector('.rec-tile-card__face');
    act(() => {
      face.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(onToggle).toHaveBeenCalledWith('finding-1');
    unmount();
  });

  it('toggles from keyboard Enter', () => {
    const { container, onToggle, unmount } = renderTile();

    const face = container.querySelector('.rec-tile-card__face');
    act(() => {
      face.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });
    expect(onToggle).toHaveBeenCalledWith('finding-1');
    unmount();
  });
});
