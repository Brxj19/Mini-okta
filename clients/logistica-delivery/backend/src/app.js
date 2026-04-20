require('dotenv').config();

const cors = require('cors');
const express = require('express');
const morgan = require('morgan');

const { deriveClientRole } = require('./utils/idpAuth');
const { authenticateRequest } = require('./middlewares/authenticate');
const {
  buildClearSessionCookie,
  buildSessionCookie,
  buildIdpLogoutUrl,
  createSessionToken,
  exchangeAuthorizationCode,
  fetchUserInfo,
} = require('../../../shared/sessionAuth');

const app = express();

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:4101';
const IDP_ISSUER_URL = process.env.IDP_ISSUER_URL || 'http://localhost:8000';
const IDP_CLIENT_ID = process.env.IDP_CLIENT_ID || '';
const IDP_REDIRECT_URI = process.env.IDP_REDIRECT_URI || `${FRONTEND_URL}/auth/callback`;
const POST_LOGOUT_REDIRECT_URI = process.env.POST_LOGOUT_REDIRECT_URI || FRONTEND_URL;
const SESSION_COOKIE_NAME = process.env.APP_SESSION_COOKIE_NAME || 'logistica_session';
const SESSION_SECRET = process.env.APP_SESSION_SECRET || 'logistica-dev-session-secret';
const SESSION_TTL_SECONDS = Number(process.env.APP_SESSION_TTL_SECONDS || 60 * 60 * 8);
const SECURE_COOKIE = process.env.APP_SESSION_COOKIE_SECURE === 'true';

function sessionCookieOptions() {
  return {
    cookieName: SESSION_COOKIE_NAME,
    maxAge: SESSION_TTL_SECONDS,
    secure: SECURE_COOKIE,
  };
}

app.use(
  cors({
    origin: FRONTEND_URL,
    credentials: true,
  })
);
app.use(express.json());
app.use(morgan('dev'));

app.get('/health', (req, res) => {
  res.json({
    ok: true,
    service: 'logistica-delivery-backend',
    timestamp: new Date().toISOString()
  });
});

app.post('/auth/idp/exchange', async (req, res, next) => {
  try {
    const { code, codeVerifier } = req.body || {};
    if (!code) {
      return res.status(400).json({ error: 'Authorization code is required' });
    }

    const tokenSet = await exchangeAuthorizationCode({
      issuerUrl: IDP_ISSUER_URL,
      clientId: IDP_CLIENT_ID,
      redirectUri: IDP_REDIRECT_URI,
      code,
      codeVerifier,
    });
    const accessToken = tokenSet.access_token || tokenSet.id_token;
    const userInfo = await fetchUserInfo({
      issuerUrl: IDP_ISSUER_URL,
      accessToken,
    });

    const clientRole = deriveClientRole(userInfo);
    if (!clientRole) {
      return res.status(403).json({
        error: 'No recognized application role was issued for this account. Ask your SigAuth administrator to configure an application role mapping.',
      });
    }
    const organization = userInfo.org_name || userInfo.organization || userInfo.tenant || userInfo.org_id || null;
    const user = {
      sub: userInfo.sub,
      name: userInfo.name || userInfo.email || 'User',
      email: userInfo.email || null,
      organization,
      roles: Array.isArray(userInfo.roles) ? userInfo.roles : [],
      permissions: Array.isArray(userInfo.permissions) ? userInfo.permissions : [],
      appRoles: Array.isArray(userInfo.app_roles) ? userInfo.app_roles : [],
      clientRole,
    };

    const sessionToken = createSessionToken({ user }, SESSION_SECRET, SESSION_TTL_SECONDS);
    res.setHeader('Set-Cookie', buildSessionCookie(sessionToken, sessionCookieOptions()));
    res.json({ user });
  } catch (error) {
    next(error);
  }
});

app.get('/auth/session', authenticateRequest, (req, res) => {
  res.json({ user: req.user });
});

app.post('/auth/logout', (req, res) => {
  res.setHeader('Set-Cookie', buildClearSessionCookie(sessionCookieOptions()));
  res.status(204).end();
});

app.get('/auth/logout-url', (req, res) => {
  res.json({
    logoutUrl: buildIdpLogoutUrl({
      issuerUrl: IDP_ISSUER_URL,
      clientId: IDP_CLIENT_ID,
      postLogoutRedirectUri: POST_LOGOUT_REDIRECT_URI,
    }),
  });
});

app.get('/api/me', authenticateRequest, (req, res) => {
  res.json({
    user: req.user,
  });
});

app.use((err, req, res, next) => {
  if (!err) return next();

  const status = err.status || 500;
  res.status(status).json({
    error: err.message || 'Unexpected server error'
  });
});

module.exports = app;
