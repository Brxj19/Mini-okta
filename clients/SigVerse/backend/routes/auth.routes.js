const router = require('express').Router();
const AuthController = require('../controllers/AuthController');
const authenticate = require('../middlewares/authenticate');
const logger = require('../middlewares/logger');

router.get('/github', AuthController.githubAuth);
router.get('/github/callback', AuthController.githubCallback);
router.post('/login', AuthController.localLogin);
router.post('/login/verify', AuthController.verifyLoginOtp);
router.post('/signup', AuthController.localSignup);
router.post('/signup/verify', AuthController.verifySignupOtp);
router.post('/forgot-password', AuthController.forgotPassword);
router.post('/reset-password', AuthController.resetPassword);
router.get('/demo-users', AuthController.demoUsers);
router.post('/idp/exchange', AuthController.idpExchange);
router.get('/logout-url', AuthController.logoutUrl);
router.get('/me', authenticate, logger, AuthController.getMe);
router.post('/logout', authenticate, logger, AuthController.logout);

module.exports = router;
