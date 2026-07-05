import React, { useContext } from 'react';
import { Link } from 'react-router-dom';
import AssetIcon from '../AssetIcon';
import {
  DASHBOARD_SECTIONS,
  formatDashboardCount,
  visibleDashboardItems,
  syncTypesForDashboardItems,
  categoryResourceCount,
  PAGE_ICON_KEYS,
  NAV_RESOURCE_GROUPS,
} from '../../config/appRegistry';
import CategorySyncButton from '../navigation/CategorySyncButton';
import { useAuth } from '../../context/AuthContext';
import { AppCtx } from '../../App';

function sectionBadgeCount(section, counts) {
  if (section.id === 'overview') return 0;
  const groupIds = new Set(
    (section.items || [])
      .filter((item) => item.type === 'resource')
      .map((item) => NAV_RESOURCE_GROUPS.find((g) => g.resourceIds.includes(item.id))?.id)
      .filter(Boolean),
  );
  let total = 0;
  for (const groupId of groupIds) {
    const group = NAV_RESOURCE_GROUPS.find((g) => g.id === groupId);
    if (group) total += categoryResourceCount(group, counts, { costOnly: true });
  }
  return total;
}

export default function DashboardInventory({
  counts,
  countsLoading,
  countsError,
  totalResources,
}) {
  const { isAdmin } = useAuth();
  const { subscription } = useContext(AppCtx);

  return (
    <section className="dashboard-inventory">
      <header className="dashboard-inventory__header">
        <div>
          <h3 className="dashboard-section__title">Browse resources</h3>
          {!countsLoading && totalResources != null && totalResources > 0 && (
            <p className="dashboard-section__sub">
              {Number(totalResources).toLocaleString()} resources with cost
            </p>
          )}
        </div>
        {countsError && (
          <span className="analysis-bar__msg analysis-bar__msg--err">Could not load counts</span>
        )}
      </header>

      <div className="dashboard-inventory__grid">
        {DASHBOARD_SECTIONS.map((section) => {
          const items = visibleDashboardItems(section, counts);
          const isResourceSection = section.id !== 'overview';
          if (isResourceSection && items.length === 0) return null;
          if (!isResourceSection && items.length === 0) return null;

          const sectionTotal = isResourceSection ? sectionBadgeCount(section, counts) : 0;

          return (
            <article
              key={section.id}
              className="dashboard-inventory__card"
              style={{ '--section-accent': section.color }}
            >
              <header className="dashboard-inventory__card-head">
                <AssetIcon iconKey={PAGE_ICON_KEYS[section.iconKey]} size={18} alt="" />
                <div className="dashboard-inventory__card-head-text">
                  <div className="dashboard-inventory__card-title-row">
                    <h4>{section.label}</h4>
                    {isResourceSection && !countsLoading && sectionTotal > 0 && (
                      <span className="dashboard-inventory__card-badge">{sectionTotal}</span>
                    )}
                  </div>
                </div>
              </header>
              {items.length > 0 ? (
                <ul className="dashboard-inventory__list">
                  {items.map((item) => {
                    const formatted = item.countKey
                      ? formatDashboardCount(counts, null, item.countKey)
                      : null;
                    const displayCount = formatted?.total ?? null;

                    return (
                      <li key={item.link}>
                        <Link to={item.link} className="dashboard-inventory__link">
                          <AssetIcon iconKey={PAGE_ICON_KEYS[item.iconKey]} size={14} alt="" />
                          <span className="dashboard-inventory__link-label">{item.name}</span>
                          <span
                            className={`dashboard-inventory__count${
                              displayCount > 0 ? ' dashboard-inventory__count--active' : ''
                            }`}
                          >
                            {item.countKey
                              ? (countsLoading ? '…' : displayCount)
                              : '—'}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="dashboard-inventory__empty">
                  <p>No resources synced.</p>
                  {isAdmin && subscription && (
                    <CategorySyncButton
                      label={section.label}
                      syncTypes={syncTypesForDashboardItems(items, counts)}
                      variant="prominent"
                    />
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
