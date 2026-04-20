const { readSessionFromRequest } = require('../../../../shared/sessionAuth');

const SESSION_COOKIE_NAME = process.env.APP_SESSION_COOKIE_NAME || 'logistica_session';
const SESSION_SECRET = process.env.APP_SESSION_SECRET || 'logistica-dev-session-secret';

function authenticateRequest(req, res, next) {
  const session = readSessionFromRequest(req, {
    secret: SESSION_SECRET,
    cookieName: SESSION_COOKIE_NAME,
  });

  if (!session?.user) {
    return res.status(401).json({
      error: 'Unauthorized',
    });
  }

  if (!session.user.clientRole) {
    return res.status(403).json({
      error: 'No recognized application role is attached to this session.',
    });
  }

  req.user = session.user;
  req.clientRole = session.user.clientRole;
  next();
}

module.exports = {
  authenticateRequest,
};
