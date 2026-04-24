const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { URL } = require('url');
const {
  buildClearSessionCookie,
  buildIdpLogoutUrl,
  buildSessionCookie,
  exchangeAuthorizationCode,
  fetchUserInfo,
  getJwtExpiry,
  maybeRefreshIdpSession,
  refreshAuthorizationTokens,
} = require('../../shared/sessionAuth');

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const separatorIndex = line.indexOf('=');
    if (separatorIndex === -1) continue;
    const key = line.slice(0, separatorIndex).trim();
    if (!key || Object.prototype.hasOwnProperty.call(process.env, key)) continue;
    let value = line.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

loadEnvFile(path.join(__dirname, '.env'));

const PORT = Number(process.env.PORT || 4003);
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:4000';
const IDP_ISSUER_URL = process.env.IDP_ISSUER_URL || 'http://localhost:8000';
const IDP_CLIENT_ID = process.env.IDP_CLIENT_ID || 'hr-portal-client-id';
const IDP_CLIENT_SECRET = process.env.IDP_CLIENT_SECRET || '';
const IDP_REDIRECT_URI = process.env.IDP_REDIRECT_URI || `http://localhost:${PORT}/auth/callback`;
const POST_LOGOUT_REDIRECT_URI = process.env.POST_LOGOUT_REDIRECT_URI || FRONTEND_URL;
const SESSION_COOKIE_NAME = process.env.APP_SESSION_COOKIE_NAME || 'hr_portal_session';
const SESSION_SECRET = process.env.APP_SESSION_SECRET || 'hr-portal-dev-session-secret';
const SESSION_TTL_SECONDS = Number(process.env.APP_SESSION_TTL_SECONDS || 60 * 60 * 8);
const SECURE_COOKIE = process.env.APP_SESSION_COOKIE_SECURE === 'true';
const OAUTH_STATE_COOKIE_NAME = process.env.OAUTH_STATE_COOKIE_NAME || 'hr_portal_oauth_state';
const serverSessions = new Map();

function sendJson(res, status, payload, extraHeaders = {}) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': FRONTEND_URL,
    'Access-Control-Allow-Credentials': 'true',
    ...extraHeaders,
  });
  res.end(JSON.stringify(payload));
}

