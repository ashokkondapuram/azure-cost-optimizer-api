import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const msg = err?.response?.data?.error?.message
      || err?.response?.data?.detail
      || err?.message
      || 'Unknown error';
    return Promise.reject(new Error(msg));
  }
);

export default api;
