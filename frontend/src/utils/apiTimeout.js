/**
 * Reject when a promise does not settle within `timeoutMs`.
 * Used for auth/bootstrap calls that must not block the UI indefinitely.
 */
export function withTimeout(promise, timeoutMs, message = 'Request timed out') {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const err = new Error(message);
      err.code = 'TIMEOUT';
      reject(err);
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}
