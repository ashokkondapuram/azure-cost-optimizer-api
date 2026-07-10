import React, { useEffect, useRef, useState } from 'react';
import { Zap } from 'lucide-react';

const TYPE_MS = 22;

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  return reduced;
}

function useTypewriter(text, active, reducedMotion) {
  const [displayed, setDisplayed] = useState('');
  const timerRef = useRef(null);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (!active) {
      setDisplayed('');
      return undefined;
    }

    if (reducedMotion) {
      setDisplayed(text);
      return undefined;
    }

    setDisplayed('');
    let index = 0;
    timerRef.current = setInterval(() => {
      index += 1;
      setDisplayed(text.slice(0, index));
      if (index >= text.length && timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }, TYPE_MS);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [active, text, reducedMotion]);

  const complete = active && displayed.length >= text.length;
  return { displayed, complete };
}

export function LoginHeroTitleBlock({
  id,
  title,
  reveals,
  reveal,
  className = '',
  blockClassName = '',
}) {
  const variants = reveals?.length ? reveals : (reveal ? [reveal] : []);
  const splitAt = title.lastIndexOf(' ');
  const reducedMotion = usePrefersReducedMotion();
  const [active, setActive] = useState(false);
  const [variantIndex, setVariantIndex] = useState(() => (
    variants.length ? Math.floor(Math.random() * variants.length) : 0
  ));
  const currentReveal = variants[variantIndex] || variants[0] || {};
  const { displayed, complete } = useTypewriter(currentReveal.headline || '', active, reducedMotion);
  const hintId = 'login-optimization-hint';

  const openReveal = () => {
    setActive((wasActive) => {
      if (!wasActive && variants.length > 1) {
        setVariantIndex((prev) => (prev + 1) % variants.length);
      }
      return true;
    });
  };

  const closeReveal = () => setActive(false);

  if (splitAt <= 0) {
    return (
      <h1 id={id} className={className}>
        {title}
      </h1>
    );
  }

  const accent = title.slice(splitAt + 1);
  const typing = active && !complete && displayed.length > 0;

  return (
    <div
      className={`login-hero__title-block${blockClassName ? ` ${blockClassName}` : ''}`}
      onMouseEnter={openReveal}
      onMouseLeave={closeReveal}
      onFocusCapture={openReveal}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) closeReveal();
      }}
    >
      <h1 id={id} className={className}>
        {title.slice(0, splitAt)}{' '}
        <span
          className="login-hero__title-accent"
          tabIndex={0}
          role="button"
          aria-describedby={active ? hintId : undefined}
          aria-expanded={active}
        >
          {accent}
        </span>
      </h1>

      <div
        id={hintId}
        className={`login-hero__optimization-reveal${active ? ' login-hero__optimization-reveal--open' : ''}`}
        aria-hidden={!active}
      >
        <div className="login-hero__optimization-reveal-inner">
          <div className="login-hero__optimization-reveal-head">
            <span className="login-hero__optimization-reveal-icon" aria-hidden>
              <Zap size={14} />
            </span>
            <span className="login-hero__optimization-reveal-eyebrow">{currentReveal.eyebrow}</span>
          </div>
          <p className="login-hero__optimization-reveal-headline">
            <span>{displayed}</span>
            {(typing || (active && complete)) && (
              <span className="login-hero__optimization-cursor" aria-hidden />
            )}
          </p>
          <ul
            className={`login-hero__optimization-reveal-list${complete ? ' login-hero__optimization-reveal-list--visible' : ''}`}
          >
            {(currentReveal.bullets || []).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/** @deprecated Use LoginHeroTitleBlock */
export function LoginHeroTitle({ title, optimizationHint }) {
  return (
    <>
      {title.slice(0, title.lastIndexOf(' '))}{' '}
      <span className="login-hero__title-accent">{title.slice(title.lastIndexOf(' ') + 1)}</span>
      <span className="sr-only">{optimizationHint}</span>
    </>
  );
}
