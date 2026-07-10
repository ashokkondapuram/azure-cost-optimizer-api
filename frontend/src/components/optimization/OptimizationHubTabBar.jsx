import React from 'react';
import AssetIcon from '../AssetIcon';
import { useOptimizationHub, OPTIMIZATION_HUB_TABS } from '../../context/OptimizationHubContext';

export default function OptimizationHubTabBar() {
  const { tab, setTab } = useOptimizationHub();

  return (
    <nav
      className="optimization-hub-tabs"
      role="tablist"
      aria-label="Optimization hub sections"
    >
      {OPTIMIZATION_HUB_TABS.map((item) => {
        const active = tab === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`optimization-hub-tab-${item.id}`}
            aria-selected={active}
            aria-controls={`optimization-hub-panel-${item.id}`}
            className={`optimization-hub-tabs__tab${active ? ' optimization-hub-tabs__tab--active' : ''}`}
            onClick={() => setTab(item.id)}
          >
            <span className="optimization-hub-tabs__icon" aria-hidden>
              <AssetIcon iconKey={item.iconKey} size={16} alt="" />
            </span>
            <span className="optimization-hub-tabs__text">
              <span className="optimization-hub-tabs__label">{item.label}</span>
              <span className="optimization-hub-tabs__desc">{item.desc}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
