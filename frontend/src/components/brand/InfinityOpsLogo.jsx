import React, { useId } from 'react';

/**
 * InfinityOps brand mark — infinity loop + orbital node.
 */
export default function InfinityOpsLogo({
  size = 32,
  className = '',
  title = 'InfinityOps',
}) {
  const uid = useId().replace(/:/g, '');
  const bgId = `io-bg-${uid}`;
  const shineId = `io-shine-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{title}</title>
      <defs>
        <linearGradient id={bgId} x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#0ea5e9" />
          <stop offset="100%" stopColor="#6366f1" />
        </linearGradient>
        <linearGradient id={shineId} x1="6" y1="4" x2="26" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill={`url(#${bgId})`} />
      <rect x="1" y="1" width="30" height="30" rx="9" fill={`url(#${shineId})`} />
      <path
        d="M10.5 16c0-2.8 2.2-4.5 4.5-4.5 1.6 0 2.8.7 3.5 1.8M21.5 16c0 2.8-2.2 4.5-4.5 4.5-1.6 0-2.8-.7-3.5-1.8"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14.2 13.8c1.4-1.2 3.4-1.2 4.8 0 1.4 1.2 1.4 3.1 0 4.3-1.4 1.2-3.4 1.2-4.8 0"
        fill="none"
        stroke="#e0f2fe"
        strokeWidth="1.65"
        strokeLinecap="round"
      />
      <circle cx="23.5" cy="8.5" r="2.35" fill="#bae6fd" />
      <circle cx="23.5" cy="8.5" r="1.1" fill="#ffffff" />
    </svg>
  );
}

export function InfinityOpsWordmark({ className = '' }) {
  return (
    <div className={`sidebar-logo__text${className ? ` ${className}` : ''}`}>
      Infinity<span>Ops</span>
    </div>
  );
}
