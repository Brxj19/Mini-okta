import React, { useState, useEffect, useRef } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:4003';

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
  const [ready, setReady] = useState(false);
  const hasHandledErrorParam = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const errorMessage = params.get('error');

    if (errorMessage && !hasHandledErrorParam.current) {
      hasHandledErrorParam.current = true;
      setError(errorMessage);
      window.history.replaceState({}, '', '/');
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
    window.location.href = `${API_URL}/auth/login`;
  };

  const handleLocalLogout = async () => {
    setUser(null);
    await logoutLocalSession().catch(() => {});
  };

  const handleGlobalLogout = async () => {
    const logoutUrl = await getIdpLogoutUrl().catch(() => null);
    setUser(null);
    await logoutLocalSession().catch(() => {});
    if (logoutUrl) {
      window.location.href = logoutUrl;
      return;
    }
    window.location.href = '/';
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
      {!user ? (
        <div style={{ ...cardStyle, textAlign: 'center' }}>
          <h2 style={{ fontSize: '22px', marginBottom: '16px' }}>Welcome to HR Portal</h2>
          <p style={{ color: '#94a3b8', marginBottom: '24px' }}>Sign in through SigAuth. HR Portal now uses a backend-owned confidential web-app flow with an HttpOnly session cookie.</p>
          <button onClick={handleLogin} style={btnStyle}>Sign in with HR Portal →</button>
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
