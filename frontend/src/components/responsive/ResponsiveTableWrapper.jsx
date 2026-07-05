import React, { useEffect, useState } from 'react';

const MOBILE_BP = 768;

function useIsNarrow(breakpoint = MOBILE_BP) {
  const [narrow, setNarrow] = useState(
    () => (typeof window !== 'undefined' ? window.innerWidth <= breakpoint : false),
  );

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const onChange = () => setNarrow(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [breakpoint]);

  return narrow;
}

/**
 * Renders table on desktop and optional mobile card list.
 * Pass mobileCards when card layout differs from table rows.
 */
export default function ResponsiveTableWrapper({
  children,
  mobileCards = null,
  className = '',
}) {
  const isNarrow = useIsNarrow();

  if (isNarrow && mobileCards) {
    return <div className={`responsive-table-cards${className ? ` ${className}` : ''}`}>{mobileCards}</div>;
  }

  return (
    <div className={`responsive-table-wrap${className ? ` ${className}` : ''}`}>
      {children}
    </div>
  );
}
