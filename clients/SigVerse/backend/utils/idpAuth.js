const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');

let cachedPublicKey = null;

function getPublicKey() {
  if (cachedPublicKey) return cachedPublicKey;

  const configuredPath = process.env.IDP_PUBLIC_KEY_PATH
    ? path.resolve(process.cwd(), process.env.IDP_PUBLIC_KEY_PATH)
    : null;
  const fallbackPath = path.resolve(__dirname, '../../../../backend/secrets/public.pem');
  const publicKeyPath = configuredPath && fs.existsSync(configuredPath)
    ? configuredPath
    : fallbackPath;

  cachedPublicKey = fs.readFileSync(publicKeyPath, 'utf8');
  return cachedPublicKey;
}

function getConfiguredRoleList(value, fallback = []) {
  const source = value || fallback.join(',');
  return source
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function deriveSigVerseRole(claims) {
  const appRoles = Array.isArray(claims.app_roles) ? claims.app_roles.map((item) => String(item).toLowerCase()) : [];
  const adminAppRoles = getConfiguredRoleList(process.env.SIGVERSE_ADMIN_APP_ROLES, ['app:admin', 'admin']);
  const instructorAppRoles = getConfiguredRoleList(process.env.SIGVERSE_INSTRUCTOR_APP_ROLES, ['app:instructor', 'instructor']);
  const learnerAppRoles = getConfiguredRoleList(process.env.SIGVERSE_LEARNER_APP_ROLES, ['app:learner', 'learner']);

  if (appRoles.some((role) => adminAppRoles.includes(role))) return 'admin';
  if (appRoles.some((role) => instructorAppRoles.includes(role))) return 'instructor';
  if (appRoles.some((role) => learnerAppRoles.includes(role))) return 'learner';

  return null;
}

function verifyIdpToken(token) {
  const audience = process.env.IDP_CLIENT_ID;
  if (!audience) {
    const err = new Error('IDP_CLIENT_ID is not configured');
    err.status = 500;
    throw err;
  }

  return jwt.verify(token, getPublicKey(), {
    algorithms: ['RS256'],
    issuer: process.env.IDP_ISSUER_URL || 'http://localhost:8000',
    audience
  });
}

module.exports = {
  deriveSigVerseRole,
  verifyIdpToken
};
