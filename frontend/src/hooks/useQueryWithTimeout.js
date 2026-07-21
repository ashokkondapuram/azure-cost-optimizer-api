import { useQuery } from '@tanstack/react-query';

/**
 * Wrapper around useQuery that adds timeout handling.
 * If query times out, returns cached data or empty object without error.
 * @param {Object} options - React Query options + timeout, cacheTime
 * @param {number} options.timeout - Request timeout in ms (default: 3000)
 * @param {boolean} options.allowEmpty - Allow empty object on timeout (default: true)
 */
export default function useQueryWithTimeout({
  timeout = 3000,
  allowEmpty = true,
  ...queryOptions
}) {
  const originalFn = queryOptions.queryFn;

  const wrappedFn = async (...args) => {
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Query timeout')), timeout)
    );

    try {
      return await Promise.race([originalFn(...args), timeoutPromise]);
    } catch (err) {
      if (err.message === 'Query timeout') {
        if (allowEmpty) {
          return {};
        }
        throw err;
      }
      throw err;
    }
  };

  return useQuery({
    ...queryOptions,
    queryFn: wrappedFn,
    retry: 1,
  });
}
