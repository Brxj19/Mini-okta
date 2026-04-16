import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { logout as logoutApi, logoutFromIdp } from '../services/authService';
import ConfirmModal from './ConfirmModal';
import Icon from './Icon';

export default function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const clearLocalSession = async () => {
    try {
      await logoutApi();
    } catch (error) {
      console.warn('Logout API request failed, clearing local session anyway.', error);
    }
    logout();
  };

  const handleLocalLogout = async () => {
    setShowLogoutConfirm(false);
    await clearLocalSession();
  };

  const handleGlobalLogout = async () => {
    const idToken = localStorage.getItem('jwt_token');
    setShowLogoutConfirm(false);
    await clearLocalSession();
    logoutFromIdp(idToken);
  };

  if (!user) return null;

  const navLinks = [
    { path: '/dashboard', label: 'Dashboard', icon: 'dashboard', roles: ['learner', 'instructor', 'admin'] },
    { path: '/courses', label: 'Courses', icon: 'courses', roles: ['learner', 'instructor', 'admin'] },
    { path: '/my-courses', label: 'My Courses', icon: 'enrollments', roles: ['learner'] },
    { path: '/performance', label: 'Performance', icon: 'performance', roles: ['learner'] },
    { path: '/instructor', label: 'Instructor', icon: 'instructor', roles: ['instructor'] },
    { path: '/admin', label: 'Admin', icon: 'admin', roles: ['admin'] }
  ];

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/dashboard" className="navbar-brand">
          <Icon name="brand" size={18} className="brand-icon-svg" />
          <span className="brand-text">Sigverse</span>
        </Link>
        <div className="navbar-links">
          {navLinks
            .filter((link) => link.roles.includes(user.role))
            .map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`nav-link ${location.pathname === link.path ? 'active' : ''}`}
              >
                <Icon name={link.icon} size={15} />
                <span>{link.label}</span>
              </Link>
            ))}
        </div>
        <div className="navbar-user">
          <Link to="/profile" className="user-avatar-link">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt={user.name} className="user-avatar" />
            ) : (
              <div className="user-avatar-placeholder">{user.name?.[0]?.toUpperCase() || '?'}</div>
            )}
            <span className="user-name">{user.name}</span>
          </Link>
          <span className="role-badge" data-role={user.role}>{user.role}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowLogoutConfirm(true)}>
            Logout
          </button>
        </div>
      </div>
      {showLogoutConfirm && (
        <ConfirmModal
          title="Ready to log out?"
          message="Sign out of SigVerse only, or sign out of SigVerse and your SigAuth session too."
          cancelLabel="Stay Logged In"
          confirmLabel="Logout from SigVerse"
          secondaryLabel="Sign out of SigAuth"
          onCancel={() => setShowLogoutConfirm(false)}
          onConfirm={handleLocalLogout}
          onSecondary={handleGlobalLogout}
        />
      )}
    </nav>
  );
}
