import { useEffect } from 'react';

let lockCount = 0;
let savedScrollY = 0;
let savedStyles = null;

/** Apply fixed-body scroll lock and return a restore function. Ref-counted for nested drawers / Strict Mode. */
export function lockBodyScroll(scrollY = window.scrollY) {
  if (lockCount === 0) {
    savedScrollY = scrollY;
    const { style } = document.body;
    savedStyles = {
      overflow: style.overflow,
      position: style.position,
      top: style.top,
      left: style.left,
      right: style.right,
      width: style.width,
      paddingRight: style.paddingRight,
    };
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    style.overflow = 'hidden';
    style.position = 'fixed';
    style.top = `-${scrollY}px`;
    style.left = '0';
    style.right = '0';
    style.width = '100%';
    if (scrollbarWidth > 0) {
      style.paddingRight = `${scrollbarWidth}px`;
    }
  }

  lockCount += 1;

  return () => {
    lockCount = Math.max(0, lockCount - 1);
    if (lockCount > 0 || !savedStyles) return;

    const { style } = document.body;
    style.overflow = savedStyles.overflow;
    style.position = savedStyles.position;
    style.top = savedStyles.top;
    style.left = savedStyles.left;
    style.right = savedStyles.right;
    style.width = savedStyles.width;
    style.paddingRight = savedStyles.paddingRight;
    window.scrollTo(0, savedScrollY);
    savedStyles = null;
  };
}

/** Lock document scroll without jumping to the top (for modals/drawers). */
export default function useBodyScrollLock(active = true) {
  useEffect(() => {
    if (!active) return undefined;
    return lockBodyScroll();
  }, [active]);
}
