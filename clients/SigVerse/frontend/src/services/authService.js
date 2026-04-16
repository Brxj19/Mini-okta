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

  const formData = new URLSearchParams();
  formData.set('grant_type', 'authorization_code');
  formData.set('code', code);
  formData.set('redirect_uri', IDP_REDIRECT_URI);
  formData.set('client_id', IDP_CLIENT_ID);
  if (codeVerifier) formData.set('code_verifier', codeVerifier);

  const response = await fetch(`${IDP_URL}/api/v1/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
  });
  const data = await response.json();
  if (!response.ok || !data.id_token) {
    throw new Error(data.error_description || 'Token exchange failed');
  }

  sessionStorage.removeItem('sigverse_oauth_state');
  sessionStorage.removeItem('sigverse_code_verifier');
  return data;
}

export function logoutFromIdp(idToken) {
  const params = new URLSearchParams({
    client_id: IDP_CLIENT_ID,
    post_logout_redirect_uri: window.location.origin,
  });
  if (idToken) {
    params.set('id_token_hint', idToken);
  }
  window.location.assign(`${IDP_URL}/api/v1/logout?${params.toString()}`);
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
