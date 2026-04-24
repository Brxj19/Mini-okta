# SigAuth

Identity orchestration by Sigmoid Analytics.

Production-style Identity Provider with OIDC Authorization Code + PKCE, multi-tenant admin console, RBAC, audit logs, invitation onboarding, password lifecycle controls, and app/group scoping.

Integration documentation for external developers:
- [App Integration Guide](./doc/APP_INTEGRATION_GUIDE.md)
- [Detailed Local Runbook](./RUNBOOK.md)

## What Runs

| Component | Port | Purpose |
|---|---:|---|
| IdP Backend (FastAPI) | `8000` | OIDC, admin APIs, token/session/audit logic |
| Admin Frontend (React/Vite) | `3000` | Org/user/group/app/role/audit management UI |
| HR Demo Client | `4000` | OIDC demo client |
| Project Tracker Demo Client | `4001` | OIDC demo client |
| SigVerse Frontend | `5173` | OIDC-integrated sample app |
| SigVerse Backend (Express) | `3100` | Resource server validating IdP tokens |
| PostgreSQL | `5432` | Main IdP data |
| Redis | `6379` | Session + rate-limit cache |
| MailHog (optional) | `1025` / `8025` | Local SMTP capture + inbox UI |

---

## Prerequisites

- Python `3.11+`
- Node.js `18+` (Node `20+` recommended)
- PostgreSQL `15+`
- Redis `7+`
- Docker (optional, for MailHog)
- For SigVerse only: MySQL + MongoDB

---

## 1. Configure Environment

From repo root:

```bash
cp .env.example backend/.env
```

Review `backend/.env` and keep at least:

- `DATABASE_URL=postgresql+asyncpg://localhost:5432/idp`
- `REDIS_URL=redis://localhost:6379/0`
- `ISSUER_URL=http://localhost:8000`
- `ADMIN_CONSOLE_URL=http://localhost:3000`

For MailHog local email testing:

```dotenv
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USE_TLS=false
SMTP_STARTTLS=false
SMTP_USER=
SMTP_PASS=
SMTP_FROM=noreply@internal.com
```

---

## 2. Start Infrastructure

Create database:

```bash
createdb idp
```

Start Redis (example with Homebrew):

```bash
brew services start redis
```

Optional: start MailHog

```bash
docker run -d --name mailhog -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

Mail UI: `http://localhost:8025`

---

## 3. Run IdP Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload --port 8000
```

Notes:
- If `alembic` command is missing, use `python -m alembic ...`.
- Ensure you are migrated in the same DB as `DATABASE_URL` (`idp`), not the default `postgres` DB.

Backend smoke checks:

```bash
curl http://localhost:8000/
curl http://localhost:8000/api/v1/.well-known/openid-configuration
```

---

## 4. Run Admin Console

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:3000`

Default seeded users:

| User | Email | Password |
|---|---|---|
| Super Admin | value of `ADMIN_EMAIL` in `backend/.env` | value of `ADMIN_SECRET` in `backend/.env` |
| Sample User | `alice@internal.com` | `Test@1234` |
| Sample User | `bob@internal.com` | `Test@1234` |

---

## 5. Run Demo OIDC Clients

HR Portal:

```bash
cd clients/hr-portal
npm install
npm run dev
```

Project Tracker:

```bash
cd clients/project-tracker
npm install
npm run dev
```

Use seeded app clients:
- HR: `client_id=hr-portal-client-id`, redirect `http://localhost:4003/auth/callback`
- Project Tracker: `client_id=project-tracker-client-id`, redirect `http://localhost:4001/callback`

---

## 6. Run SigVerse (OIDC + App Groups)

SigVerse frontend and backend live in `clients/SigVerse`.

### Backend (Express on 3100)

1. Configure `clients/SigVerse/backend/.env` (local DB + IdP settings).
2. Ensure these are correct:
   - `IDP_ISSUER_URL=http://localhost:8000`
   - `IDP_CLIENT_ID=<SigVerse app client_id from IdP>`
   - `IDP_PUBLIC_KEY_PATH=../../../backend/secrets/public.pem`
   - `SIGVERSE_ADMIN_GROUPS=sigverse-admins,admins`
   - `SIGVERSE_INSTRUCTOR_GROUPS=sigverse-instructors,instructors`
   - `SIGVERSE_ADMIN_APP_ROLES=app:admin,admin`
   - `SIGVERSE_INSTRUCTOR_APP_ROLES=app:instructor,instructor`
   - `SIGVERSE_LEARNER_APP_ROLES=app:learner,learner`

