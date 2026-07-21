import React from 'react';
import InsightCanvasSections from './InsightCanvasSections';
import InsightSkuPanel from './InsightSkuPanel';
import { CANVAS_SECTION_DEFS } from '../../utils/insightCanvasUtils';
import useInsightScrollSpy, { scrollToInsightSection } from '../../hooks/useInsightScrollSpy';

export default function InsightCanvasLayout({ data }) {
  const sections = data?.sections || [];
  const sectionIds = sections.map((s) => `section-${s}`);
  useInsightScrollSpy(sectionIds);

  const layoutClass = `ic-layout ic-layout--${data?.profileType || 'vm'} ic-layout--${data?.severityKey || 'medium'}`;

  return (
    <>
      <div className="ic-chip-nav" role="navigation" aria-label="Sections">
        {sections.map((sectionId, idx) => {
          const def = CANVAS_SECTION_DEFS[sectionId] || { nav: sectionId };
          const anchor = `section-${sectionId}`;
          return (
            <a
              key={sectionId}
              href={`#${anchor}`}
              className={`ic-chip-nav__item${idx === 0 ? ' active' : ''}`}
              data-section={anchor}
              title={def.nav}
              onClick={(e) => {
                e.preventDefault();
                scrollToInsightSection(anchor);
              }}
            >
              {def.nav}
            </a>
          );
        })}
      </div>
      <div className={layoutClass} id="ic-layout">
        <nav className="ic-nav" aria-label="Sections">
          <p className="ic-nav__label section-title--compact">Sections</p>
          <ul className="ic-nav__list">
            {sections.map((sectionId, idx) => {
              const def = CANVAS_SECTION_DEFS[sectionId] || { nav: sectionId };
              const anchor = `section-${sectionId}`;
              return (
                <li key={sectionId}>
                  <a
                    href={`#${anchor}`}
                    className={`ic-nav__link${idx === 0 ? ' active' : ''}`}
                    data-section={anchor}
                    title={def.nav}
                    onClick={(e) => {
                      e.preventDefault();
                      scrollToInsightSection(anchor);
                    }}
                  >
                    {def.nav}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>
        <InsightCanvasSections data={data} />
        <InsightSkuPanel data={data} />
      </div>
    </>
  );
}
