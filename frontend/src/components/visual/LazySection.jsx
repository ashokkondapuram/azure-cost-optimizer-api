import React, { useEffect, useRef, useState } from 'react';
import SectionSkeleton from './SectionSkeleton';

export default function LazySection({
  title,
  children,
  onVisible,
  isLoading = false,
  showSkeleton = true,
  skeletonRows = 3
}) {
  const [hasBeenVisible, setHasBeenVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    if (!sectionRef.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasBeenVisible) {
          setHasBeenVisible(true);
          onVisible?.();
        }
      },
      { threshold: 0.1, rootMargin: '50px' }
    );

    observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, [hasBeenVisible, onVisible]);

  return (
    <section ref={sectionRef} className="lazy-section">
      {title && <h3 className="lazy-section__title">{title}</h3>}
      <div className="lazy-section__content">
        {hasBeenVisible ? (
          <>
            {isLoading && showSkeleton && <SectionSkeleton rows={skeletonRows} />}
            {!isLoading && children}
          </>
        ) : (
          showSkeleton && <SectionSkeleton rows={skeletonRows} />
        )}
      </div>
    </section>
  );
}
