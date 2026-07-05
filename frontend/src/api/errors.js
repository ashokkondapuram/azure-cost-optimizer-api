/** Normalized API error helpers for consistent UI messaging. */

import { toDisplayText } from '../utils/formatDisplay';

export function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (!error) return fallback;

  const data = error.response?.data;
  if (typeof data === 'string' && data.trim()) return data;
  if (data?.error?.message) return data.error.message;
  if (data?.detail != null) {
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
    }
    if (typeof data.detail === 'object') {
      const text = toDisplayText(data.detail);
      if (text !== '—') return text;
    }
  }
  if (data?.message) return data.message;
  if (error.code === 'ECONNABORTED') return 'Request timed out. Please try again.';
  if (!error.response) return 'Cannot reach the API. Check that the backend is running.';
  if (error.response.status === 401) return 'Your session ended. Sign in again.';
  if (error.response.status === 403) return 'You do not have permission to access this resource.';
  if (error.response.status === 404) return 'The requested resource was not found.';
  if (error.response.status >= 500) return 'Server error. Please try again later.';
  return fallback;
}

export function isNetworkError(error) {
  return !error?.response;
}
