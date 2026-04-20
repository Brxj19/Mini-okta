import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { exchangeIdpCode } from '../services/authService';

export default function AuthCallback() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const hasExchangedRef = useRef(false);

  useEffect(() => {
    if (hasExchangedRef.current) {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (code && state) {
      hasExchangedRef.current = true;
      exchangeIdpCode({ code, state })
        .then(() => login())
        .then(() => navigate('/dashboard', { replace: true }))
        .catch(() => navigate('/login', { replace: true }));
    } else {
      navigate('/login', { replace: true });
    }
  }, [login, navigate]);
  return (
    <div className="spinner-overlay">
      <div className="spinner"><div className="spinner-ring"></div></div>
      <p className="spinner-text">Authenticating with SigAuth...</p>
    </div>
  );
}
