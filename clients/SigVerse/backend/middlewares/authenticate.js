const jwt = require('jsonwebtoken');
const { sendError } = require('../utils/response');
const UserRepository = require('../repositories/UserRepository');
const { deriveSigVerseRole, verifyIdpToken } = require('../utils/idpAuth');
const { readSessionFromRequest } = require('../../../shared/sessionAuth');

const SESSION_COOKIE_NAME = process.env.APP_SESSION_COOKIE_NAME || 'sigverse_session';
const SESSION_SECRET = process.env.APP_SESSION_SECRET || 'sigverse-dev-session-secret';

module.exports = async (req, res, next) => {
  const cookieSession = readSessionFromRequest(req, {
    secret: SESSION_SECRET,
    cookieName: SESSION_COOKIE_NAME,
  });
  if (cookieSession?.user) {
    req.user = cookieSession.user;
    return next();
  }

  const authHeader = req.headers['authorization'];
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return sendError(res, 401, 'No token provided');
  }
  const token = authHeader.split(' ')[1];
  try {
    let decoded;
    let localUser = null;

    try {
      decoded = verifyIdpToken(token);
      const role = deriveSigVerseRole(decoded);
      const email = String(decoded.email || '').trim().toLowerCase();
      const name = decoded.name || email || 'SigVerse User';

      if (!email) {
        return sendError(res, 401, 'IDP token does not include an email');
      }
      if (!role) {
        return sendError(res, 403, 'No recognized SigVerse application role was issued for this account.');
      }

      localUser = await UserRepository.findByEmail(email);
      if (!localUser) {
        localUser = await UserRepository.create({
          name,
          email,
          role
        });
      } else if (localUser.role !== role || localUser.name !== name) {
        localUser = await UserRepository.patch(localUser.id, { role, name });
      }

      req.user = {
        sub: localUser.id,
        external_sub: decoded.sub,
        email,
        role: localUser.role,
        name: localUser.name,
        app_roles: decoded.app_roles || [],
        groups: decoded.groups || [],
        app_groups: decoded.app_groups || []
      };
      return next();
    } catch (idpError) {
      decoded = jwt.verify(token, process.env.JWT_SECRET);
      req.user = decoded; // { sub, email, role }
      return next();
    }

    next();
  } catch (err) {
    return sendError(res, 401, 'Invalid or expired token');
  }
};
