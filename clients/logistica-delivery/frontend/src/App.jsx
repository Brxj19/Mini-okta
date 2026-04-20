import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';

const IDP_URL = import.meta.env.VITE_IDP_URL || 'http://localhost:8000';
const IDP_CLIENT_ID = import.meta.env.VITE_IDP_CLIENT_ID || 'P9NNBIKqxRyTQmKbRsUF5AGjGVAXaudc';
const REDIRECT_URI = import.meta.env.VITE_IDP_REDIRECT_URI || `${window.location.origin}/auth/callback`;
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:4100';

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

async function beginIdpLogin() {
  if (!IDP_CLIENT_ID) {
    throw new Error('VITE_IDP_CLIENT_ID is not configured');
  }

  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = crypto.randomUUID();
  const nonce = crypto.randomUUID();

  sessionStorage.setItem('logistica_oauth_state', state);
  sessionStorage.setItem('logistica_code_verifier', codeVerifier);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: IDP_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: 'openid profile email',
    state,
    nonce,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256'
  });

  window.location.href = `${IDP_URL}/api/v1/authorize?${params.toString()}`;
}

async function exchangeIdpCode({ code, state }) {
  const savedState = sessionStorage.getItem('logistica_oauth_state');
  const codeVerifier = sessionStorage.getItem('logistica_code_verifier');

  if (state !== savedState) {
    throw new Error('State mismatch');
  }

  const response = await fetch(`${API_URL}/auth/idp/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      code,
      codeVerifier,
    }),
  });
  const data = await response.json();

  sessionStorage.removeItem('logistica_oauth_state');
  sessionStorage.removeItem('logistica_code_verifier');

  if (!response.ok || !data.user) {
    throw new Error(data.error || 'Unable to finish sign-in');
  }

  return data.user;
}

async function fetchSession() {
  const response = await fetch(`${API_URL}/auth/session`, {
    credentials: 'include',
  });

  if (response.status === 401) {
    return null;
  }

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Unable to load session');
  }

  return payload.user;
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
  const payload = await response.json();
  if (!response.ok || !payload.logoutUrl) {
    throw new Error(payload.error || 'Unable to start SigAuth logout');
  }
  return payload.logoutUrl;
}

const ROLE_CONTENT = {
  admin: [
    {
      title: 'Operations command',
      text: 'Review fleet readiness, route coverage, and customer SLA trends from one place.'
    },
    {
      title: 'Team controls',
      text: 'Assign delivery agents, monitor incidents, and coordinate warehouse-to-doorstep workflows.'
    },
    {
      title: 'Client visibility',
      text: 'See which end-user cohorts are active across regions and which accounts need attention.'
    }
  ],
  delivery_agent: [
    {
      title: 'Assigned route',
      text: 'Focus on the active route, handoff notes, and checkpoints required before completion.'
    },
    {
      title: 'Delivery updates',
      text: 'Keep customer ETA, package handoff, and proof-of-delivery actions in one lightweight panel.'
    },
    {
      title: 'Escalations',
      text: 'Quickly flag exceptions back to operations when a package needs support or rescheduling.'
    }
  ],
  end_user: [
    {
      title: 'Order timeline',
      text: 'Track where the order is, the expected ETA, and whether the final delivery has been completed.'
    },
    {
      title: 'Delivery contact',
      text: 'See the assigned delivery team and stay aligned on the final handoff window.'
    },
    {
      title: 'Support snapshot',
      text: 'Keep the delivery reference and account info handy if a reschedule or support request is needed.'
    }
  ]
};

function AuthPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async () => {
    setBusy(true);
    setError('');
    try {
      await beginIdpLogin();
    } catch (err) {
      setBusy(false);
      setError(err.message || 'Unable to start SigAuth login');
    }
  };

  return (
    <div className="app-shell">
      <div className="auth-layout">
        <section className="hero-panel">
          <div>
            <span className="eyebrow">Logistics client</span>
            <h1 className="hero-title">Logistica Delivery keeps every handoff role-aware.</h1>
            <p className="hero-copy">
              This lightweight client app shows how SigAuth can gate access with application roles only.
              Admins, delivery agents, and end users all land in the same product with the right welcome dashboard.
            </p>
            <div className="pill-list">
              <span className="pill">SigAuth login</span>
              <span className="pill">Backend session cookie</span>
              <span className="pill">Node + Express + React</span>
            </div>
          </div>

          <div className="hero-grid">
            <div className="feature-card">
              <strong>Admin</strong>
              <span>Sees the operations overview, fleet posture, and delivery program controls.</span>
            </div>
            <div className="feature-card">
              <strong>Delivery agent</strong>
              <span>Gets a focused operational dashboard for assigned routes and active drop-offs.</span>
            </div>
            <div className="feature-card">
              <strong>End user</strong>
              <span>Gets a customer-friendly view of delivery progress, ETA, and support touchpoints.</span>
            </div>
          </div>
        </section>

        <aside className="auth-card">
          <div className="brand-lockup">
            <div className="brand-mark">LD</div>
            <div>
              <h1>Logistica Delivery</h1>
              <div className="muted">Role-based logistics workspace powered by SigAuth</div>
            </div>
          </div>

          <p className="muted">
            Sign in with your SigAuth account. Access is controlled by application assignment in SigAuth,
            while the in-app experience is shaped by the `app_roles` claim.
          </p>

          <div className="auth-actions">
            <button type="button" className="btn btn-primary" onClick={handleLogin} disabled={busy}>
              {busy ? 'Redirecting to SigAuth...' : 'Continue with SigAuth'}
            </button>
            <div className="muted">Recommended app roles: `admin`, `delivery_agent`, `end_user`.</div>
            {error ? <div className="muted" style={{ color: '#b91c1c' }}>{error}</div> : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

function CallbackPage({ onAuthenticated }) {
  const navigate = useNavigate();
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (!code || !state) {
      navigate('/', { replace: true });
      return;
    }

    exchangeIdpCode({ code, state })
      .then(async (user) => {
        onAuthenticated(user);
        navigate('/dashboard', { replace: true });
      })
      .catch(() => {
        navigate('/', { replace: true });
      });
  }, [navigate, onAuthenticated]);

  return (
    <div className="app-shell">
      <div className="callback-shell">
        <div className="callback-card">
          <span className="eyebrow">Authorizing</span>
          <h1>Finishing your Logistica Delivery sign-in</h1>
          <p className="muted">
            We are verifying your SigAuth token and loading the correct dashboard for your application role.
          </p>
        </div>
      </div>
    </div>
  );
}

function Dashboard({ user, onLogout }) {
  const content = ROLE_CONTENT[user.clientRole] || ROLE_CONTENT.end_user;

  return (
    <div className="app-shell">
      <div className="dashboard-shell">
        <div className="dashboard-card">
          <div className="dashboard-header">
            <div>
              <span className="eyebrow">Welcome dashboard</span>
              <h1>{user.name}, you are signed in to Logistica Delivery.</h1>
              <p className="muted">
                This client trusts SigAuth for access control and uses app roles for the experience shown below.
              </p>
            </div>
            <div>
              <div className="role-banner">Role: {user.clientRole.replace('_', ' ')}</div>
              <div style={{ height: 12 }}></div>
              <div style={{ display: 'grid', gap: 10 }}>
                <button type="button" className="btn btn-secondary" onClick={() => onLogout(false)}>
                  Sign out from Logistica
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => onLogout(true)}>
                  Sign out of SigAuth
                </button>
              </div>
            </div>
          </div>

          <div className="dashboard-grid">
            <div className="dashboard-stack">
              <div className="dashboard-card" style={{ padding: 24 }}>
                <h2 style={{ marginTop: 0 }}>Session profile</h2>
                <div className="info-list">
                  <div className="info-row">
                    <div className="info-label">Email</div>
                    <div>{user.email || 'Not provided'}</div>
                  </div>
                  <div className="info-row">
                    <div className="info-label">Organization</div>
                    <div>{user.organization || 'Unknown organization'}</div>
                  </div>
                  <div className="info-row">
                    <div className="info-label">Directory roles</div>
                    <div>{user.roles.length ? user.roles.join(', ') : 'None'}</div>
                  </div>
                  <div className="info-row">
                    <div className="info-label">App roles</div>
                    <div>{user.appRoles.length ? user.appRoles.join(', ') : 'None'}</div>
                  </div>
                </div>
              </div>

              <div className="dashboard-card" style={{ padding: 24 }}>
                <h2 style={{ marginTop: 0 }}>Role-aware workspace</h2>
                <div className="role-panel-list">
                  {content.map((item) => (
                    <div key={item.title} className="role-panel-item">
                      <strong>{item.title}</strong>
                      <span className="muted">{item.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="dashboard-stack">
              <div className="metrics-grid">
                <div className="metric-card">
                  <strong>Orders</strong>
                  <span>148 tracked shipments in the demo viewport.</span>
                </div>
                <div className="metric-card">
                  <strong>On time</strong>
                  <span>96.2% simulated delivery success for the active cohort.</span>
                </div>
                <div className="metric-card">
                  <strong>Escalations</strong>
                  <span>4 open handoff exceptions requiring follow-up.</span>
                </div>
              </div>

              <div className="dashboard-card" style={{ padding: 24 }}>
                <h2 style={{ marginTop: 0 }}>Token capabilities</h2>
                <p className="muted">
                  These claims were resolved at sign-in and are now protected by the backend session cookie.
                </p>
                <div className="token-badges">
                  {user.permissions.length
                    ? user.permissions.map((permission) => (
                        <span key={permission} className="token-badge">
                          {permission}
                        </span>
                      ))
                    : <span className="token-badge">No additional permissions in token</span>}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchSession()
      .then((sessionUser) => {
        setUser(sessionUser);
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const authApi = useMemo(() => ({
    onAuthenticated(nextUser) {
      setUser(nextUser);
    },
    async logout(globalLogout = false) {
      await logoutLocalSession().catch(() => {});
      setUser(null);
      if (globalLogout) {
        const logoutUrl = await getIdpLogoutUrl();
        window.location.assign(logoutUrl);
        return;
      }
      navigate('/', { replace: true });
    }
  }), [navigate]);

  if (!ready) {
    return (
      <div className="app-shell">
        <div className="callback-shell">
          <div className="callback-card">
            <span className="eyebrow">Loading</span>
            <h1>Preparing Logistica Delivery</h1>
            <p className="muted">Checking whether you already have a valid session for this client.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <AuthPage />} />
      <Route path="/auth/callback" element={<CallbackPage onAuthenticated={authApi.onAuthenticated} />} />
      <Route
        path="/dashboard"
        element={user ? <Dashboard user={user} onLogout={authApi.logout} /> : <Navigate to="/" replace />}
      />
      <Route path="*" element={<Navigate to={user ? '/dashboard' : '/'} replace />} />
    </Routes>
  );
}
