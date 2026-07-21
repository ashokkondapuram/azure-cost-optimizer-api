import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle } from 'lucide-react';
import { buildRecommendationTooltipContent } from '../utils/recommendationTooltip';

const SHOW_DELAY_MS = 120;

function TooltipFlyout({ id, tip, content, detailHint }) {
  if (!tip || !content.message) return null;

  return createPortal(
    <div
      id={id}
      className="rec-help-flyout"
      style={{ top: tip.top, left: tip.left }}
      role="tooltip"
    >
      <p className="rec-help-flyout__message">{content.message}</p>
      {content.metaParts.length > 0 && (
        <p className="rec-help-flyout__meta">{content.metaParts.join(' · ')}</p>
      )}
      {detailHint && (
        <p className="rec-help-flyout__hint">{detailHint}</p>
      )}
    </div>,
    document.body,
  );
}

/**
 * Hover/focus help affordance for recommendation headlines.
 * Shows a ? icon on hover and a portaled tooltip with full context.
 */
export default function RecommendationHelpTooltip({
  finding,
  children,
  compact = false,
  block = false,
  detailHint = null,
  className = '',
}) {
  const content = buildRecommendationTooltipContent(finding);
  const tooltipId = useId();
  const slotRef = useRef(null);
  const showTimerRef = useRef(null);
  const [tip, setTip] = useState(null);
  const [open, setOpen] = useState(false);

  const positionTip = useCallback(() => {
    const node = slotRef.current;
    if (!node) return null;
    const rect = node.getBoundingClientRect();
    const flyoutWidth = Math.min(320, window.innerWidth - 24);
    let left = rect.left;
    if (left + flyoutWidth > window.innerWidth - 12) {
      left = Math.max(12, window.innerWidth - flyoutWidth - 12);
    }
    return {
      top: rect.bottom + 8,
      left,
    };
  }, []);

  const showTip = useCallback(() => {
    if (!content.message) return;
    clearTimeout(showTimerRef.current);
    showTimerRef.current = setTimeout(() => {
      const next = positionTip();
      if (next) {
        setTip(next);
        setOpen(true);
      }
    }, SHOW_DELAY_MS);
  }, [content.message, positionTip]);

  const hideTip = useCallback(() => {
    clearTimeout(showTimerRef.current);
    setTip(null);
    setOpen(false);
  }, []);

  useEffect(() => {
    if (!open) return undefined;

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
  }, [open, positionTip, hideTip]);

  useEffect(() => () => clearTimeout(showTimerRef.current), []);

  if (!content.message) {
    return children ?? null;
  }

  const Wrapper = block ? 'div' : 'span';

  return (
    <>
      <Wrapper
        ref={slotRef}
        className={`rec-help${compact ? ' rec-help--compact' : ''}${block ? ' rec-help--block' : ''}${className ? ` ${className}` : ''}`}
        onMouseEnter={showTip}
        onMouseLeave={hideTip}
      >
        {block ? children : <span className="rec-help__text">{children}</span>}
        <button
          type="button"
          className="rec-help__trigger"
          aria-label={content.ariaLabel}
          aria-describedby={open ? tooltipId : undefined}
          onFocus={showTip}
          onBlur={hideTip}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <HelpCircle size={compact ? 12 : 13} aria-hidden />
        </button>
      </Wrapper>
      <TooltipFlyout
        id={tooltipId}
        tip={tip}
        content={content}
        detailHint={detailHint}
      />
    </>
  );
}
