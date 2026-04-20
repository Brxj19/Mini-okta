import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:3100',
  withCredentials: true,
});

api.interceptors.response.use(
  res => res,
  err => {
    const isAuthEndpoint = err.config?.url?.startsWith('/auth/');
    if (err.response?.status === 401 && !isAuthEndpoint) {
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;
