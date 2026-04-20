import api from './api';

export const loginWithGithub = () => {
  window.location.href = `${import.meta.env.VITE_API_URL || 'http://localhost:3100'}/auth/github`;
};

const IDP_URL = import.meta.env.VITE_IDP_URL || 'http://localhost:8000';
const IDP_CLIENT_ID = import.meta.env.VITE_IDP_CLIENT_ID || '';
const IDP_REDIRECT_URI = import.meta.env.VITE_IDP_REDIRECT_URI || `${window.location.origin}/auth/callback`;

function generateCodeVerifier() {
  const arr = new Uint8Array(32);
  crypto.getRandomValues(arr);
  return btoa(String.fromCharCode(...arr)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function loginWithIdp() {
  if (!IDP_CLIENT_ID) {
    throw new Error('VITE_IDP_CLIENT_ID is not configured');
  }

  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = crypto.randomUUID();
  const nonce = crypto.randomUUID();

  sessionStorage.setItem('sigverse_oauth_state', state);
  sessionStorage.setItem('sigverse_code_verifier', codeVerifier);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: IDP_CLIENT_ID,
    redirect_uri: IDP_REDIRECT_URI,
    scope: 'openid profile email',
    state,
    nonce,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256'
  });

  window.location.href = `${IDP_URL}/api/v1/authorize?${params.toString()}`;
}

export async function exchangeIdpCode({ code, state }) {
  const savedState = sessionStorage.getItem('sigverse_oauth_state');
  const codeVerifier = sessionStorage.getItem('sigverse_code_verifier');

  if (state !== savedState) {
    throw new Error('State mismatch');
  }

  const response = await api.post('/auth/idp/exchange', {
    code,
    codeVerifier,
  });

  sessionStorage.removeItem('sigverse_oauth_state');
  sessionStorage.removeItem('sigverse_code_verifier');
  return response.data?.data;
}

export async function logoutFromIdp() {
  const response = await api.get('/auth/logout-url');
  const logoutUrl = response.data?.data?.logoutUrl;
  if (!logoutUrl) {
    throw new Error('Unable to resolve SigAuth logout URL');
  }
  window.location.assign(logoutUrl);
}

export const loginWithEmail = (data) => api.post('/auth/login', data);
export const signupWithEmail = (data) => api.post('/auth/signup', data);
export const verifyLoginOtp = (data) => api.post('/auth/login/verify', data);
export const verifySignupOtp = (data) => api.post('/auth/signup/verify', data);
export const requestPasswordReset = (data) => api.post('/auth/forgot-password', data);
export const resetPassword = (data) => api.post('/auth/reset-password', data);
export const getMe = () => api.get('/auth/me');

export const logout = async () => {
  return api.post('/auth/logout');
};
