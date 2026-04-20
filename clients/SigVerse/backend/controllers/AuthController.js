const { sendSuccess, sendError } = require('../utils/response');
const LogService = require('../services/LogService');
const UserService = require('../services/UserService');
const BootstrapService = require('../services/BootstrapService');
const UserRepository = require('../repositories/UserRepository');
const { deriveSigVerseRole } = require('../utils/idpAuth');
const {
  buildClearSessionCookie,
  buildIdpLogoutUrl,
  buildSessionCookie,
  createSessionToken,
  exchangeAuthorizationCode,
  fetchUserInfo,
} = require('../../../shared/sessionAuth');

const IDP_ISSUER_URL = process.env.IDP_ISSUER_URL || 'http://localhost:8000';
const IDP_CLIENT_ID = process.env.IDP_CLIENT_ID || '';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3101';
const IDP_REDIRECT_URI = process.env.IDP_REDIRECT_URI || `${FRONTEND_URL}/auth/callback`;
const POST_LOGOUT_REDIRECT_URI = process.env.POST_LOGOUT_REDIRECT_URI || FRONTEND_URL;
const SESSION_COOKIE_NAME = process.env.APP_SESSION_COOKIE_NAME || 'sigverse_session';
const SESSION_SECRET = process.env.APP_SESSION_SECRET || 'sigverse-dev-session-secret';
const SESSION_TTL_SECONDS = Number(process.env.APP_SESSION_TTL_SECONDS || 60 * 60 * 8);
const SECURE_COOKIE = process.env.APP_SESSION_COOKIE_SECURE === 'true';

function sessionCookieOptions() {
  return {
    cookieName: SESSION_COOKIE_NAME,
    maxAge: SESSION_TTL_SECONDS,
    secure: SECURE_COOKIE,
  };
}

async function resolveLocalUserFromClaims(claims) {
  const role = deriveSigVerseRole(claims);
  const email = String(claims.email || '').trim().toLowerCase();
  const name = claims.name || email || 'SigVerse User';

  if (!email) {
    const error = new Error('IDP token does not include an email');
    error.status = 401;
    throw error;
  }
  if (!role) {
    const error = new Error('No recognized SigVerse application role was issued for this account. Ask your SigAuth administrator to configure an application role mapping.');
    error.status = 403;
    throw error;
  }

  let localUser = await UserRepository.findByEmail(email);
  if (!localUser) {
    localUser = await UserRepository.create({
      name,
      email,
      role
    });
  } else if (localUser.role !== role || localUser.name !== name) {
    localUser = await UserRepository.patch(localUser.id, { role, name });
  }

  return {
    sub: localUser.id,
    external_sub: claims.sub,
    email,
    role: localUser.role,
    name: localUser.name,
    app_roles: claims.app_roles || [],
    groups: claims.groups || [],
    app_groups: claims.app_groups || [],
  };
}

function sendIdpOnly(res) {
  return sendError(
    res,
    410,
    'SigVerse now uses SigAuth only. Sign in through the IdP flow.',
    ['Use /login in the SigVerse frontend and continue with SigAuth.']
  );
}

exports.idpOnlyUnavailable = async (req, res) => sendIdpOnly(res);

exports.githubAuth = (req, res) => sendIdpOnly(res);

exports.githubCallback = (req, res) => {
  return sendIdpOnly(res);
};

exports.localLogin = async (req, res) => {
  return sendIdpOnly(res);
};

exports.localSignup = async (req, res) => {
  return sendIdpOnly(res);
};

exports.verifyLoginOtp = async (req, res) => {
  return sendIdpOnly(res);
};

exports.verifySignupOtp = async (req, res) => {
  return sendIdpOnly(res);
};

exports.forgotPassword = async (req, res) => {
  return sendIdpOnly(res);
};

exports.resetPassword = async (req, res) => {
  return sendIdpOnly(res);
};

exports.demoUsers = async (req, res, next) => {
  try {
    sendSuccess(res, 200, BootstrapService.getDemoAccounts());
  } catch (err) { next(err); }
};

exports.idpExchange = async (req, res, next) => {
  try {
    const { code, codeVerifier } = req.body || {};
    if (!code) return sendError(res, 400, 'Authorization code is required');

    const tokenSet = await exchangeAuthorizationCode({
      issuerUrl: IDP_ISSUER_URL,
      clientId: IDP_CLIENT_ID,
      redirectUri: IDP_REDIRECT_URI,
      code,
      codeVerifier,
    });
    const accessToken = tokenSet.access_token || tokenSet.id_token;
    const claims = await fetchUserInfo({
      issuerUrl: IDP_ISSUER_URL,
      accessToken,
    });

    const sessionUser = await resolveLocalUserFromClaims(claims);
    const sessionToken = createSessionToken({ user: sessionUser }, SESSION_SECRET, SESSION_TTL_SECONDS);
    res.setHeader('Set-Cookie', buildSessionCookie(sessionToken, sessionCookieOptions()));
    sendSuccess(res, 200, sessionUser, 'SigAuth session established');
  } catch (err) {
    next(err);
  }
};

exports.logoutUrl = async (req, res, next) => {
  try {
    sendSuccess(res, 200, {
      logoutUrl: buildIdpLogoutUrl({
        issuerUrl: IDP_ISSUER_URL,
        clientId: IDP_CLIENT_ID,
        postLogoutRedirectUri: POST_LOGOUT_REDIRECT_URI,
      }),
    });
  } catch (err) { next(err); }
};

exports.getMe = async (req, res, next) => {
  try {
    const user = await UserService.getById(req.user.sub);
    if (!user) return sendError(res, 404, 'User not found');
    sendSuccess(res, 200, user);
  } catch (err) { next(err); }
};

exports.logout = async (req, res, next) => {
  try {
    if (req.user?.sub) {
      await LogService.logActivity({
        user_id: req.user.sub,
        action: 'logout',
        module: 'auth',
        metadata: {},
        timestamp: new Date()
      });
    }
    res.setHeader('Set-Cookie', buildClearSessionCookie(sessionCookieOptions()));
    sendSuccess(res, 200, null, 'Logged out successfully');
  } catch (err) { next(err); }
};
