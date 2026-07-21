import { useState, useCallback } from 'react';

const STORAGE_KEY = 'insight-drawer-width';
const DEFAULT_WIDTH = 440;
const MIN_WIDTH = 320;
const MAX_WIDTH = 900;

function readStoredWidth() {
  try {
    const value = Number(localStorage.getItem(STORAGE_KEY));
    const max = Math.min(window.innerWidth * 0.96, MAX_WIDTH);
    if (value >= MIN_WIDTH && value <= max) return value;
  } catch {
    /* ignore */
  }
  return DEFAULT_WIDTH;
}

/** Drag the left edge of the insight drawer to resize width. */
export default function useResizableDrawerWidth() {
  const [width, setWidth] = useState(readStoredWidth);

  const onResizeStart = useCallback((event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const maxW = Math.min(window.innerWidth * 0.96, MAX_WIDTH);
    let latest = startWidth;

    const onMove = (moveEvent) => {
      latest = Math.min(maxW, Math.max(MIN_WIDTH, startWidth + (startX - moveEvent.clientX)));
      setWidth(latest);
    };

    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.classList.remove('insight-drawer--resizing');
      try {
        localStorage.setItem(STORAGE_KEY, String(latest));
      } catch {
        /* ignore */
      }
    };

    document.body.classList.add('insight-drawer--resizing');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [width]);

  return { width, onResizeStart, minWidth: MIN_WIDTH };
}
