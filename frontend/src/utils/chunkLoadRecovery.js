const CHUNK_RELOAD_FLAG = 'costopt-chunk-reload';

export function isChunkLoadError(error) {
  const message = error?.message || String(error || '');
  return error?.name === 'ChunkLoadError' || /Loading chunk [\w./-]+ failed/i.test(message);
}

/** Reload once after a stale chunk failure (common after dev rebuilds or deploys). */
export function recoverFromChunkLoadError(error) {
  if (!isChunkLoadError(error)) return false;

  if (!sessionStorage.getItem(CHUNK_RELOAD_FLAG)) {
    sessionStorage.setItem(CHUNK_RELOAD_FLAG, '1');
    window.location.reload();
    return true;
  }

  sessionStorage.removeItem(CHUNK_RELOAD_FLAG);
  return false;
}

export function installChunkLoadRecovery() {
  window.addEventListener('unhandledrejection', (event) => {
    if (recoverFromChunkLoadError(event.reason)) {
      event.preventDefault();
    }
  });

  window.addEventListener('load', () => {
    sessionStorage.removeItem(CHUNK_RELOAD_FLAG);
  });
}
