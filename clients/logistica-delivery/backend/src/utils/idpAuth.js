const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');

let cachedPublicKey = null;

function getPublicKey() {
  if (cachedPublicKey) return cachedPublicKey;

  const configuredPath = process.env.IDP_PUBLIC_KEY_PATH
    ? path.resolve(process.cwd(), process.env.IDP_PUBLIC_KEY_PATH)
    : null;
  const fallbackPath = path.resolve(__dirname, '../../../../../backend/secrets/public.pem');
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

function deriveClientRole(claims) {
  const appRoles = Array.isArray(claims.app_roles)
    ? claims.app_roles.map((item) => String(item).toLowerCase())
    : [];

  const adminRoles = getConfiguredRoleList(process.env.LOGISTICA_ADMIN_APP_ROLES, ['admin', 'app:admin']);
  const deliveryAgentRoles = getConfiguredRoleList(
    process.env.LOGISTICA_DELIVERY_AGENT_APP_ROLES,
    ['delivery_agent', 'agent', 'app:delivery_agent']
  );
  const endUserRoles = getConfiguredRoleList(
    process.env.LOGISTICA_END_USER_APP_ROLES,
    ['end_user', 'customer', 'user', 'app:end_user']
  );

  if (appRoles.some((role) => adminRoles.includes(role))) return 'admin';
  if (appRoles.some((role) => deliveryAgentRoles.includes(role))) return 'delivery_agent';
  if (appRoles.some((role) => endUserRoles.includes(role))) return 'end_user';

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
  deriveClientRole,
  verifyIdpToken
};
