import axios from 'axios';
import { LOGOUT_SYNC_KEY, clearStoredAuth } from '../utils/authStorage';
import { pushToast } from '../utils/toastBus';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

const RESOURCE_LABELS = {
  organizations: 'Organization',
  users: 'User',
  groups: 'Group',
  applications: 'Application',
  roles: 'Role',
  sessions: 'Session',
  notifications: 'Notification',
  'role-mappings': 'Role mapping',
  'email-deliveries': 'Email delivery',
  subscription: 'Subscription',
  billing: 'Subscription',
  preferences: 'Preferences',
};

const ACTION_MESSAGES = {
  disable: 'disabled successfully',
  enable: 'enabled successfully',
  activate: 'activated successfully',
  suspend: 'suspended successfully',
  'rotate-secret': 'secret rotated successfully',
  'cancel-at-period-end': 'will end at the close of the current billing cycle',
  resume: 'resumed successfully',
  'verify-enterprise': 'moved to verified enterprise successfully',
  'set-limited': 'moved to limited tier successfully',
  approve: 'approved successfully',
  reject: 'rejected successfully',
  read: 'updated successfully',
  'read-all': 'updated successfully',
  'checkout-complete': 'updated successfully',
  'revoke-sessions': 'sessions revoked successfully',
  unlock: 're-enabled successfully',
  'reset-password': 'password reset email queued successfully',
  'upgrade-request': 'upgrade request submitted successfully',
};

function shouldHandleMutationToast(config) {
  const method = String(config?.method || 'get').toLowerCase();
  const url = String(config?.url || '');
  if (!['post', 'put', 'patch', 'delete'].includes(method)) return false;
  if (config?.skipToast) return false;
  if (
    url.includes('/api/v1/login') ||
    url.includes('/api/v1/signup') ||
    url.includes('/password-reset') ||
    url.includes('/setup-password') ||
    url.includes('/api/v1/token') ||
    url.includes('/api/v1/authorize') ||
    url.endsWith('/logout')
  ) {
    return false;
  }
  return true;
}

function getResourceLabel(url) {
  const segments = String(url || '')
    .split('?')[0]
    .split('/')
    .filter(Boolean)
    .filter((segment) => !['api', 'v1', 'admin'].includes(segment) && !/^[0-9a-f-]{8,}$/i.test(segment));

  const lastCollection = [...segments].reverse().find((segment) => RESOURCE_LABELS[segment]);
  return RESOURCE_LABELS[lastCollection] || 'Record';
}

function buildSuccessMessage(config, response) {
  if (config?.toastSuccessMessage) return config.toastSuccessMessage;
  const responseMessage = response?.data?.message;
  if (typeof responseMessage === 'string' && responseMessage.trim()) return responseMessage;

  const url = String(config?.url || '').split('?')[0];
  const method = String(config?.method || 'get').toLowerCase();
  const action = url.split('/').filter(Boolean).pop();
  const resource = getResourceLabel(url);
  if (action && ACTION_MESSAGES[action]) {
    return `${resource} ${ACTION_MESSAGES[action]}.`;
  }
  if (method === 'post') return `${resource} created successfully.`;
  if (method === 'put' || method === 'patch') return `${resource} updated successfully.`;
  if (method === 'delete') return `${resource} deleted successfully.`;
  return 'Operation completed successfully.';
}

function buildErrorMessage(error) {
  return (
    error?.response?.data?.detail?.error_description ||
    error?.response?.data?.message ||
    error?.message ||
    'Something went wrong while saving your changes.'
  );
}

// Response interceptor: 401 → logout
api.interceptors.response.use(
  (response) => {
    if (shouldHandleMutationToast(response.config)) {
      pushToast({
        type: 'success',
        title: 'Success',
        message: buildSuccessMessage(response.config, response),
      });
    }
    return response;
  },
  (error) => {
    if (shouldHandleMutationToast(error.config) && !error.config?.skipErrorToast) {
      pushToast({
        type: 'error',
        title: 'Action failed',
        message: buildErrorMessage(error),
      });
    }
    const requestUrl = error.config?.url || '';
    const shouldIgnoreUnauthorizedRedirect =
      requestUrl.includes('/api/v1/login') ||
      requestUrl.includes('/api/v1/me/context') ||
      requestUrl.includes('/api/v1/me/profile');

    if (error.response?.status === 401 && !shouldIgnoreUnauthorizedRedirect) {
      clearStoredAuth();
      window.localStorage.setItem(LOGOUT_SYNC_KEY, String(Date.now()));
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
