/**
 * Disk insight canvas — uses shared ic-layout with concept v2 disk data shape.
 */
import React from 'react';
import InsightCanvasBar from '../components/insight-canvas/InsightCanvasBar';
import InsightCanvasLayout from '../components/insight-canvas/InsightCanvasLayout';

export default function DiskInsightCanvas({
  data,
  positionLabel,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  subscriptionId,
  isAdmin,
  currency,
}) {
  if (!data) return null;
  return (
    <section className="ic-detail disk-v2" aria-label="Resource analysis">
      <InsightCanvasBar
        data={data}
        positionLabel={positionLabel}
        onPrev={onPrev}
        onNext={onNext}
        prevDisabled={prevDisabled}
        nextDisabled={nextDisabled}
        subscriptionId={subscriptionId}
        isAdmin={isAdmin}
        currency={currency}
      />
      <InsightCanvasLayout data={data} />
    </section>
  );
}
