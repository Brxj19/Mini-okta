import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';

const ID_TOKEN_STORAGE_KEY = 'logistica_delivery_id_token';
const ACCESS_TOKEN_STORAGE_KEY = 'logistica_delivery_access_token';
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

function readStoredToken() {
  return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
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

  const formData = new URLSearchParams();
  formData.set('grant_type', 'authorization_code');
  formData.set('code', code);
  formData.set('redirect_uri', REDIRECT_URI);
  formData.set('client_id', IDP_CLIENT_ID);
  if (codeVerifier) formData.set('code_verifier', codeVerifier);

  const response = await fetch(`${IDP_URL}/api/v1/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
  });
  const data = await response.json();

  if (!response.ok || !data.id_token) {
    throw new Error(data.error_description || 'Token exchange failed');
  }

  sessionStorage.removeItem('logistica_oauth_state');
  sessionStorage.removeItem('logistica_code_verifier');
  return {
    idToken: data.id_token,
    accessToken: data.access_token || data.id_token
  };
}

async function fetchSession(token) {
  const response = await fetch(`${API_URL}/api/me`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Unable to load session');
  }

  return payload.user;
}

function logoutFromIdp(idToken) {
  const params = new URLSearchParams({
    client_id: IDP_CLIENT_ID,
    post_logout_redirect_uri: window.location.origin,
  });
  if (idToken) {
    params.set('id_token_hint', idToken);
  }
  window.location.assign(`${IDP_URL}/api/v1/logout?${params.toString()}`);
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
              <span className="pill">App roles only</span>
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
      .then(async ({ idToken, accessToken }) => {
        localStorage.setItem(ID_TOKEN_STORAGE_KEY, idToken);
        localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
        const user = await fetchSession(accessToken);
        onAuthenticated({ idToken, accessToken, user });
        navigate('/dashboard', { replace: true });
      })
      .catch(() => {
        localStorage.removeItem(ID_TOKEN_STORAGE_KEY);
        localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
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
                  These claims are already available to the client without needing any organization group names.
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
  const [token, setToken] = useState(readStoredToken);
  const [idToken, setIdToken] = useState(() => localStorage.getItem(ID_TOKEN_STORAGE_KEY));
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const activeToken = readStoredToken();
    if (!activeToken) {
      setUser(null);
      setReady(true);
      return;
    }

    fetchSession(activeToken)
      .then((sessionUser) => {
        setToken(activeToken);
        setUser(sessionUser);
      })
      .catch(() => {
        localStorage.removeItem(ID_TOKEN_STORAGE_KEY);
        localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
        setIdToken(null);
        setToken(null);
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const authApi = useMemo(() => ({
    onAuthenticated({ idToken: nextIdToken, accessToken: nextAccessToken, user: nextUser }) {
      setIdToken(nextIdToken);
      setToken(nextAccessToken);
      setUser(nextUser);
    },
    async logout(globalLogout = false) {
      const activeIdToken = idToken || localStorage.getItem(ID_TOKEN_STORAGE_KEY);
      localStorage.removeItem(ID_TOKEN_STORAGE_KEY);
      localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
      setIdToken(null);
      setToken(null);
      setUser(null);
      if (globalLogout) {
        logoutFromIdp(activeIdToken);
        return;
      }
      navigate('/', { replace: true });
    }
  }), [idToken, navigate]);

  if (!ready) {
    return (
      <div className="app-shell">
        <div className="callback-shell">
          <div className="callback-card">
            <span className="eyebrow">Loading</span>
            <h1>Preparing Logistica Delivery</h1>
            <p className="muted">Checking whether you already have a valid SigAuth session for this client.</p>
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
