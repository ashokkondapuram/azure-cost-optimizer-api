import { useEffect, useRef } from 'react';

export default function useInsightScrollSpy(sectionIds = []) {
  const activeRef = useRef(sectionIds[0] || null);

  useEffect(() => {
    if (!sectionIds.length) return undefined;

    const nodes = sectionIds
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    if (!nodes.length) return undefined;

    const getSpyOffset = () => {
      const firstSection = document.querySelector('.ic-section');
      const scrollMargin = firstSection
        ? parseFloat(getComputedStyle(firstSection).scrollMarginTop) || 96
        : 96;
      return scrollMargin + 8;
    };

    const setActive = (activeId) => {
      if (!activeId || activeRef.current === activeId) return;
      activeRef.current = activeId;
      document.querySelectorAll('.ic-nav__link, .ic-chip-nav__item').forEach((el) => {
        el.classList.toggle('active', el.dataset.section === activeId);
      });
    };

    const pickActiveSection = () => {
      const scrollRoot = document.scrollingElement || document.documentElement;
      const scrollBottom = scrollRoot.scrollTop + window.innerHeight;
      const docHeight = scrollRoot.scrollHeight;
      const lastId = sectionIds[sectionIds.length - 1];

      if (scrollBottom >= docHeight - 64) {
        setActive(lastId);
        return;
      }

      const spyOffset = getSpyOffset();
      let activeId = sectionIds[0];
      for (const id of sectionIds) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        if (top <= spyOffset) activeId = id;
      }
      setActive(activeId);
    };

    let rafId = 0;
    const schedulePick = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        pickActiveSection();
      });
    };

    window.addEventListener('scroll', schedulePick, { passive: true });
    window.addEventListener('resize', schedulePick, { passive: true });
    pickActiveSection();

    return () => {
      window.removeEventListener('scroll', schedulePick);
      window.removeEventListener('resize', schedulePick);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [sectionIds.join('|')]);
}

export function scrollToInsightSection(sectionId) {
  const target = document.getElementById(sectionId);
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