function sessionCookieOptions() {
  return {
    cookieName: SESSION_COOKIE_NAME,
    maxAge: SESSION_TTL_SECONDS,
    secure: SECURE_COOKIE,
  };
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

function buildOauthStateCookie(state) {
  return serializeCookie(OAUTH_STATE_COOKIE_NAME, state, {
    maxAge: 600,
    path: '/',
    httpOnly: true,
    sameSite: 'Lax',
    secure: SECURE_COOKIE,
  });
}

function clearOauthStateCookie() {
  return serializeCookie(OAUTH_STATE_COOKIE_NAME, '', {
    maxAge: 0,
    path: '/',
    httpOnly: true,
    sameSite: 'Lax',
    secure: SECURE_COOKIE,
  });
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

function redirectWithError(res, message) {
  const target = new URL(FRONTEND_URL);
  target.searchParams.set('error', message);
  res.writeHead(302, {
    Location: target.toString(),
    'Set-Cookie': clearOauthStateCookie(),
  });
  res.end();
}

function buildHrPortalSessionUser(claims) {
  return {
    name: claims?.name || claims?.email || 'HR Portal User',
    email: claims?.email || null,
    email_verified: !!claims?.email_verified,
    roles: Array.isArray(claims?.roles) ? claims.roles : [],
    org_id: claims?.org_id || null,
  };
}

function buildHrPortalIdpState(tokenSet = {}, existingState = {}) {
  const accessToken = tokenSet.access_token || existingState.accessToken || null;
  return {
    accessToken,
    accessTokenExp: getJwtExpiry(accessToken),
    refreshToken: tokenSet.refresh_token || existingState.refreshToken || null,
  };
}

function createServerSession(payload) {
  const sessionId = crypto.randomUUID();
  serverSessions.set(sessionId, {
    ...payload,
    expiresAt: Date.now() + (SESSION_TTL_SECONDS * 1000),
  });
  return sessionId;
}

function getServerSession(sessionId) {
  if (!sessionId) return null;
  const session = serverSessions.get(sessionId);
  if (!session) return null;
  if (session.expiresAt <= Date.now()) {
    serverSessions.delete(sessionId);
    return null;
  }
  return session;
}

function touchServerSession(sessionId, payload = {}) {
  const existing = getServerSession(sessionId);
  if (!existing) return null;
  const nextSession = {
    ...existing,
    ...payload,
    expiresAt: Date.now() + (SESSION_TTL_SECONDS * 1000),
  };
  serverSessions.set(sessionId, nextSession);
  return nextSession;
}

function destroyServerSession(sessionId) {
  if (!sessionId) return;
  serverSessions.delete(sessionId);
}

function getRequestSession(req) {
  const cookies = parseCookies(req.headers.cookie || '');
  const sessionId = cookies[SESSION_COOKIE_NAME];
  if (!sessionId) return { sessionId: null, session: null };
  return {
    sessionId,
    session: getServerSession(sessionId),
  };
}

setInterval(() => {
  const now = Date.now();
  for (const [sessionId, session] of serverSessions.entries()) {
    if (!session?.expiresAt || session.expiresAt <= now) {
      serverSessions.delete(sessionId);
    }
  }
}, 60 * 1000).unref();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': FRONTEND_URL,
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    });
    res.end();
    return;
  }

  try {
    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, { ok: true, service: 'hr-portal-backend' });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/auth/login') {
      if (!IDP_CLIENT_SECRET) {
        redirectWithError(
          res,
          'HR Portal is missing IDP_CLIENT_SECRET for confidential web-app login.'
        );
        return;
      }

      const state = crypto.randomUUID();
      const nonce = crypto.randomUUID();
      const params = new URLSearchParams({
        response_type: 'code',
        client_id: IDP_CLIENT_ID,
        redirect_uri: IDP_REDIRECT_URI,
        scope: 'openid profile email',
        state,
        nonce,
      });
      res.writeHead(302, {
        Location: `${IDP_ISSUER_URL}/api/v1/authorize?${params.toString()}`,
        'Set-Cookie': buildOauthStateCookie(state),
      });
      res.end();
      return;
    }

    if (req.method === 'GET' && url.pathname === '/auth/callback') {
      const code = url.searchParams.get('code');
      const state = url.searchParams.get('state');
      const cookies = parseCookies(req.headers.cookie || '');
      const expectedState = cookies[OAUTH_STATE_COOKIE_NAME];

      if (!code || !state) {
        redirectWithError(res, 'Authorization code is missing');
        return;
      }

      if (!expectedState || expectedState !== state) {
        redirectWithError(res, 'State mismatch — possible CSRF attack');
        return;
      }

      const tokenSet = await exchangeAuthorizationCode({
        issuerUrl: IDP_ISSUER_URL,
        clientId: IDP_CLIENT_ID,
        clientSecret: IDP_CLIENT_SECRET,
        redirectUri: IDP_REDIRECT_URI,
        code,
      });
      const accessToken = tokenSet.access_token || tokenSet.id_token;
      const userInfo = await fetchUserInfo({
        issuerUrl: IDP_ISSUER_URL,
        accessToken,
      });

      const sessionId = createServerSession(
        {
          user: buildHrPortalSessionUser(userInfo),
          idp: buildHrPortalIdpState(tokenSet),
        }
      );
      res.writeHead(302, {
        Location: FRONTEND_URL,
        'Set-Cookie': [
          buildSessionCookie(sessionId, sessionCookieOptions()),
          clearOauthStateCookie(),
        ],
      });
      res.end();
      return;
    }

    if (req.method === 'GET' && url.pathname === '/auth/session') {
      const { sessionId, session } = getRequestSession(req);
      if (!session?.user) {
        sendJson(res, 401, { error: 'Unauthorized' });
        return;
      }

      let nextUser = session.user;
      try {
        const refreshed = await maybeRefreshIdpSession({
          session,
          issuerUrl: IDP_ISSUER_URL,
          clientId: IDP_CLIENT_ID,
          clientSecret: IDP_CLIENT_SECRET,
        });
        const claims = await fetchUserInfo({
          issuerUrl: IDP_ISSUER_URL,
          accessToken: refreshed.session.idp.accessToken,
        });
        nextUser = {
          ...buildHrPortalSessionUser(claims),
          claims,
        };
        if (refreshed.refreshed) {
          touchServerSession(sessionId, {
            ...refreshed.session,
            user: buildHrPortalSessionUser(claims),
            idp: buildHrPortalIdpState(refreshed.tokenSet || {}, refreshed.session.idp),
          });
          sendJson(
            res,
            200,
            { user: nextUser },
            { 'Set-Cookie': buildSessionCookie(sessionId, sessionCookieOptions()) }
          );
          return;
        }
        touchServerSession(sessionId, { user: buildHrPortalSessionUser(claims) });
      } catch (_error) {
        destroyServerSession(sessionId);
        sendJson(
          res,
          401,
          { error: 'Session expired. Please sign in again.' },
          { 'Set-Cookie': buildClearSessionCookie(sessionCookieOptions()) }
        );
        return;
      }

      sendJson(res, 200, { user: nextUser });
      return;
    }

    if (req.method === 'POST' && url.pathname === '/auth/logout') {
      const { sessionId } = getRequestSession(req);
      destroyServerSession(sessionId);
      sendJson(
        res,
        204,
        {},
        { 'Set-Cookie': buildClearSessionCookie(sessionCookieOptions()) }
      );
      return;
    }

    if (req.method === 'GET' && url.pathname === '/auth/logout-url') {
      const { session } = getRequestSession(req);
      let idTokenHint = null;

      if (session?.idp?.refreshToken) {
        try {
          const refreshed = await refreshAuthorizationTokens({
            issuerUrl: IDP_ISSUER_URL,
            clientId: IDP_CLIENT_ID,
            clientSecret: IDP_CLIENT_SECRET,
            refreshToken: session.idp.refreshToken,
          });
          idTokenHint = refreshed.id_token || null;
        } catch {
          idTokenHint = null;
        }
      }

      sendJson(res, 200, {
        logoutUrl: buildIdpLogoutUrl({
          issuerUrl: IDP_ISSUER_URL,
          clientId: IDP_CLIENT_ID,
          postLogoutRedirectUri: POST_LOGOUT_REDIRECT_URI,
          idTokenHint,
        }),
      });
      return;
    }

    sendJson(res, 404, { error: 'Not found' });
  } catch (error) {
    if (req.method === 'GET' && url.pathname === '/auth/callback') {
      redirectWithError(res, error.message || 'Unexpected server error');
      return;
    }
    sendJson(res, 500, { error: error.message || 'Unexpected server error' });
  }
});

server.listen(PORT, () => {
  console.log(`HR Portal backend listening on http://localhost:${PORT}`);
});
