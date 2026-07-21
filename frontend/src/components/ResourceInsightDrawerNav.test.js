import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import ResourceInsightDrawerNav, { focusSectionToTab } from './ResourceInsightDrawerNav';

const SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'findings', label: 'Findings', badge: 3 },
  { id: 'metrics', label: 'Metrics' },
];

function renderNav(props) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<ResourceInsightDrawerNav {...props} />);
  });
  return {
    container,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

describe('focusSectionToTab', () => {
  it('maps legacy section ids to drawer tabs', () => {
    expect(focusSectionToTab(null)).toBe('overview');
    expect(focusSectionToTab('advanced-analysis')).toBe('analysis');
    expect(focusSectionToTab('cost-signals')).toBe('cost-drivers');
    expect(focusSectionToTab('cost-drivers')).toBe('cost-drivers');
    expect(focusSectionToTab('consistency-policy')).toBe('overview');
    expect(focusSectionToTab('tag-compliance')).toBe('overview');
    expect(focusSectionToTab('prop-consistencyPolicy')).toBe('overview');
    expect(focusSectionToTab('technical-properties')).toBe('overview');
    expect(focusSectionToTab('prop:general')).toBe('overview');
    expect(focusSectionToTab('proposed-actions')).toBe('actions');
    expect(focusSectionToTab('findings')).toBe('findings');
  });
});

describe('ResourceInsightDrawerNav', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders section labels and badges when expanded', () => {
    const { container, unmount } = renderNav({
      sections: SECTIONS,
      activeSection: 'overview',
      onNavigate: jest.fn(),
      expanded: true,
    });

    expect(container.textContent).toContain('Overview');
    expect(container.textContent).toContain('Findings');
    expect(container.textContent).toContain('3');
    expect(container.querySelector('nav').getAttribute('aria-expanded')).toBe('true');
    unmount();
  });

  it('hides labels and exposes tooltips when collapsed', () => {
    const { container, unmount } = renderNav({
      sections: SECTIONS,
      activeSection: 'findings',
      onNavigate: jest.fn(),
      collapsed: true,
      onToggleCollapse: jest.fn(),
    });

    const findingsTab = container.querySelector('#drawer-tab-findings');
    expect(findingsTab.getAttribute('title')).toBe('Findings (3)');
    expect(findingsTab.getAttribute('aria-label')).toBe('Findings (3)');
    expect(container.querySelector('.insight-drawer__nav--collapsed')).not.toBeNull();
    expect(container.querySelector('.insight-drawer__nav-badge-dot')).not.toBeNull();
    expect(container.querySelector('.insight-drawer__nav-badge')).toBeNull();
    expect(container.querySelector('nav').getAttribute('aria-expanded')).toBe('false');
    unmount();
  });

  it('calls onNavigate when a section is clicked', () => {
    const onNavigate = jest.fn();
    const { container, unmount } = renderNav({
      sections: SECTIONS,
      activeSection: 'overview',
      onNavigate,
      expanded: true,
    });

    act(() => {
      container.querySelector('#drawer-tab-metrics').click();
    });
    expect(onNavigate).toHaveBeenCalledWith('metrics');
    unmount();
  });

  it('renders collapse toggle with accessible labels', () => {
    const onToggleCollapse = jest.fn();
    const { container, unmount } = renderNav({
      sections: SECTIONS,
      activeSection: 'overview',
      onNavigate: jest.fn(),
      expanded: true,
      onToggleCollapse,
    });

    const collapseBtn = container.querySelector('.insight-drawer__nav-toggle');
    expect(collapseBtn.getAttribute('aria-label')).toBe('Collapse navigation');
    expect(collapseBtn.getAttribute('aria-expanded')).toBe('true');

    act(() => {
      collapseBtn.click();
    });
    expect(onToggleCollapse).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('shows expand label when collapsed', () => {
    const { container, unmount } = renderNav({
      sections: SECTIONS,
      activeSection: 'overview',
      onNavigate: jest.fn(),
      collapsed: true,
      onToggleCollapse: jest.fn(),
    });

    const expandBtn = container.querySelector('.insight-drawer__nav-toggle');
    expect(expandBtn.getAttribute('aria-label')).toBe('Expand navigation');
    expect(expandBtn.getAttribute('aria-expanded')).toBe('false');
    unmount();
  });

  it('returns null when there are no sections', () => {
    const { container, unmount } = renderNav({
      sections: [],
      activeSection: 'overview',
      onNavigate: jest.fn(),
    });
    expect(container.querySelector('nav')).toBeNull();
    unmount();
  });
});
