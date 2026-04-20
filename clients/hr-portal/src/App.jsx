import React, { useState, useEffect, useRef } from 'react';

const IDP_URL = import.meta.env.VITE_IDP_URL || 'http://localhost:8000';
const CLIENT_ID = import.meta.env.VITE_IDP_CLIENT_ID || 'hr-portal-client-id';
const REDIRECT_URI = import.meta.env.VITE_IDP_REDIRECT_URI || `${window.location.origin}/callback`;
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:4003';

function generateCodeVerifier() {
  const arr = new Uint8Array(32);
  crypto.getRandomValues(arr);
  return btoa(String.fromCharCode(...arr)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function fetchSession() {
  const response = await fetch(`${API_URL}/auth/session`, {
    credentials: 'include',
  });
  if (response.status === 401) return null;
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Unable to load session');
  }
  return data.user;
}

async function exchangeIdpCode({ code, state }) {
  const savedState = sessionStorage.getItem('oauth_state');
  const codeVerifier = sessionStorage.getItem('code_verifier');

  if (state !== savedState) {
    throw new Error('State mismatch — possible CSRF attack');
  }

  const response = await fetch(`${API_URL}/auth/idp/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ code, codeVerifier }),
  });
  const data = await response.json();

  sessionStorage.removeItem('oauth_state');
  sessionStorage.removeItem('code_verifier');

  if (!response.ok || !data.user) {
    throw new Error(data.error || 'Token exchange failed');
  }

  return data.user;
}

async function logoutLocalSession() {
  await fetch(`${API_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

async function getIdpLogoutUrl() {
  const response = await fetch(`${API_URL}/auth/logout-url`, {
    credentials: 'include',
  });
  const data = await response.json();
  if (!response.ok || !data.logoutUrl) {
    throw new Error(data.error || 'Unable to build logout URL');
  }
  return data.logoutUrl;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const hasHandledCallback = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (code && state) {
      if (hasHandledCallback.current) return;
      hasHandledCallback.current = true;

      setLoading(true);
      exchangeIdpCode({ code, state })
        .then((sessionUser) => {
          setUser(sessionUser);
        })
        .catch((e) => {
          hasHandledCallback.current = false;
          setError(e.message);
        })
        .finally(() => {
          setLoading(false);
          setReady(true);
          window.history.replaceState({}, '', '/');
        });
      return;
    }

    fetchSession()
      .then((sessionUser) => {
        setUser(sessionUser);
      })
      .catch((e) => {
        setError(e.message);
      })
      .finally(() => setReady(true));
  }, []);

  const handleLogin = async () => {
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = await generateCodeChallenge(codeVerifier);
    const state = crypto.randomUUID();
    const nonce = crypto.randomUUID();

    sessionStorage.setItem('oauth_state', state);
    sessionStorage.setItem('code_verifier', codeVerifier);

    const params = new URLSearchParams({
      response_type: 'code',
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      scope: 'openid profile email',
      state, nonce,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
    });

    window.location.href = `${IDP_URL}/api/v1/authorize?${params}`;
  };

  const handleLocalLogout = async () => {
    setUser(null);
    await logoutLocalSession().catch(() => {});
  };

  const handleGlobalLogout = async () => {
    setUser(null);
    await logoutLocalSession().catch(() => {});
    const logoutUrl = await getIdpLogoutUrl();
    window.location.href = logoutUrl;
  };

  const cardStyle = { background: 'rgba(30,41,59,0.7)', border: '1px solid rgba(71,85,105,0.5)', borderRadius: '16px', padding: '32px', backdropFilter: 'blur(10px)' };
  const btnStyle = { padding: '12px 32px', background: 'linear-gradient(135deg, #3b82f6, #2563eb)', color: '#fff', border: 'none', borderRadius: '10px', fontSize: '16px', fontWeight: 600, cursor: 'pointer' };

  if (!ready) {
    return <div style={{ textAlign: 'center', padding: '80px', color: '#94a3b8' }}>Loading HR Portal session...</div>;
  }

  return (
    <div style={{ padding: '40px', maxWidth: '700px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '40px' }}>
        <span style={{ fontSize: '48px' }}>🏢</span>
        <h1 style={{ fontSize: '28px', fontWeight: 700, marginTop: '12px', background: 'linear-gradient(135deg, #60a5fa, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>HR Portal</h1>
        <p style={{ color: '#94a3b8', marginTop: '4px' }}>Demo Client App — cookie-backed session with SigAuth</p>
      </div>

      {error && <div style={{ ...cardStyle, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171', marginBottom: '20px', textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ textAlign: 'center', color: '#94a3b8' }}>Finalizing secure session...</div>}

      {!user ? (
        <div style={{ ...cardStyle, textAlign: 'center' }}>
          <h2 style={{ fontSize: '22px', marginBottom: '16px' }}>Welcome to HR Portal</h2>
          <p style={{ color: '#94a3b8', marginBottom: '24px' }}>Sign in through SigAuth. This client now keeps auth state in an HttpOnly session cookie.</p>
          <button onClick={handleLogin} style={btnStyle}>Sign in with IdP →</button>
        </div>
      ) : (
        <div>
          <div style={{ ...cardStyle, marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '20px' }}>👋 Welcome, {user.name || user.email}</h2>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button onClick={handleLocalLogout} style={{ ...btnStyle, background: 'rgba(100,116,139,0.3)', fontSize: '14px', padding: '8px 16px' }}>Logout App</button>
                <button onClick={handleGlobalLogout} style={{ ...btnStyle, background: 'rgba(15,23,42,0.85)', fontSize: '14px', padding: '8px 16px' }}>Logout SigAuth</button>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {[
                ['Email', user.email],
                ['Verified', user.email_verified ? '✅ Yes' : '❌ No'],
                ['Org ID', user.org_id?.substring(0, 12) + '...' || '—'],
                ['Roles', (user.roles || []).join(', ') || '—'],
              ].map(([label, value]) => (
                <div key={label}><div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px' }}>{label}</div><div style={{ color: '#e2e8f0', marginTop: '4px', fontSize: '14px', wordBreak: 'break-all' }}>{value}</div></div>
              ))}
            </div>
          </div>
          <div style={cardStyle}>
            <h3 style={{ fontSize: '16px', marginBottom: '12px', color: '#94a3b8' }}>Resolved session claims</h3>
            <pre style={{ fontSize: '12px', color: '#cbd5e1', background: 'rgba(15,23,42,0.8)', padding: '16px', borderRadius: '8px', overflow: 'auto', maxHeight: '300px' }}>{JSON.stringify(user.claims, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
