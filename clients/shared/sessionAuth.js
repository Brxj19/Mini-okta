const crypto = require('crypto');

const DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 8;

function base64urlEncode(value) {
  return Buffer.from(value)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function base64urlDecode(value) {
  let normalized = String(value).replace(/-/g, '+').replace(/_/g, '/');
  while (normalized.length % 4) normalized += '=';
  return Buffer.from(normalized, 'base64').toString('utf8');
}

function signPayload(encodedPayload, secret) {
  return crypto
    .createHmac('sha256', secret)
    .update(encodedPayload)
    .digest('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function createSessionToken(payload, secret, ttlSeconds = DEFAULT_SESSION_TTL_SECONDS) {
  const body = {
    ...payload,
    exp: Math.floor(Date.now() / 1000) + ttlSeconds,
  };
  const encodedPayload = base64urlEncode(JSON.stringify(body));
  const signature = signPayload(encodedPayload, secret);
  return `${encodedPayload}.${signature}`;
}

function verifySessionToken(token, secret) {
  if (!token || !secret) return null;
  const [encodedPayload, providedSignature] = String(token).split('.');
  if (!encodedPayload || !providedSignature) return null;

  const expectedSignature = signPayload(encodedPayload, secret);
  const expected = Buffer.from(expectedSignature);
  const provided = Buffer.from(providedSignature);
  if (expected.length !== provided.length || !crypto.timingSafeEqual(expected, provided)) {
    return null;
  }

  try {
    const payload = JSON.parse(base64urlDecode(encodedPayload));
    if (!payload?.exp || payload.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

function parseCookies(cookieHeader = '') {
  return String(cookieHeader)
    .split(';')
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .reduce((acc, chunk) => {
      const index = chunk.indexOf('=');
      if (index === -1) return acc;
      const key = decodeURIComponent(chunk.slice(0, index).trim());
      const value = decodeURIComponent(chunk.slice(index + 1).trim());
      acc[key] = value;
      return acc;
    }, {});
}

function serializeCookie(name, value, options = {}) {
  const parts = [`${encodeURIComponent(name)}=${encodeURIComponent(value)}`];
  if (options.maxAge !== undefined) parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
  if (options.path) parts.push(`Path=${options.path}`);
  if (options.httpOnly) parts.push('HttpOnly');
  if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
  if (options.secure) parts.push('Secure');
  return parts.join('; ');
}

function buildSessionCookie(token, options = {}) {
  return serializeCookie(options.cookieName || 'app_session', token, {
    maxAge: options.maxAge ?? DEFAULT_SESSION_TTL_SECONDS,
    path: options.path || '/',
    httpOnly: true,
    sameSite: options.sameSite || 'Lax',
    secure: Boolean(options.secure),
  });
}

function buildClearSessionCookie(options = {}) {
  return serializeCookie(options.cookieName || 'app_session', '', {
    maxAge: 0,
    path: options.path || '/',
    httpOnly: true,
    sameSite: options.sameSite || 'Lax',
    secure: Boolean(options.secure),
  });
}

function readSessionFromRequest(req, { secret, cookieName = 'app_session' }) {
  const cookies = parseCookies(req.headers?.cookie || '');
  return verifySessionToken(cookies[cookieName], secret);
}

async function exchangeAuthorizationCode({
  issuerUrl,
  clientId,
  redirectUri,
  code,
  codeVerifier,
}) {
  const formData = new URLSearchParams();
  formData.set('grant_type', 'authorization_code');
  formData.set('code', code);
  formData.set('redirect_uri', redirectUri);
  formData.set('client_id', clientId);
  if (codeVerifier) formData.set('code_verifier', codeVerifier);

  const response = await fetch(`${issuerUrl}/api/v1/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString(),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error_description || 'Token exchange failed');
  }
  return data;
}

async function fetchUserInfo({ issuerUrl, accessToken }) {
  const response = await fetch(`${issuerUrl}/api/v1/userinfo`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error_description || data.detail?.error_description || 'Unable to load user info');
  }
  return data;
}

function buildIdpLogoutUrl({
  issuerUrl,
  clientId,
  postLogoutRedirectUri,
}) {
  const params = new URLSearchParams({
    client_id: clientId,
    post_logout_redirect_uri: postLogoutRedirectUri,
  });
  return `${issuerUrl}/api/v1/logout?${params.toString()}`;
}

module.exports = {
  DEFAULT_SESSION_TTL_SECONDS,
  buildClearSessionCookie,
  buildIdpLogoutUrl,
  buildSessionCookie,
  createSessionToken,
  exchangeAuthorizationCode,
  fetchUserInfo,
  parseCookies,
  readSessionFromRequest,
  verifySessionToken,
};
