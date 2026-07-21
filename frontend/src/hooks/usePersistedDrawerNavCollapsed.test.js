import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import usePersistedDrawerNavCollapsed from './usePersistedDrawerNavCollapsed';

function renderHookResult(storageKey = 'finops-drawer-nav-collapsed') {
  let latest;
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  function Harness() {
    latest = usePersistedDrawerNavCollapsed(storageKey);
    return null;
  }

  act(() => {
    root.render(<Harness />);
  });

  return {
    get latest() {
      return latest;
    },
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

describe('usePersistedDrawerNavCollapsed', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
  });

  it('defaults to expanded (not collapsed)', () => {
    const harness = renderHookResult();
    expect(harness.latest[0]).toBe(false);
    harness.unmount();
  });

  it('reads persisted collapsed preference', () => {
    localStorage.setItem('finops-drawer-nav-collapsed', 'true');
    const harness = renderHookResult();
    expect(harness.latest[0]).toBe(true);
    harness.unmount();
  });

  it('toggles collapsed state and persists it', () => {
    const harness = renderHookResult();
    const [, toggleCollapsed] = harness.latest;

    act(() => {
      toggleCollapsed();
    });

    expect(harness.latest[0]).toBe(true);
    expect(JSON.parse(localStorage.getItem('finops-drawer-nav-collapsed'))).toBe(true);
    harness.unmount();
  });
});
