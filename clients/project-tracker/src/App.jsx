import React, { useState, useEffect, useRef } from 'react';

const IDP_URL = 'http://localhost:8000';
const CLIENT_ID = 'project-tracker-client-id';
const REDIRECT_URI = 'http://localhost:4001/callback';
const POST_LOGOUT_REDIRECT_URI = 'http://localhost:4001';

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

function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')));
  } catch { return null; }
}

export default function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [userInfo, setUserInfo] = useState(null);
  const hasHandledCallback = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (code && state) {
      if (hasHandledCallback.current) return;
      hasHandledCallback.current = true;

      const savedState = sessionStorage.getItem('oauth_state');
      const codeVerifier = sessionStorage.getItem('code_verifier');

      if (state !== savedState) {
        setError('State mismatch — possible CSRF attack');
        hasHandledCallback.current = false;
        return;
      }

      setLoading(true);
      const formData = new URLSearchParams();
      formData.set('grant_type', 'authorization_code');
      formData.set('code', code);
      formData.set('redirect_uri', REDIRECT_URI);
      formData.set('client_id', CLIENT_ID);
      if (codeVerifier) formData.set('code_verifier', codeVerifier);

      fetch(`${IDP_URL}/api/v1/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
      })
        .then(r => r.json())
        .then(data => {
          if (data.id_token) {
            const claims = parseJwt(data.id_token);
            setUser(claims);
            setToken(data.id_token);
            sessionStorage.setItem('pt_token', data.id_token);
            sessionStorage.removeItem('oauth_state');
            sessionStorage.removeItem('code_verifier');
            // Call userinfo
            fetch(`${IDP_URL}/api/v1/userinfo`, { headers: { Authorization: `Bearer ${data.id_token}` } })
              .then(r => r.json())
              .then(setUserInfo)
              .catch(() => {});
          } else {
            hasHandledCallback.current = false;
            setError(data.error_description || 'Token exchange failed');
          }
        })
        .catch(e => {
          hasHandledCallback.current = false;
          setError(e.message);
        })
        .finally(() => { setLoading(false); window.history.replaceState({}, '', '/'); });
    }
  }, []);

  useEffect(() => {
    const stored = sessionStorage.getItem('pt_token');
    if (stored) {
      const claims = parseJwt(stored);
      if (claims?.exp && claims.exp * 1000 > Date.now()) {
        setUser(claims);
        setToken(stored);
        fetch(`${IDP_URL}/api/v1/userinfo`, { headers: { Authorization: `Bearer ${stored}` } })
          .then(r => r.json())
          .then(setUserInfo)
          .catch(() => {});
      } else { sessionStorage.removeItem('pt_token'); }
    }
  }, []);

  const handleLogin = async () => {
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = await generateCodeChallenge(codeVerifier);
    const state = crypto.randomUUID();
    const nonce = crypto.randomUUID();

    sessionStorage.setItem('oauth_state', state);
    sessionStorage.setItem('code_verifier', codeVerifier);

    const params = new URLSearchParams({
      response_type: 'code', client_id: CLIENT_ID, redirect_uri: REDIRECT_URI,
      scope: 'openid profile email', state, nonce,
      code_challenge: codeChallenge, code_challenge_method: 'S256',
    });

    window.location.href = `${IDP_URL}/api/v1/authorize?${params}`;
  };

  const handleLogout = async () => {
    setUser(null);
    setToken(null);
    setUserInfo(null);
    sessionStorage.removeItem('pt_token');
    const params = new URLSearchParams({
      client_id: CLIENT_ID,
      post_logout_redirect_uri: POST_LOGOUT_REDIRECT_URI,
    });
    if (token) {
      params.set('id_token_hint', token);
    }
    window.location.href = `${IDP_URL}/api/v1/logout?${params.toString()}`;
  };

  const cardStyle = { background: 'rgba(30,41,59,0.7)', border: '1px solid rgba(71,85,105,0.5)', borderRadius: '16px', padding: '32px', backdropFilter: 'blur(10px)' };
  const btnStyle = { padding: '12px 32px', background: 'linear-gradient(135deg, #10b981, #059669)', color: '#fff', border: 'none', borderRadius: '10px', fontSize: '16px', fontWeight: 600, cursor: 'pointer' };

  return (
    <div style={{ padding: '40px', maxWidth: '700px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '40px' }}>
        <span style={{ fontSize: '48px' }}>📊</span>
        <h1 style={{ fontSize: '28px', fontWeight: 700, marginTop: '12px', background: 'linear-gradient(135deg, #34d399, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Project Tracker</h1>
        <p style={{ color: '#94a3b8', marginTop: '4px' }}>Demo Client App 2 — SPA with PKCE + UserInfo</p>
      </div>

      {error && <div style={{ ...cardStyle, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171', marginBottom: '20px', textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ textAlign: 'center', color: '#94a3b8' }}>Exchanging authorization code...</div>}

      {!user ? (
        <div style={{ ...cardStyle, textAlign: 'center' }}>
          <h2 style={{ fontSize: '22px', marginBottom: '16px' }}>Welcome to Project Tracker</h2>
          <p style={{ color: '#94a3b8', marginBottom: '24px' }}>Authenticate with Internal IdP to track your projects</p>
          <button onClick={handleLogin} style={btnStyle}>Sign in with IdP →</button>
        </div>
      ) : (
        <div>
          <div style={{ ...cardStyle, marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '20px' }}>👋 Welcome, {user.name || user.email}</h2>
              <button onClick={handleLogout} style={{ ...btnStyle, background: 'rgba(100,116,139,0.3)', fontSize: '14px', padding: '8px 16px' }}>Logout</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {[
                ['Email', user.email],
                ['Verified', user.email_verified ? '✅' : '❌'],
                ['Roles', (user.roles || []).join(', ') || '—'],
                ['Permissions', (user.permissions || []).length + ' assigned'],
              ].map(([label, value]) => (
                <div key={label}><div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>{label}</div><div style={{ marginTop: '4px', fontSize: '14px' }}>{value}</div></div>
              ))}
            </div>
          </div>

          {userInfo && (
            <div style={{ ...cardStyle, marginBottom: '20px' }}>
              <h3 style={{ fontSize: '16px', marginBottom: '12px', color: '#94a3b8' }}>UserInfo Endpoint Response</h3>
              <pre style={{ fontSize: '12px', color: '#cbd5e1', background: 'rgba(15,23,42,0.8)', padding: '16px', borderRadius: '8px', overflow: 'auto' }}>{JSON.stringify(userInfo, null, 2)}</pre>
            </div>
          )}

          <div style={cardStyle}>
            <h3 style={{ fontSize: '16px', marginBottom: '12px', color: '#94a3b8' }}>Raw ID Token Claims</h3>
            <pre style={{ fontSize: '12px', color: '#cbd5e1', background: 'rgba(15,23,42,0.8)', padding: '16px', borderRadius: '8px', overflow: 'auto', maxHeight: '300px' }}>{JSON.stringify(user, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
