import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const SHOW_DELAY_MS = 80;

/**
 * Flyout label for collapsed sidebar rail items (portaled so it is not clipped).
 */
export default function SidebarRailTooltip({ label, children }) {
  const slotRef = useRef(null);
  const showTimerRef = useRef(null);
  const [tip, setTip] = useState(null);

  const positionTip = useCallback(() => {
    const node = slotRef.current;
    if (!node) return null;
    const rect = node.getBoundingClientRect();
    return {
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
    };
  }, []);

  const showTip = useCallback(() => {
    if (!label) return;
    clearTimeout(showTimerRef.current);
    showTimerRef.current = setTimeout(() => {
      const next = positionTip();
      if (next) setTip(next);
    }, SHOW_DELAY_MS);
  }, [label, positionTip]);

  const hideTip = useCallback(() => {
    clearTimeout(showTimerRef.current);
    setTip(null);
  }, []);

  useEffect(() => {
    if (!tip) return undefined;

    const refresh = () => {
      const next = positionTip();
      if (next) setTip(next);
    };

    const hideOnScroll = () => hideTip();

    window.addEventListener('scroll', hideOnScroll, true);
    window.addEventListener('resize', refresh);
    return () => {
      window.removeEventListener('scroll', hideOnScroll, true);
      window.removeEventListener('resize', refresh);
    };
  }, [tip, positionTip, hideTip]);

  useEffect(() => () => clearTimeout(showTimerRef.current), []);

  return (
    <>
      <div
        className="sidebar-rail-slot"
        ref={slotRef}
        onMouseEnter={showTip}
        onMouseLeave={hideTip}
        onFocus={showTip}
        onBlur={hideTip}
      >
        {children}
      </div>
      {tip && label && createPortal(
        <div
          className="sidebar-rail-flyout"
          style={{ top: tip.top, left: tip.left }}
          role="tooltip"
        >
          <span className="sidebar-rail-flyout__label">{label}</span>
        </div>,
        document.body,
      )}
    </>
  );
}