Run:

```bash
cd clients/SigVerse/backend
npm install
npm run dev
```

### Frontend (Vite on 5173)

Set `clients/SigVerse/frontend/.env`:

```dotenv
VITE_API_URL=http://localhost:3100
VITE_IDP_URL=http://localhost:8000
VITE_IDP_CLIENT_ID=<same SigVerse client_id>
VITE_IDP_REDIRECT_URI=http://localhost:5173/auth/callback
```

Run:

```bash
cd clients/SigVerse/frontend
npm install
npm run dev -- --port 5173
```

### SigVerse App Registration Checklist (in Admin UI)

1. Create application with type `spa`.
2. Add redirect URI `http://localhost:5173/auth/callback`.
3. Allowed scopes: `openid profile email`.
4. Assign application groups (for example `sigverse-admins`, `sigverse-instructors`, `sigverse-learners`).
5. Add users to those groups.

### One-command SigVerse IdP bootstrap (optional)

After running the base IdP seed, you can auto-configure the SigVerse app/groups/users:

```bash
cd backend
python scripts/seed_sigverse.py
```

This script is idempotent and will:
- create/update the SigVerse SPA app with `client_id=GfRUxhhDZeKl1b6IoatrdMQdlCEsRQEY`
- create `sigverse-admins`, `sigverse-instructors`, `sigverse-learners`
- assign those groups to the SigVerse app
- create seeded users and attach each to the matching group

---

## 7. End-to-End Test Checklist

1. Login to admin console (`http://localhost:3000`) as super admin.
2. Create organization from **Organizations**.
3. Create user from **Users**:
   - Invitation email should appear in MailHog.
   - Open setup link and set first password.
4. Trigger reset password:
   - Email appears in MailHog.
   - Reset flow works at `/password-reset/confirm`.
5. Add/remove user to/from group:
   - Audit row is created.
   - Notification email is queued/sent.
6. Suspend and unlock user:
   - Login blocked while suspended.
   - Unlock restores access.
7. Open **Email Queue** page:
   - Check `pending/sent/failed/dead` states.
8. Open **Audit Log** detail page:
   - Metadata renders in structured UI.
9. Login to SigVerse and verify route access:
   - `sigverse-admins` => admin UI access.
   - instructor groups => instructor routes.
   - others => learner routes.

---

## 8. Build and Validation Commands

Backend syntax check:

```bash
cd backend
python3 -m py_compile app/main.py app/routers/*.py app/services/*.py app/models/*.py app/schemas/*.py
```

Admin frontend build:

```bash
cd frontend
npm run build
```

SigVerse builds:

```bash
cd clients/SigVerse/frontend && npm run build
cd clients/SigVerse/backend && npm start
```

---

## 9. Common Troubleshooting

- Migration says success but schema not updated:
  - You are likely connected to a different DB. Check `DATABASE_URL` and query `alembic_version` in that DB.
- No emails in MailHog:
  - Confirm `SMTP_HOST/PORT`, `SMTP_USE_TLS=false`, `SMTP_STARTTLS=false`.
  - Check admin UI **Email Queue** for `last_error`.
- `401 invalid/expired token` in SigVerse:
  - Verify `IDP_CLIENT_ID` matches token `aud`.
  - Verify `IDP_PUBLIC_KEY_PATH` points to IdP public key.
- OIDC callback fails:
  - Redirect URI in app config must exactly match the runtime callback URL.

---

## Key API Surfaces

- Auth: `/api/v1/login`, `/api/v1/authorize`, `/api/v1/token`, `/api/v1/logout`, `/api/v1/userinfo`
- Discovery/JWKS: `/api/v1/.well-known/openid-configuration`, `/api/v1/.well-known/jwks.json`
- Password flows: `/api/v1/password-reset/request`, `/api/v1/password-reset/confirm`, `/api/v1/password-setup/confirm`
- Admin orgs: `/api/v1/admin/organizations`
- Tenant resources: `/api/v1/organizations/{org_id}/users|groups|applications|roles|audit-log|email-deliveries`

## License

MIT
