import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { OPTIMIZATION_NAV_ITEMS } from '../../config/appRegistry';
import AssetIcon from '../AssetIcon';
import { PAGE_ICON_KEYS } from '../../config/appRegistry';

export default function OptimizationHubLinks({ className = '', showSections = false }) {
  const { isAdmin } = useAuth();
  const items = OPTIMIZATION_NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  if (items.length === 0) return null;

  let lastSection = null;

  return (
    <nav className={`optimization-hub${className ? ` ${className}` : ''}`} aria-label="Optimization">
      <NavLink
        to="/optimization-hub"
        className={({ isActive }) =>
          `optimization-hub__link${isActive ? ' optimization-hub__link--active' : ''}`
        }
      >
        <AssetIcon iconKey={PAGE_ICON_KEYS.actions} size={15} alt="" />
        <span>Optimization hub</span>
      </NavLink>
      {items.map((item) => {
        const sectionLabel = showSections && item.section && item.section !== lastSection;
        if (sectionLabel) lastSection = item.section;
        return (
          <React.Fragment key={item.path}>
            {sectionLabel && (
              <span className="optimization-hub__section">{item.section}</span>
            )}
            <NavLink
              to={item.path}
              className={({ isActive }) =>
                `optimization-hub__link${isActive ? ' optimization-hub__link--active' : ''}`
              }
            >
              <AssetIcon iconKey={PAGE_ICON_KEYS[item.iconKey]} size={15} alt="" />
              <span>{item.title}</span>
            </NavLink>
          </React.Fragment>
        );
      })}
    </nav>
  );
}
