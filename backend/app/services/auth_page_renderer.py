"""HTML renderers for branded authorization and auth-adjacent pages."""

import html
import json
from typing import Optional
from urllib.parse import quote

from app.branding import PRODUCT_NAME, PRODUCT_TAGLINE
from app.config import settings

SCOPE_LABELS = {
    "openid": ("Identity verification", "Confirm who you are and complete secure sign-in."),
    "profile": ("Basic profile", "See your name and standard profile details."),
    "email": ("Email address", "Read the email address linked to your account."),
    "offline_access": ("Persistent access", "Keep access active without asking you to sign in every time."),
}

LOTTIE_SCRIPT_SRC = "https://unpkg.com/@lottiefiles/dotlottie-wc@0.9.10/dist/dotlottie-wc.js"
LOTTIE_AUTH_ANIMATION_SRC = "https://lottie.host/e80c996e-1c39-4dd8-917b-01c52c73e00a/vzPjEPcJse.lottie"


def _authorize_brand_styles() -> str:
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: "Manrope", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif; background: #ffffff; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 32px; color: #111111; position: relative; }
        body::before { content: ""; position: fixed; inset: 0; background:
          radial-gradient(circle at 16% 14%, rgba(0,0,0,0.04), transparent 24%),
          radial-gradient(circle at 82% 20%, rgba(0,0,0,0.035), transparent 22%),
          radial-gradient(circle at 72% 78%, rgba(0,0,0,0.03), transparent 24%),
          linear-gradient(180deg, rgba(245,245,245,0.78), rgba(255,255,255,0.95));
          pointer-events: none; }
        .shell { width: min(1120px, 100%); display: grid; grid-template-columns: 1.08fr 0.92fr; border: 1px solid #e5e7eb; border-radius: 30px; overflow: hidden; background: rgba(255,255,255,0.96); box-shadow: 0 24px 60px rgba(15,23,42,0.08); position: relative; z-index: 1; }
        .context { padding: 44px; background: linear-gradient(180deg, #fafafa, #f5f5f5); border-right: 1px solid #e5e7eb; }
        .signin { padding: 44px; background: #ffffff; color: #111111; }
        .eyebrow { font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 700; color: #6b7280; }
        .context h1 { font-size: 40px; line-height: 1.02; margin-top: 16px; color: #111111; letter-spacing: -0.04em; }
        .context-copy { margin-top: 18px; color: #52525b; font-size: 15px; line-height: 1.7; }
        .client-card { margin-top: 28px; border: 1px solid #e5e7eb; border-radius: 22px; background: #ffffff; padding: 22px; }
        .client-top { display: flex; align-items: center; gap: 16px; }
        .client-logo-image, .client-logo-fallback { width: 64px; height: 64px; border-radius: 18px; object-fit: cover; background: #f5f5f5; border: 1px solid #e5e7eb; }
        .client-logo-fallback { display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800; color: #111111; background: #f3f4f6; }
        .client-label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.16em; color: #71717a; }
        .client-name { margin-top: 6px; font-size: 24px; font-weight: 700; color: #111111; }
        .client-host { margin-top: 6px; font-size: 14px; color: #6b7280; }
        .scope-panel { margin-top: 28px; }
        .scope-panel h2 { font-size: 16px; color: #111111; margin-bottom: 14px; }
        .scope-list { list-style: none; display: grid; gap: 12px; }
        .scope-item { display: grid; grid-template-columns: 14px 1fr; gap: 14px; align-items: start; border-radius: 16px; padding: 14px 16px; background: #fafafa; border: 1px solid #ececec; }
        .scope-icon { width: 10px; height: 10px; border-radius: 999px; background: #111111; margin-top: 7px; }
        .scope-item strong { display: block; font-size: 14px; color: #111111; }
        .scope-item p { margin-top: 4px; font-size: 13px; line-height: 1.55; color: #6b7280; }
        .signin h2 { font-size: 28px; color: #111111; margin-bottom: 8px; letter-spacing: -0.03em; }
        p.subtitle { color: #6b7280; margin-bottom: 28px; font-size: 14px; line-height: 1.6; }
        label { display: block; font-size: 14px; font-weight: 500; color: #374151; margin-bottom: 6px; }
        input[type="email"], input[type="password"], input[type="text"] { width: 100%; padding: 13px 16px; border: 1px solid #e5e7eb; border-radius: 12px; font-size: 15px; transition: border-color 0.2s, box-shadow 0.2s; margin-bottom: 20px; background: #ffffff; }
        input:focus { outline: none; border-color: #111111; box-shadow: 0 0 0 4px rgba(17,17,17,0.06); }
        button { width: 100%; padding: 13px; background: #111111; color: #ffffff; border: none; border-radius: 999px; font-size: 16px; font-weight: 800; cursor: pointer; transition: transform 0.1s, box-shadow 0.1s; box-shadow: 0 14px 28px rgba(17,17,17,0.14); }
        button:hover { transform: translateY(-1px); }
        button:active { transform: translateY(0); }
        .error { background: #fef2f2; color: #dc2626; padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }
        .brand-row { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
        .brand-lock { width: 48px; height: 48px; border-radius: 16px; display: flex; align-items: center; justify-content: center; background: #f5f5f5; border: 1px solid #e5e7eb; overflow: hidden; }
        .brand-lock img { width: 100%; height: 100%; object-fit: cover; }
        .brand-copy strong { display: block; font-size: 15px; }
        .brand-copy span { display: block; font-size: 13px; color: #6b7280; margin-top: 2px; }
        .disclosure { margin-top: 18px; font-size: 12px; line-height: 1.6; color: #6b7280; }
        .setup-box { margin-bottom: 18px; border: 1px solid #e5e7eb; border-radius: 16px; background: #fafafa; padding: 16px; }
        .setup-box strong { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.14em; color: #6b7280; margin-bottom: 8px; }
        .setup-key { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 15px; word-break: break-all; color: #111111; }
        .qr-box { margin-bottom: 18px; display: flex; justify-content: center; border: 1px solid #e5e7eb; border-radius: 16px; background: #fafafa; padding: 16px; }
        .qr-image { width: 180px; height: 180px; display: block; }
        .steps { margin: 0 0 18px 18px; color: #52525b; display: grid; gap: 8px; font-size: 14px; line-height: 1.6; }
        .motion-card { margin-top: 24px; display: flex; align-items: center; justify-content: center; border: 1px solid #e5e7eb; border-radius: 24px; background: linear-gradient(180deg, #ffffff, #f7f7f7); min-height: 280px; padding: 16px; }
        .motion-card dotlottie-wc { width: 300px; height: 300px; max-width: 100%; }
        .transition-shell { width: min(560px, 100%); border: 1px solid #e5e7eb; border-radius: 28px; background: rgba(255,255,255,0.96); box-shadow: 0 24px 60px rgba(15,23,42,0.08); padding: 28px; text-align: center; position: relative; z-index: 1; }
        .transition-logo { width: 56px; height: 56px; margin: 0 auto 16px; border-radius: 18px; border: 1px solid #e5e7eb; background: #f5f5f5; overflow: hidden; }
        .transition-logo img { width: 100%; height: 100%; object-fit: cover; }
        .transition-shell h1 { font-size: 28px; letter-spacing: -0.03em; color: #111111; }
        .transition-shell p { margin-top: 10px; font-size: 14px; line-height: 1.7; color: #6b7280; }
        .transition-motion { margin: 24px auto 18px; display: flex; justify-content: center; }
        .transition-motion dotlottie-wc { width: 300px; height: 300px; max-width: 100%; }
        .transition-note { margin-top: 8px; font-size: 12px; color: #71717a; }
        @media (max-width: 900px) {
          .shell { grid-template-columns: 1fr; }
          .context { border-right: none; border-bottom: 1px solid #e5e7eb; }
        }
    """


def _authorize_lottie_block(class_name: str = "motion-card") -> str:
    return f"""
        <div class="{class_name}">
            <dotlottie-wc
                src="{html.escape(LOTTIE_AUTH_ANIMATION_SRC)}"
                autoplay
                loop
            ></dotlottie-wc>
        </div>
    """


def render_authorize_transition_page(*, redirect_url: str, auth_state: dict) -> str:
    client_name = html.escape(auth_state.get("client_name") or "Application")
    safe_product_logo_url = html.escape(f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png")
    safe_redirect_url = html.escape(redirect_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting to {client_name}</title>
    <script src="{html.escape(LOTTIE_SCRIPT_SRC)}" type="module"></script>
    <style>{_authorize_brand_styles()}</style>
</head>
<body>
    <main class="transition-shell">
        <div class="transition-logo">
            <img src="{safe_product_logo_url}" alt="{html.escape(PRODUCT_NAME)} logo" />
        </div>
        <h1>Authentication successful</h1>
        <p>{html.escape(PRODUCT_NAME)} has verified your sign-in. We’re now redirecting you back to <strong>{client_name}</strong>.</p>
        <div class="transition-motion">
            <dotlottie-wc src="{html.escape(LOTTIE_AUTH_ANIMATION_SRC)}" autoplay loop></dotlottie-wc>
        </div>
        <p class="transition-note">If the redirect does not happen automatically, continue manually.</p>
        <form method="GET" action="{safe_redirect_url}" style="margin-top:18px;">
            <button type="submit">Continue to {client_name}</button>
        </form>
    </main>
    <script>
      window.setTimeout(() => {{
        window.location.href = {json.dumps(redirect_url)};
      }}, 1300);
    </script>
</body>
</html>"""


def render_logged_out_page(*, redirect_url: Optional[str] = None, client_name: Optional[str] = None) -> str:
    safe_product_logo_url = html.escape(f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png")
    safe_client_name = html.escape(client_name or "your application")
    continue_markup = ""
    script_markup = ""
    if redirect_url:
        safe_redirect_url = html.escape(redirect_url, quote=True)
        continue_markup = f"""
            <p class="transition-note">You can close this window, or continue back to {safe_client_name}.</p>
            <form method="GET" action="{safe_redirect_url}" style="margin-top:18px;">
                <button type="submit">Continue to {safe_client_name}</button>
            </form>
        """
        script_markup = f"""
    <script>
      window.setTimeout(() => {{
        window.location.href = {json.dumps(redirect_url)};
      }}, 1200);
    </script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Signed out</title>
    <style>{_authorize_brand_styles()}</style>
</head>
<body>
    <main class="transition-shell">
        <div class="transition-logo">
            <img src="{safe_product_logo_url}" alt="{html.escape(PRODUCT_NAME)} logo" />
        </div>
        <h1>You have been signed out</h1>
        <p>{html.escape(PRODUCT_NAME)} has ended your browser session. The next time you sign in from a client app, you will be asked to authenticate again.</p>
        {continue_markup}
    </main>{script_markup}
</body>
</html>"""


def render_authorize_mfa_page(
    *,
    state: str,
    challenge_token: str,
    auth_state: dict,
    challenge_type: str,
    manual_entry_key: Optional[str] = None,
    qr_code_data_url: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    client_name = auth_state.get("client_name") or "Application"
    client_logo_url = auth_state.get("client_logo_url")
    redirect_uri = auth_state.get("redirect_uri") or ""
    requested_scopes = auth_state.get("requested_scopes") or ["openid"]

    safe_client_name = html.escape(client_name)
    safe_redirect_host = html.escape(redirect_uri.split("/")[2] if "://" in redirect_uri else redirect_uri)
    safe_product_logo_url = html.escape(f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png")
    safe_manual_entry_key = html.escape(manual_entry_key or "")
    safe_qr_code_data_url = html.escape(qr_code_data_url or "")
    error_markup = f'<div class="error">{html.escape(error_message)}</div>' if error_message else ""
    logo_markup = (
        f"<img src=\"{html.escape(client_logo_url)}\" alt=\"{safe_client_name} logo\" class=\"client-logo-image\" />"
        if client_logo_url else
        f"<div class=\"client-logo-fallback\">{html.escape(client_name[:2].upper())}</div>"
    )
    scope_items = "".join(
        f"""
        <li class="scope-item">
            <div class="scope-icon"></div>
            <div>
                <strong>{html.escape(SCOPE_LABELS.get(scope_name, (scope_name.replace('_', ' ').replace(':', ' ').title(), 'Access requested by this application.'))[0])}</strong>
                <p>{html.escape(SCOPE_LABELS.get(scope_name, (scope_name.replace('_', ' ').replace(':', ' ').title(), 'Access requested by this application.'))[1])}</p>
            </div>
        </li>
        """
        for scope_name in requested_scopes
    )
    setup_markup = ""
    title = "Enter your authenticator code"
    subtitle = f"Use the current 6-digit code from Google Authenticator to continue authorizing {safe_client_name}."
    if challenge_type == "setup":
        title = "Set up Google Authenticator"
        subtitle = f"Your organization requires multi-factor authentication before {safe_client_name} can be authorized."
        setup_markup = f"""
            {'<div class="qr-box"><img src="' + safe_qr_code_data_url + '" alt="Authenticator setup QR code" class="qr-image" /></div>' if safe_qr_code_data_url else ''}
            <ol class="steps">
                <li>Open Google Authenticator and scan this QR code.</li>
                <li>Choose <strong>Enter a setup key</strong>.</li>
                <li>Use your email address as the account name.</li>
                <li>If scanning is not available, paste the setup key below, then enter the 6-digit code here.</li>
            </ol>
            <div class="setup-box">
                <strong>Manual setup key</strong>
                <div class="setup-key">{safe_manual_entry_key}</div>
            </div>
        """
    else:
        subtitle = f"Use the current 6-digit code from Google Authenticator, or enter one of your backup codes, to continue authorizing {safe_client_name}."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MFA - {safe_client_name}</title>
    <style>{_authorize_brand_styles()}</style>
</head>
<body>
    <div class="shell">
        <section class="context">
            <div class="eyebrow">Authorization Request</div>
            <h1>{safe_client_name} wants access to your {html.escape(PRODUCT_NAME)} account.</h1>
            <p class="context-copy">Complete multi-factor verification to continue the authorization request securely.</p>
            <div class="client-card">
                <div class="client-top">
                    {logo_markup}
                    <div>
                        <div class="client-label">Requesting application</div>
                        <div class="client-name">{safe_client_name}</div>
                        <div class="client-host">{safe_redirect_host or "Unknown redirect host"}</div>
                    </div>
                </div>
                <div class="scope-panel">
                    <h2>This app is requesting access to:</h2>
                    <ul class="scope-list">{scope_items}</ul>
                </div>
            </div>
        </section>
        <section class="signin">
            <div class="brand-row">
                <div class="brand-lock">
                    <img src="{safe_product_logo_url}" alt="{html.escape(PRODUCT_NAME)} logo" />
                </div>
                <div class="brand-copy">
                    <strong>{html.escape(PRODUCT_NAME)}</strong>
                    <span>{html.escape(PRODUCT_TAGLINE)}</span>
                </div>
            </div>
            <h2>{title}</h2>
            <p class="subtitle">{subtitle}</p>
            {error_markup}
            {setup_markup}
            <form method="POST" action="/api/v1/authorize/mfa-submit">
                <input type="hidden" name="state" value="{html.escape(state)}" />
                <input type="hidden" name="challenge_token" value="{html.escape(challenge_token)}" />
                <label for="code">{'Authenticator code' if challenge_type == 'setup' else 'Authenticator or backup code'}</label>
                <input type="text" id="code" name="code" {'inputmode="numeric" maxlength="6" autocomplete="one-time-code"' if challenge_type == 'setup' else 'maxlength="24" autocomplete="one-time-code"'} required placeholder="{'123456' if challenge_type == 'setup' else '123456 or ABCD-EFGH-IJKL'}" />
                <button type="submit">{'Verify And Finish Setup' if challenge_type == 'setup' else 'Verify And Continue'}</button>
            </form>
            <p class="disclosure">If you did not expect this authorization request, close this window and contact your administrator.</p>
        </section>
    </div>
</body>
</html>"""


def render_authorize_backup_codes_page(
    *,
    redirect_url: str,
    auth_state: dict,
    backup_codes: list[str],
) -> str:
    client_name = html.escape(auth_state.get("client_name") or "Application")
    safe_product_logo_url = html.escape(f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png")
    backup_items = "".join(f"<li>{html.escape(code)}</li>" for code in backup_codes)
    backup_codes_text = html.escape("\n".join(backup_codes))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Save your backup codes</title>
    <script src="{html.escape(LOTTIE_SCRIPT_SRC)}" type="module"></script>
    <style>{_authorize_brand_styles()}
        .backup-panel {{ border: 1px solid #dbe3ef; border-radius: 18px; background: #f8fafc; padding: 18px; margin: 18px 0; }}
        .backup-list {{ list-style: none; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; padding: 0; }}
        .backup-list li {{ border-radius: 12px; border: 1px solid #e2e8f0; background: #fff; padding: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; text-align: center; color: #0f172a; }}
        .backup-copy {{ width: 100%; margin-top: 12px; padding: 12px; border-radius: 12px; border: 1px solid #dbe3ef; background: #fff; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: #334155; }}
        .backup-note {{ margin-top: 14px; font-size: 12px; line-height: 1.6; color: #64748b; }}
    </style>
</head>
<body>
    <div class="shell">
        <section class="context">
            <div class="eyebrow">Recovery Codes</div>
            <h1>Save these backup codes before you continue.</h1>
            <p class="context-copy">You can use each code once if you lose access to Google Authenticator for your {html.escape(PRODUCT_NAME)} account.</p>
            {_authorize_lottie_block()}
        </section>
        <section class="signin">
            <div class="brand-row">
                <div class="brand-lock">
                    <img src="{safe_product_logo_url}" alt="{html.escape(PRODUCT_NAME)} logo" />
                </div>
                <div class="brand-copy">
                    <strong>{html.escape(PRODUCT_NAME)}</strong>
                    <span>{client_name} authorization</span>
                </div>
            </div>
            <h2>Backup codes ready</h2>
            <p class="subtitle">These codes are shown only once. Store them somewhere safe before you continue.</p>
            <div class="backup-panel">
                <ul class="backup-list">{backup_items}</ul>
                <textarea class="backup-copy" rows="6" readonly>{backup_codes_text}</textarea>
                <p class="backup-note">Each backup code works once and will be invalidated after use.</p>
            </div>
            <form method="GET" action="{html.escape(redirect_url)}">
                <button type="submit">I saved my backup codes</button>
            </form>
        </section>
    </div>
</body>
</html>"""


def render_authorize_login_page(*, state: str, auth_state: dict, error_message: Optional[str] = None) -> str:
    client_name = auth_state.get("client_name") or "Application"
    client_logo_url = auth_state.get("client_logo_url")
    redirect_uri = auth_state.get("redirect_uri") or ""
    requested_scopes = auth_state.get("requested_scopes") or ["openid"]

    safe_client_name = html.escape(client_name)
    safe_redirect_host = html.escape(redirect_uri.split("/")[2] if "://" in redirect_uri else redirect_uri)
    safe_product_logo_url = html.escape(f"{settings.ADMIN_CONSOLE_URL.rstrip('/')}/logo.png")
    safe_error_message = html.escape(error_message) if error_message else ""
    error_markup = (
        f'<div class="error" style="display:block">{safe_error_message}</div>'
        if safe_error_message
        else '<div class="error" id="error"></div>'
    )
    logo_markup = (
        f"<img src=\"{html.escape(client_logo_url)}\" alt=\"{safe_client_name} logo\" class=\"client-logo-image\" />"
        if client_logo_url else
        f"<div class=\"client-logo-fallback\">{html.escape(client_name[:2].upper())}</div>"
    )
    scope_items = "".join(
        f"""
        <li class="scope-item">
            <div class="scope-icon"></div>
            <div>
                <strong>{html.escape(SCOPE_LABELS.get(scope_name, (scope_name.replace('_', ' ').replace(':', ' ').title(), 'Access requested by this application.'))[0])}</strong>
                <p>{html.escape(SCOPE_LABELS.get(scope_name, (scope_name.replace('_', ' ').replace(':', ' ').title(), 'Access requested by this application.'))[1])}</p>
            </div>
        </li>
        """
        for scope_name in requested_scopes
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In - {safe_client_name}</title>
    <style>{_authorize_brand_styles()} .error {{ display: none; }}</style>
</head>
<body>
    <div class="shell">
        <section class="context">
            <div class="eyebrow">Authorization Request</div>
            <h1>{safe_client_name} wants access to your {html.escape(PRODUCT_NAME)} account.</h1>
            <p class="context-copy">Review the client application below, then sign in to continue. This mirrors the familiar OAuth experience where the identity provider shows who is asking and what access is being requested.</p>
            <div class="client-card">
                <div class="client-top">
                    {logo_markup}
                    <div>
                        <div class="client-label">Requesting application</div>
                        <div class="client-name">{safe_client_name}</div>
                        <div class="client-host">{safe_redirect_host or "Unknown redirect host"}</div>
                    </div>
                </div>
                <div class="scope-panel">
                    <h2>This app is requesting access to:</h2>
                    <ul class="scope-list">
                        {scope_items}
                    </ul>
                </div>
            </div>
        </section>
        <section class="signin">
            <div class="brand-row">
                <div class="brand-lock">
                    <img src="{safe_product_logo_url}" alt="{html.escape(PRODUCT_NAME)} logo" />
                </div>
                <div class="brand-copy">
                    <strong>{html.escape(PRODUCT_NAME)}</strong>
                    <span>{html.escape(PRODUCT_TAGLINE)}</span>
                </div>
            </div>
            <h2>Sign in to continue</h2>
            <p class="subtitle">You are authorizing <strong>{safe_client_name}</strong> to access the permissions shown on the left.</p>
            {error_markup}
            <form method="POST" action="/api/v1/authorize/submit">
                <input type="hidden" name="state" value="{state}" />
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required placeholder="you@example.com" />
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required placeholder="••••••••" />
                <button type="submit">Authorize And Sign In</button>
            </form>
            <p class="disclosure">Only configured scopes for this application are shown. If the request looks unexpected, close this page and contact your administrator.</p>
        </section>
    </div>
</body>
</html>"""


def login_error_page(state: str, error_msg: str) -> str:
    """Preserve branded UI by redirecting back to authorize/login-page with error text."""
    encoded_error = quote(error_msg, safe="")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting...</title>
    <meta http-equiv="refresh" content="0;url=/api/v1/authorize/login-page?state={state}&error={encoded_error}">
</head>
<body>
    Redirecting...
</body>
</html>"""
