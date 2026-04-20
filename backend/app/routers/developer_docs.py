"""Public developer documentation page."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.branding import DEVELOPER_DOCS_NAME, PRODUCT_NAME, PRODUCT_TAGLINE
from app.config import settings

router = APIRouter(tags=["developer-docs"])


@router.get("/docs", include_in_schema=False, response_class=HTMLResponse)
async def developer_docs_page():
    """Render developer-facing integration docs with practical code examples."""
    issuer = settings.ISSUER_URL.rstrip("/")
    logo_url = f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png"
    authorize_url = f"{issuer}/api/v1/authorize"
    token_url = f"{issuer}/api/v1/token"
    userinfo_url = f"{issuer}/api/v1/userinfo"
    discovery_url = f"{issuer}/api/v1/.well-known/openid-configuration"
    jwks_url = f"{issuer}/api/v1/.well-known/jwks.json"
    logout_url = f"{issuer}/api/v1/logout"

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{DEVELOPER_DOCS_NAME}</title>
  <style>
    :root {{
      --bg: #ffffff;
      --bg-elevated: #ffffff;
      --panel: #ffffff;
      --panel-soft: #fafafa;
      --line: #e5e7eb;
      --text: #111111;
      --text-muted: #6b7280;
      --accent: #111111;
      --accent-soft: #f4f4f5;
      --ok: #22c55e;
      --warn: #f59e0b;
      --danger: #ef4444;
      --code: #f8fafc;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ min-height: 100%; }}
    body {{
      font-family: "Manrope", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 6% 0%, rgba(17, 17, 17, 0.05), transparent 20%),
        radial-gradient(circle at 88% 14%, rgba(17, 17, 17, 0.04), transparent 20%),
        linear-gradient(180deg, #fafafa, #ffffff 55%, #fcfcfc 100%);
      line-height: 1.65;
    }}
    a {{ color: #111111; text-decoration: none; }}
    a:hover {{ color: #404040; }}

    .shell {{
      width: min(1280px, 100%);
      margin: 0 auto;
      padding: 26px 18px 48px;
      display: grid;
      grid-template-columns: 270px minmax(0, 1fr);
      gap: 18px;
    }}

    .sidebar {{
      position: sticky;
      top: 18px;
      height: max-content;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.92);
      padding: 16px;
      box-shadow: 0 18px 40px rgba(15,23,42,0.05);
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .brand img {{
      width: 34px;
      height: 34px;
      border-radius: 10px;
      object-fit: cover;
      border: 1px solid #e5e7eb;
      background: #ffffff;
      padding: 4px;
    }}
    .brand h1 {{
      font-size: 15px;
      line-height: 1.2;
      letter-spacing: -0.01em;
    }}
    .brand p {{
      font-size: 11px;
      color: var(--text-muted);
    }}

    .toc-title {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #6b7280;
      margin-bottom: 10px;
      font-weight: 700;
    }}
    .toc {{
      display: grid;
      gap: 5px;
      margin-bottom: 14px;
    }}
    .toc a {{
      border-radius: 8px;
      padding: 7px 9px;
      color: #374151;
      font-size: 13px;
      border: 1px solid transparent;
    }}
    .toc a:hover {{
      background: #fafafa;
      border-color: #e5e7eb;
    }}

    .meta {{
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: var(--text-muted);
      font-size: 11px;
      display: grid;
      gap: 5px;
      word-break: break-word;
    }}

    .content {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.94);
      overflow: hidden;
      box-shadow: 0 24px 50px rgba(15,23,42,0.06);
    }}

    .hero {{
      padding: 28px 26px 20px;
      border-bottom: 1px solid var(--line);
      background:
        radial-gradient(circle at top right, rgba(17, 17, 17, 0.05), transparent 30%),
        linear-gradient(180deg, rgba(17, 17, 17, 0.02), rgba(255, 255, 255, 0));
    }}
    .eyebrow {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #6b7280;
      font-weight: 700;
    }}
    .hero h2 {{
      margin-top: 8px;
      font-size: clamp(30px, 4.2vw, 46px);
      line-height: 1.05;
      letter-spacing: -0.03em;
    }}
    .hero p {{
      margin-top: 12px;
      color: #52525b;
      max-width: 920px;
      font-size: 15px;
    }}
    .badges {{
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .badge {{
      border: 1px solid #e5e7eb;
      background: #fafafa;
      color: #27272a;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
    }}
    .links {{
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 9px;
    }}
    .links a {{
      padding: 8px 12px;
      border-radius: 10px;
      font-size: 12px;
      border: 1px solid #e5e7eb;
      background: #ffffff;
    }}

    .section {{
      padding: 22px 26px;
      border-bottom: 1px solid var(--line);
    }}
    .section:last-child {{ border-bottom: none; }}
    .section h3 {{
      font-size: 23px;
      letter-spacing: -0.02em;
      margin-bottom: 8px;
    }}
    .section h4 {{
      margin-top: 14px;
      font-size: 16px;
      color: #111111;
    }}
    .section p, .section li {{
      font-size: 14px;
      color: #4b5563;
    }}
    .section ul, .section ol {{
      margin: 8px 0 0 20px;
      display: grid;
      gap: 5px;
    }}

    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .card {{
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      background: #fafafa;
      padding: 12px;
    }}
    .card strong {{
      display: block;
      margin-bottom: 4px;
      color: #111111;
      font-size: 13px;
    }}
    .card span {{
      font-size: 12px;
      color: #6b7280;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      overflow: hidden;
    }}
    th, td {{
      text-align: left;
      padding: 10px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 12px;
      vertical-align: top;
    }}
    th {{
      background: #fafafa;
      color: #111111;
      font-weight: 700;
      font-size: 12px;
    }}
    tr:last-child td {{ border-bottom: none; }}

    .code-wrap {{
      margin-top: 12px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      background: var(--code);
      overflow: hidden;
    }}
    .code-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #e5e7eb;
      padding: 8px 10px;
      background: #ffffff;
      color: #52525b;
      font-size: 12px;
    }}
    .copy-btn {{
      border: 1px solid #e5e7eb;
      background: #fafafa;
      color: #111111;
      border-radius: 8px;
      font-size: 11px;
      padding: 4px 8px;
      cursor: pointer;
    }}
    pre {{
      margin: 0;
      padding: 12px;
      overflow-x: auto;
      font-size: 12px;
      line-height: 1.6;
      color: #111111;
    }}
    code {{
      background: #fafafa;
      border: 1px solid #e5e7eb;
      padding: 1px 5px;
      border-radius: 5px;
      font-size: 12px;
    }}

    .status-ok {{ color: var(--ok); font-weight: 700; }}
    .status-warn {{ color: var(--warn); font-weight: 700; }}
    .status-danger {{ color: var(--danger); font-weight: 700; }}

    @media (max-width: 980px) {{
      .shell {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: relative;
        top: 0;
      }}
      .grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <aside class="sidebar">
      <div class="brand">
        <img src="{logo_url}" alt="{PRODUCT_NAME} logo" />
        <div>
          <h1>{DEVELOPER_DOCS_NAME}</h1>
          <p>{PRODUCT_TAGLINE}</p>
        </div>
      </div>

      <div class="toc-title">On This Page</div>
      <nav class="toc">
        <a href="#quickstart">Quickstart</a>
        <a href="#register-client">Register Client App</a>
        <a href="#oidc-flow">OIDC Flow (PKCE)</a>
        <a href="#token-validation">Token Validation</a>
        <a href="#scopes-claims">Scopes and Claims</a>
        <a href="#api-endpoints">Endpoint Reference</a>
        <a href="#examples">Code Examples</a>
        <a href="#errors">Error Handling</a>
        <a href="#security">Security Hardening</a>
        <a href="#ops">Production Checklist</a>
        <a href="#troubleshooting">Troubleshooting</a>
      </nav>

      <div class="meta">
        <div><strong>Issuer:</strong> {issuer}</div>
        <div><strong>Flow:</strong> Authorization Code + PKCE</div>
        <div><strong>Default scopes:</strong> openid profile email</div>
      </div>
    </aside>

    <article class="content">
      <header class="hero">
        <div class="eyebrow">{PRODUCT_NAME} • Developer Platform</div>
        <h2>Comprehensive Developer Documentation</h2>
        <p>
          Use this guide to integrate your web app, SPA, mobile app, or backend service with {PRODUCT_NAME}.
          It reflects the latest recommended flow in this project: the browser performs the PKCE authorize redirect,
          your client backend exchanges the code, validates claims, and then creates an app-owned session cookie.
        </p>
        <div class="badges">
          <span class="badge">OIDC Compatible</span>
          <span class="badge">PKCE for public clients</span>
          <span class="badge">Role/Group aware access</span>
          <span class="badge">Admin and audit workflows</span>
        </div>
        <div class="links">
          <a href="{discovery_url}" target="_blank" rel="noreferrer">Discovery JSON</a>
          <a href="{jwks_url}" target="_blank" rel="noreferrer">JWKS</a>
          <a href="{issuer}/api/docs" target="_blank" rel="noreferrer">API Reference</a>
          <a href="{issuer}" target="_blank" rel="noreferrer">Platform Base URL</a>
        </div>
      </header>

      <section id="quickstart" class="section">
        <h3>Quickstart</h3>
        <p>For a standard client application in this project, follow this sequence:</p>
        <ol>
          <li>Create or obtain a {PRODUCT_NAME} client application and configure a strict redirect URI.</li>
          <li>Generate PKCE values (<code>code_verifier</code>, <code>code_challenge</code>), plus <code>state</code> and <code>nonce</code>.</li>
          <li>Redirect users to <code>{authorize_url}</code>.</li>
          <li>On callback, post the returned <code>code</code> and stored PKCE values to your own client backend.</li>
          <li>Your client backend exchanges the code at <code>{token_url}</code>, validates the response, optionally fetches <code>{userinfo_url}</code>, and creates an <code>HttpOnly</code> app session cookie.</li>
          <li>Your frontend bootstraps from your own backend session endpoint, not from browser-stored bearer tokens.</li>
          <li>On sign-out, decide between local app logout and provider logout via <code>{logout_url}</code>.</li>
        </ol>

        <div class="grid-2">
          <div class="card">
            <strong>Public clients (SPA/mobile)</strong>
            <span>Use PKCE. Keep only short-lived PKCE state in browser storage and let your backend create the durable app session.</span>
          </div>
          <div class="card">
            <strong>Confidential clients (backend)</strong>
            <span>Store secrets server-side, exchange the authorization code there, and issue your own secure session cookie to the frontend.</span>
          </div>
        </div>
      </section>

      <section id="register-client" class="section">
        <h3>Register Client App</h3>
        <p>Before authentication works, your client app must be configured with exact callback URLs and allowed scopes.</p>
        <h4>Required configuration</h4>
        <ul>
          <li><code>client_id</code> and client type (<code>spa</code>, <code>web</code>, <code>native</code>, <code>m2m</code>).</li>
          <li>Exact redirect URI allowlist (no wildcard redirects).</li>
          <li>Post-logout redirect URI allowlist.</li>
          <li>Allowed scopes such as <code>openid</code>, <code>profile</code>, <code>email</code>.</li>
          <li>Application assignments (users/groups) and role mapping where applicable.</li>
        </ul>
        <h4>Environment setup recommendation</h4>
        <div class="code-wrap">
          <div class="code-head"><span>.env example for a client app</span><button class="copy-btn" data-copy="env-config">Copy</button></div>
          <pre id="env-config">SIGAUTH_ISSUER={issuer}
SIGAUTH_CLIENT_ID=your-client-id
SIGAUTH_REDIRECT_URI=http://localhost:4000/callback
MINI_OKTA_POST_LOGOUT_REDIRECT_URI=http://localhost:4000/
MINI_OKTA_SCOPES=openid profile email</pre>
        </div>
      </section>

      <section id="oidc-flow" class="section">
        <h3>OIDC Authorization Code + PKCE Flow</h3>
        <p>This is the recommended flow for modern clients and should be your default implementation.</p>
        <ol>
          <li>Create secure random values for <code>state</code>, <code>nonce</code>, and <code>code_verifier</code>.</li>
          <li>Derive <code>code_challenge = BASE64URL(SHA256(code_verifier))</code>.</li>
          <li>Redirect to <code>/authorize</code> with PKCE parameters.</li>
          <li>User authenticates and consents (if enabled).</li>
          <li>Your frontend callback page receives <code>code</code> at the registered redirect URI.</li>
          <li>Your frontend immediately forwards that <code>code</code>, plus <code>state</code> and <code>code_verifier</code>, to your own client backend.</li>
          <li>Your client backend exchanges the code for tokens at <code>/token</code>.</li>
          <li>Your client backend validates claims, derives local role/session state, and creates an app-owned session cookie.</li>
          <li>Your frontend reads the logged-in user from your own backend session endpoint.</li>
        </ol>
        <div class="card" style="margin-top:12px;">
          <strong>Recommended storage pattern</strong>
          <span>Do not persist SigAuth bearer tokens in <code>localStorage</code> for your app session. Use <code>HttpOnly</code> cookies for the app session and keep only temporary PKCE values in <code>sessionStorage</code>.</span>
        </div>
      </section>

      <section id="token-validation" class="section">
        <h3>Token Validation</h3>
        <p>Always perform server-side verification before trusting token claims for authorization decisions.</p>
        <table>
          <thead>
            <tr><th>Check</th><th>What to verify</th><th>Why it matters</th></tr>
          </thead>
          <tbody>
            <tr><td>Signature</td><td>Validate JWT signature using <code>{jwks_url}</code>.</td><td>Prevents forged token acceptance.</td></tr>
            <tr><td>Issuer</td><td><code>iss</code> exactly equals <code>{issuer}</code>.</td><td>Rejects tokens from unknown providers.</td></tr>
            <tr><td>Audience</td><td><code>aud</code> matches your client or API audience.</td><td>Stops token reuse across applications.</td></tr>
            <tr><td>Expiry</td><td><code>exp</code> is still valid, with small clock skew tolerance.</td><td>Prevents use of stale credentials.</td></tr>
            <tr><td>Nonce</td><td>For browser flows, compare <code>nonce</code> to stored value.</td><td>Mitigates token replay in callbacks.</td></tr>
          </tbody>
        </table>
      </section>

      <section id="scopes-claims" class="section">
        <h3>Scopes and Claims</h3>
        <p>Request only what you need. Smaller scope sets reduce risk and consent friction.</p>
        <table>
          <thead>
            <tr><th>Scope</th><th>Typical claims</th><th>Usage</th></tr>
          </thead>
          <tbody>
            <tr><td><code>openid</code></td><td><code>sub</code>, OIDC identity claims</td><td>Required for OIDC login.</td></tr>
            <tr><td><code>profile</code></td><td><code>name</code>, <code>preferred_username</code></td><td>Display profile in application UI.</td></tr>
            <tr><td><code>email</code></td><td><code>email</code>, <code>email_verified</code></td><td>Email-based identity UX and notifications.</td></tr>
          </tbody>
        </table>
      </section>

      <section id="api-endpoints" class="section">
        <h3>Endpoint Reference</h3>
        <table>
          <thead>
            <tr><th>Method</th><th>Endpoint</th><th>Purpose</th></tr>
          </thead>
          <tbody>
            <tr><td>GET</td><td><code>{authorize_url}</code></td><td>Starts user authentication and consent flow.</td></tr>
            <tr><td>POST</td><td><code>{token_url}</code></td><td>Exchanges authorization code for tokens.</td></tr>
            <tr><td>GET</td><td><code>{userinfo_url}</code></td><td>Returns identity plus app-scoped claims such as <code>app_roles</code> for the authenticated client audience.</td></tr>
            <tr><td>POST</td><td><code>{logout_url}</code></td><td>Ends provider-side session/logout flow. Use this for full SigAuth logout, not ordinary local app logout.</td></tr>
            <tr><td>GET</td><td><code>{discovery_url}</code></td><td>Well-known metadata for clients/libraries.</td></tr>
            <tr><td>GET</td><td><code>{jwks_url}</code></td><td>Public keys for token signature validation.</td></tr>
          </tbody>
        </table>
      </section>

      <section id="examples" class="section">
        <h3>Code Examples</h3>

        <h4>Browser (JavaScript): authorize redirect</h4>
        <div class="code-wrap">
          <div class="code-head"><span>JavaScript</span><button class="copy-btn" data-copy="js-authorize">Copy</button></div>
          <pre id="js-authorize">const params = new URLSearchParams({{
  response_type: "code",
  client_id: "your-client-id",
  redirect_uri: "http://localhost:4000/callback",
  scope: "openid profile email",
  state,
  nonce,
  code_challenge,
  code_challenge_method: "S256",
}});
window.location.href = "{authorize_url}?" + params.toString();</pre>
        </div>

        <h4>Node.js backend: token exchange and session bootstrap</h4>
        <div class="code-wrap">
          <div class="code-head"><span>Node.js</span><button class="copy-btn" data-copy="node-exchange">Copy</button></div>
          <pre id="node-exchange">const tokenResponse = await fetch("{token_url}", {{
  method: "POST",
  headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
  body: new URLSearchParams({{
    grant_type: "authorization_code",
    code: authCode,
    redirect_uri: "http://localhost:4000/callback",
    client_id: process.env.SIGAUTH_CLIENT_ID,
    code_verifier: codeVerifier,
  }}),
}});

if (!tokenResponse.ok) throw new Error("token_exchange_failed");

const tokenSet = await tokenResponse.json();
const profileResponse = await fetch("{userinfo_url}", {{
  headers: {{ Authorization: `Bearer ${{tokenSet.access_token}}` }},
}});
const profile = await profileResponse.json();

// Create your own app session cookie here.
res.cookie("app_session", signedSessionValue, {{
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax",
}});</pre>
        </div>

        <h4>Node.js: userinfo call</h4>
        <div class="code-wrap">
          <div class="code-head"><span>Node.js</span><button class="copy-btn" data-copy="node-userinfo">Copy</button></div>
          <pre id="node-userinfo">const response = await fetch("{userinfo_url}", {{
  headers: {{ Authorization: `Bearer ${{accessToken}}` }},
}});
if (!response.ok) throw new Error("userinfo_failed");
const profile = await response.json();</pre>
        </div>

        <h4>Python: confidential client token exchange</h4>
        <div class="code-wrap">
          <div class="code-head"><span>Python requests</span><button class="copy-btn" data-copy="py-token">Copy</button></div>
          <pre id="py-token">import requests

response = requests.post(
    "{token_url}",
    data={{
        "grant_type": "authorization_code",
        "code": "AUTH_CODE",
        "redirect_uri": "http://localhost:4000/callback",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
    }},
    timeout=15,
)
response.raise_for_status()
print(response.json())</pre>
        </div>
      </section>

      <section id="errors" class="section">
        <h3>Error Handling and UX Guidance</h3>
        <p>Build explicit UI states for denied or failed logins. Keep users informed without leaking sensitive details.</p>
        <table>
          <thead>
            <tr><th>Scenario</th><th>Recommended app behavior</th><th>Status</th></tr>
          </thead>
          <tbody>
            <tr><td>Invalid redirect URI</td><td>Show integration misconfiguration message to developer/admin only.</td><td class="status-danger">Block</td></tr>
            <tr><td>Unauthorized user for app</td><td>Show clear access denied message with support/contact path.</td><td class="status-warn">Handle gracefully</td></tr>
            <tr><td>Invalid credentials</td><td>Show generic error text, do not reveal account existence.</td><td class="status-warn">Retry allowed</td></tr>
            <tr><td>Expired code/token</td><td>Restart auth flow, clear stale PKCE values, and rebuild the app session through a fresh redirect.</td><td class="status-ok">Recoverable</td></tr>
          </tbody>
        </table>
      </section>

      <section id="security" class="section">
        <h3>Security Hardening</h3>
        <ul>
          <li>Always enforce HTTPS in production and secure cookies (<code>HttpOnly</code>, <code>Secure</code>, <code>SameSite</code>).</li>
          <li>Prefer backend code exchange plus <code>HttpOnly</code> app session cookies over frontend token persistence.</li>
          <li>Rotate client secrets and signing keys based on policy.</li>
          <li>Validate redirect URIs exactly; never allow wildcard callbacks.</li>
          <li>Implement global session invalidation after password reset events.</li>
          <li>Model logout as two actions when needed: local app logout and full SigAuth logout.</li>
          <li>Alert and rate-limit repeated failed login attempts.</li>
        </ul>
      </section>

      <section id="ops" class="section">
        <h3>Production Readiness Checklist</h3>
        <ul>
          <li>Environment separation is in place (local/staging/prod issuers and credentials).</li>
          <li>Audit and notification streams are monitored by platform and org admins.</li>
          <li>Backup and incident playbook includes identity outage scenarios.</li>
          <li>Automated tests cover callback validation, token failures, and role-based access checks.</li>
          <li>Clock synchronization (NTP) is configured to avoid token skew issues.</li>
        </ul>
      </section>

      <section id="troubleshooting" class="section">
        <h3>Troubleshooting</h3>
        <h4>I see internal server error after clicking "Sign in with IdP"</h4>
        <p>Check app redirect URI registration first. Mismatch between requested redirect URI and configured URI is a common root cause.</p>

        <h4>Users fall into the wrong client-app role</h4>
        <p>For strict role-based apps, enable explicit role mappings and make sure the token path your client uses reads <code>app_roles</code> from the audience-specific claims or <code>/userinfo</code>.</p>

        <h4>Users are not logged out in other tabs after password reset</h4>
        <p>Ensure your frontend listens to shared logout-sync events and force-navigates all tabs to <code>/login</code> after session invalidation.</p>

        <h4>Reset links should expire after success or timeout</h4>
        <p>Use single-use reset tokens and invalidate all prior reset tokens immediately after a successful password update.</p>

        <h4>Need more API-level details?</h4>
        <p>Open <a href="{issuer}/api/docs" target="_blank" rel="noreferrer">{issuer}/api/docs</a> for endpoint schemas and request/response models.</p>
      </section>
    </article>
  </main>

  <script>
    const buttons = document.querySelectorAll(".copy-btn");
    buttons.forEach((btn) => {{
      btn.addEventListener("click", async () => {{
        const targetId = btn.getAttribute("data-copy");
        const el = document.getElementById(targetId);
        if (!el) return;
        try {{
          await navigator.clipboard.writeText(el.innerText);
          const prev = btn.innerText;
          btn.innerText = "Copied";
          setTimeout(() => {{ btn.innerText = prev; }}, 900);
        }} catch (e) {{
          btn.innerText = "Copy failed";
          setTimeout(() => {{ btn.innerText = "Copy"; }}, 1100);
        }}
      }});
    }});
  </script>
</body>
</html>"""
    )
