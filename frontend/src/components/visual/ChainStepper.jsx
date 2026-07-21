import React from 'react';

export default function ChainStepper({ step, total }) {
  const n = Number(total) || 0;
  const current = Number(step) || 1;
  if (n <= 1) return null;
  return (
    <div className="chain-stepper" aria-label={`Step ${current} of ${n}`}>
      {Array.from({ length: n }, (_, i) => {
        const idx = i + 1;
        const mod = idx < current ? 'done' : idx === current ? 'active' : '';
        return (
          <div key={idx} className={`chain-step ${mod}`}>
            {idx}
          </div>
        );
      })}
    </div>
  );
}
