# SigAuth Runbook

This is the detailed local setup guide for the full SigAuth project, including the admin console, backend APIs, seeded demo data, MailHog email capture, billing lifecycle scripts, tests, and the SigVerse client-app integration flow.

## 1. What This Repository Contains

| Component | Default Port | Purpose |
| --- | ---: | --- |
| SigAuth backend | `8000` | OIDC provider, admin APIs, MFA, notifications, billing, email queue |
| SigAuth frontend | `3000` | Admin console and landing pages |
| HR Portal frontend | `4000` | Demo web client UI |
| HR Portal backend | `4003` | Cookie-session backend for HR Portal |
| Project Tracker frontend | `4001` | Demo SPA client UI |
| Project Tracker backend | `4002` | Cookie-session backend for Project Tracker |
| Logistica frontend | `4101` | Logistics demo client UI |
| Logistica backend | `4100` | Cookie-session backend for Logistica |
| SigVerse frontend | `5173` | OIDC-integrated sample learning app |
| SigVerse backend | `3100` | Learning-app backend with local app session cookie |
| PostgreSQL | `5432` | Primary SigAuth database |
| Redis | `6379` | Sessions, MFA/login cache, rate limiting |
| MailHog SMTP | `1025` | Local outgoing email capture |
| MailHog UI | `8025` | Inspect emails in the browser |

## 2. Prerequisites

Install these first:

- Python `3.11+`
- Node.js `18+` or `20+`
- PostgreSQL `15+`
- Redis `7+`
- Docker optional, but easiest for MailHog
- For SigVerse only: MySQL and MongoDB

On macOS with Homebrew, a typical local setup is:

```bash
brew install python@3.11 node postgresql redis
brew services start postgresql
brew services start redis
```

## 3. Repository Setup

From the project root:

```bash
cd /Users/as-mac-1293/Desktop/mini-okta-v2.2
```

If you have not created the database yet:

```bash
createdb idp
```

If `createdb idp` says the database already exists, that is fine.

## 4. Backend Environment Setup

The backend reads configuration from `backend/.env`.

Create or update `backend/.env` with at least this local-development baseline:

```dotenv
DATABASE_URL=postgresql+asyncpg://localhost:5432/idp
REDIS_URL=redis://localhost:6379/0

RSA_PRIVATE_KEY_PATH=secrets/private.pem
RSA_PUBLIC_KEY_PATH=secrets/public.pem
ISSUER_URL=http://localhost:8000
ADMIN_CONSOLE_URL=http://localhost:3000

ADMIN_EMAIL=admin@internal.com
ADMIN_SECRET=changeme_admin_secret!

SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASS=
SMTP_PASSWORD=
SMTP_FROM=noreply@internal.com
SMTP_USE_TLS=false
SMTP_STARTTLS=false

PAYMENTS_PROVIDER=demo
BILLING_CURRENCY=INR
SUBSCRIPTION_CYCLE_DAYS=30

RATE_LIMIT_ENABLED=true
ACCESS_TOKENS_ENABLED=true
REFRESH_TOKENS_ENABLED=true
```

Notes:

- `PAYMENTS_PROVIDER=demo` is the correct setting for your current internship-demo billing flow.
- If you later switch to Razorpay, replace `demo` and add the Razorpay keys.
- RSA key paths already point to the checked-in local dev keys in `backend/secrets/`.

## 5. Backend Python Virtual Environment

Create the virtual environment and install dependencies:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Important note:

- Use `python -m pip ...` instead of `pip ...` if your machine has multiple Python installations.
- Use `venv/bin/python -m alembic ...` if the plain `python3 -m alembic` command is picking up the wrong environment.

## 6. MailHog Setup

MailHog is recommended for local testing because all invitations, password reset emails, verification emails, MFA alerts, and notification emails will show up there.

Option A: Docker

```bash
docker run -d --name mailhog -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

Option B: if MailHog is already installed locally, just run it with SMTP on `1025` and web UI on `8025`.

Open the inbox UI at:

```text
http://localhost:8025
```

## 7. Database Migrations

Run migrations from inside `backend`:

```bash
cd backend
source venv/bin/activate
venv/bin/python -m alembic upgrade head
```

If you prefer while the venv is activated:

```bash
python -m alembic upgrade head
```

If you ever see this error:

```text
No module named alembic.__main__
```

that usually means the current Python process is not using the backend virtual environment. Activate the venv and use:

```bash
venv/bin/python -m alembic upgrade head
```

## 8. Seed the Base Demo Data

After migrations, seed the base platform:

```bash
cd backend
source venv/bin/activate
python scripts/seed.py
```

This creates:

- default organization
- system roles
- super admin user
- sample users Alice and Bob
- sample groups
- sample applications

Default seeded accounts:

| User | Email | Password |
| --- | --- | --- |
| Super admin | `admin@internal.com` unless overridden in `.env` | value of `ADMIN_SECRET` |
| Alice | `alice@internal.com` | `Test@1234` |
| Bob | `bob@internal.com` | `Test@1234` |

## 9. Start the Backend

Run the API server:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Useful checks:

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/.well-known/openid-configuration
```

Useful URLs:

- API base: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/api/docs`
- Developer docs: `http://localhost:8000/docs`

## 10. Frontend Setup and Run

In a new terminal:

```bash
cd /Users/as-mac-1293/Desktop/mini-okta-v2.2/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The landing page, login, signup, password reset flow, settings, notifications, billing page, and docs links all route from here.

## 11. Run All Four Demo Clients with the Session-Cookie Flow

All client apps now follow the same safer pattern:

- browser keeps only temporary PKCE values in `sessionStorage`
- the client backend exchanges the authorization code with SigAuth
- the client backend stores app auth in an `HttpOnly` session cookie
- the frontend bootstraps from its own `/auth/session` endpoint
- logout can stay local to the client app, or escalate into SigAuth logout

Recommended terminal layout:

1. terminal 1: SigAuth backend
2. terminal 2: SigAuth frontend
3. terminal 3: HR Portal backend
4. terminal 4: HR Portal frontend
5. terminal 5: Project Tracker backend
6. terminal 6: Project Tracker frontend
7. terminal 7: Logistica backend
8. terminal 8: Logistica frontend
9. terminal 9: SigVerse backend
10. terminal 10: SigVerse frontend

### 11.1 HR Portal

Backend env:

```bash
cp clients/hr-portal/backend/.env.example clients/hr-portal/backend/.env
```

Backend:

```bash
cd clients/hr-portal/backend
npm install
npm run dev
```

Frontend:

```bash
cd clients/hr-portal
npm install
npm run dev
```

Open:

```text
http://localhost:4000
```

SigAuth application values:

- client type: `web`
- client ID: `hr-portal-client-id`
- client secret: set this in `clients/hr-portal/backend/.env`
- redirect URI: `http://localhost:4003/auth/callback`
- post logout redirect URI: `http://localhost:4000`

### 11.2 Project Tracker

Backend env:

```bash
cp clients/project-tracker/backend/.env.example clients/project-tracker/backend/.env
```

Backend:

```bash
cd clients/project-tracker/backend
npm install
npm run dev
```

Frontend:

```bash
cd clients/project-tracker
npm install
npm run dev
```

Open:

```text
http://localhost:4001
```

SigAuth application values:

- client type: `spa`
- client ID: `project-tracker-client-id`
- redirect URI: `http://localhost:4001/callback`
- post logout redirect URI: `http://localhost:4001`

### 11.3 Logistica Delivery

Backend env:

```bash
cp clients/logistica-delivery/backend/.env.example clients/logistica-delivery/backend/.env
```

If you already created the Logistica app in SigAuth, update `IDP_CLIENT_ID` in that file before you start the backend.

Backend:

```bash
cd clients/logistica-delivery/backend
npm install
npm run dev
```

Frontend:

```bash
cd clients/logistica-delivery/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:4101
```

SigAuth application values:

- client type: `spa`
- redirect URI: `http://localhost:4101/auth/callback`
- post logout redirect URI: `http://localhost:4101`

### 11.4 SigVerse

Backend env:

```bash
cp clients/SigVerse/backend/.env.example clients/SigVerse/backend/.env
```

Then update these values inside `clients/SigVerse/backend/.env`:

- `MYSQL_*` to your local or cloud SigVerse MySQL database
- `MONGO_URI` to your SigVerse MongoDB instance
- `IDP_CLIENT_ID` to the SigVerse app client ID from SigAuth

Backend:

```bash
cd clients/SigVerse/backend
npm install
npm run dev
```

Frontend env:

```bash
cp clients/SigVerse/frontend/.env.example clients/SigVerse/frontend/.env
```

Then set `VITE_IDP_CLIENT_ID` in that file to match the SigVerse SigAuth app.

Frontend:

```bash
cd clients/SigVerse/frontend
npm install
npm run dev -- --port 5173
```

Open:

```text
http://localhost:5173/login
```

SigAuth application values:

- client type: `spa`
- redirect URI: `http://localhost:5173/auth/callback`
- post logout redirect URI: `http://localhost:5173`

## 12. Running Tests and Syntax Checks

### Backend unit and API tests

```bash
cd backend
source venv/bin/activate
venv/bin/python -m unittest discover -s tests -v
```

### Backend syntax/import compilation

```bash
cd backend
source venv/bin/activate
venv/bin/python -m compileall app scripts
```

### Frontend production build

```bash
cd frontend
npm run build
```

These three are the recommended minimum validation commands before a demo.

## 13. Email and Notification Scheduled Jobs

Two backend scripts are intended to run on a schedule.

### Weekly summary emails

```bash
cd backend
source venv/bin/activate
python scripts/send_weekly_summaries.py
```

### Subscription reminder and expiry notifications

```bash
cd backend
source venv/bin/activate
python scripts/process_subscription_notifications.py
```

### Soft-delete purge after 90 days

```bash
cd backend
source venv/bin/activate
python scripts/purge_soft_deletes.py
```

You can also copy the ready-to-use repo template:

```bash
cd /Users/as-mac-1293/Desktop/mini-okta-v2.2
crontab cron.example
```

For temporary verification with short intervals, use:

```bash
cd /Users/as-mac-1293/Desktop/mini-okta-v2.2
crontab cron.test.example
```

Or paste these entries manually with `crontab -e`:

```cron
0 9 * * 1 cd /Users/as-mac-1293/Desktop/mini-okta-v2.2/backend && venv/bin/python scripts/send_weekly_summaries.py >> /tmp/sigauth-weekly-summaries.log 2>&1
30 8 * * * cd /Users/as-mac-1293/Desktop/mini-okta-v2.2/backend && venv/bin/python scripts/process_subscription_notifications.py >> /tmp/sigauth-subscription-notifications.log 2>&1
15 2 * * * cd /Users/as-mac-1293/Desktop/mini-okta-v2.2/backend && venv/bin/python scripts/purge_soft_deletes.py >> /tmp/sigauth-soft-delete-purge.log 2>&1
```

What each job does:

- `send_weekly_summaries.py`: sends weekly summary emails to users who opted in
- `process_subscription_notifications.py`: sends renewal reminders, cancel-at-period-end reminders, and downgrade expiry notices
- `purge_soft_deletes.py`: permanently removes soft-deleted users, applications, and organizations older than 90 days

Useful test-mode overrides:

- `python scripts/send_weekly_summaries.py --window-days 1 --force`
- `python scripts/process_subscription_notifications.py --renewal-window-days 365 --cancel-window-days 365`
- `python scripts/purge_soft_deletes.py --retention-days 0`

Verify the installed schedule with:

```bash
crontab -l
```

## 14. SigVerse Quick Start

SigVerse is the most complete example client app in this repo.

There are two ways to connect it:

- Quick path: use the SigVerse seed script
- Manual path: create a new organization and configure the client app yourself

### 14.1 Quick Path Using the SigVerse Seed Script

After the base backend seed is done:

```bash
cd backend
source venv/bin/activate
python scripts/seed_sigverse.py
```

What the script does:

- creates or reuses a SPA app named `SigVerse`
- default client ID: `GfRUxhhDZeKl1b6IoatrdMQdlCEsRQEY`
- default redirect URI: `http://localhost:5173/auth/callback`
- creates groups:
  - `sigverse-admins`
  - `sigverse-instructors`
  - `sigverse-learners`
- assigns those groups to the SigVerse app
- creates seeded users:
  - `sigverse.admin@gmail.com`
  - `sigverse.instructor@gmail.com`
  - `sigverse.learner@gmail.com`
- default seeded password: `Test@1234`

You can override the defaults before running the script:

```bash
export SIGVERSE_CLIENT_ID=your-client-id
export SIGVERSE_REDIRECT_URI=http://localhost:5173/auth/callback
export SIGVERSE_DEMO_PASSWORD=Test@1234
python scripts/seed_sigverse.py
```

## 15. SigVerse Manual Setup with a New Organization

Use this if you want the demo to show a fresh organization created in SigAuth instead of the default org.

### 15.1 Create the organization

1. Open `http://localhost:3000/signup`
2. Create a new self-serve organization
3. Sign in as that organization admin
4. If needed, upgrade the org plan from the billing page so you are not blocked by self-serve limits

### 15.2 Create the SigVerse groups

Inside the organization admin console:

1. Go to `Groups`
2. Create:
   - `sigverse-admins`
   - `sigverse-instructors`
   - `sigverse-learners`

### 15.3 Create the SigVerse application

Inside `Applications`, create a new app with these values:

- Name: `SigVerse`
- App type: `spa`
- Redirect URI: `http://localhost:5173/auth/callback`
- Allowed scopes:
  - `openid`
  - `profile`
  - `email`
- Status: active

After the app is created, copy the generated `client_id`.

### 15.4 Assign the application to groups

Open the SigVerse application detail page and assign:

- `sigverse-admins`
- `sigverse-instructors`
- `sigverse-learners`

This is required so users in those groups can actually see and launch the SigVerse app.

### 15.5 Create or invite SigVerse users

In `Users`, create or invite users for each access tier:

- one admin user
- one instructor user
- one learner user

Then add them to the correct groups:

- admin user -> `sigverse-admins`
- instructor user -> `sigverse-instructors`
- learner user -> `sigverse-learners`

Finish each invite/setup email from MailHog if you are using invite-first onboarding.

## 16. SigVerse Backend Configuration

Create or update:

```text
clients/SigVerse/backend/.env
```

The important SigAuth session values are:

```dotenv
FRONTEND_URL=http://localhost:5173
IDP_ISSUER_URL=http://localhost:8000
IDP_CLIENT_ID=<the SigVerse client_id from SigAuth>
IDP_REDIRECT_URI=http://localhost:5173/auth/callback
POST_LOGOUT_REDIRECT_URI=http://localhost:5173

APP_SESSION_COOKIE_NAME=sigverse_session
APP_SESSION_SECRET=change-me-sigverse-session-secret
APP_SESSION_TTL_SECONDS=28800
APP_SESSION_COOKIE_SECURE=false

SIGVERSE_ADMIN_APP_ROLES=app:admin,admin
SIGVERSE_INSTRUCTOR_APP_ROLES=app:instructor,instructor
SIGVERSE_LEARNER_APP_ROLES=app:learner,learner
```

Important note:

- `IDP_CLIENT_ID` must match the SigVerse application created in SigAuth.
- SigVerse now uses the backend code-exchange plus app-session-cookie flow, so its primary login path no longer depends on storing IdP tokens in the browser.
- `SIGVERSE_*_APP_ROLES` is now the preferred mapping mechanism. Group-name env mapping is no longer the recommended pattern.

Run SigVerse backend:

```bash
cd clients/SigVerse/backend
npm install
npm run dev
```

The backend still needs its own MySQL and MongoDB configuration in its `.env`. Keep those aligned with however you are already running SigVerse locally.

## 17. SigVerse Frontend Configuration

Create or update:

```text
clients/SigVerse/frontend/.env
```

Recommended values:

```dotenv
VITE_API_URL=http://localhost:3100
VITE_IDP_URL=http://localhost:8000
VITE_IDP_CLIENT_ID=<the same SigVerse client_id>
VITE_IDP_REDIRECT_URI=http://localhost:5173/auth/callback
```

Run SigVerse frontend:

```bash
cd clients/SigVerse/frontend
npm install
npm run dev -- --port 5173
```

Open:

```text
http://localhost:5173/login
```

## 18. End-to-End SigVerse Verification Flow

After SigAuth backend, SigAuth frontend, SigVerse backend, and SigVerse frontend are all running:

1. Open `http://localhost:5173/login`
2. Click `Continue with SigAuth`
3. You should be redirected to the SigAuth authorize login page
4. Sign in with a SigAuth user assigned to the SigVerse application
5. Complete MFA if the user or org requires it
6. Watch the redirect loading screen
7. Return to SigVerse authenticated

Expected access behavior:

- organization admins can log into any app in their organization
- regular users need assignment via an application group
- app role mappings are optional for access itself
- SigVerse derives its internal role primarily from `app_roles`, with org admin fallback for platform admins
- local logout should clear only the SigVerse app session unless the user explicitly chooses SigAuth logout

## 18.1 What Each Demo Client Uses

This is the current shared client pattern in the repo:

| Client | Frontend URL | Backend URL | Session storage model |
| --- | --- | --- | --- |
| HR Portal | `http://localhost:4000` | `http://localhost:4003` | backend-managed `HttpOnly` cookie |
| Project Tracker | `http://localhost:4001` | `http://localhost:4002` | backend-managed `HttpOnly` cookie |
| Logistica | `http://localhost:4101` | `http://localhost:4100` | backend-managed `HttpOnly` cookie |
| SigVerse | `http://localhost:5173` | `http://localhost:3100` | backend-managed `HttpOnly` cookie |

The frontend in each client stores only temporary PKCE values during the redirect flow.

## 19. Demo-Friendly Manual Checks

These are the best checks to run before showing the project:

1. Sign into `http://localhost:3000` as super admin
2. Create a new organization
3. Create or invite a user
4. Confirm the invitation email lands in MailHog
5. Complete password setup
6. Trigger password reset and confirm the reset email lands in MailHog
7. Enable MFA in settings and verify login challenge works
8. Assign a user to an app group and confirm the app appears in `My Apps`
9. Upgrade or manage the billing plan for a self-serve org
10. Open notifications and confirm recent activity appears
11. Open `http://localhost:8000/docs` and verify docs render correctly
12. Complete a SigVerse sign-in round trip

## 20. Troubleshooting

### Alembic error

If you see:

```text
No module named alembic.__main__
```

use the virtualenv interpreter explicitly:

```bash
cd backend
venv/bin/python -m alembic upgrade head
```

### Emails not appearing

Check:

- MailHog is running
- `SMTP_HOST=localhost`
- `SMTP_PORT=1025`
- backend was restarted after changing `.env`

### Developer docs logo not loading

The docs page expects the admin frontend to be available at `ADMIN_CONSOLE_URL`, because the logo is served from that frontend.

For local development, that should be:

```dotenv
ADMIN_CONSOLE_URL=http://localhost:3000
```

and the frontend dev server must be running.

### SigVerse login fails immediately

Check:

- SigAuth backend is running on `8000`
- SigVerse backend `IDP_CLIENT_ID` matches the exact SigAuth app client ID
- SigVerse frontend `VITE_IDP_CLIENT_ID` matches the same value
- redirect URI in SigAuth includes `http://localhost:5173/auth/callback`
- the user belongs to a group assigned to the SigVerse app, or is the org admin

### User can log into SigAuth but not see SigVerse

That usually means one of these is missing:

- the SigVerse app is not active
- the user is not in an assigned group
- the application is not assigned to the user’s group

## 21. Recommended Terminal Layout for a Full Demo

For the full multi-client demo, use 10 terminals:

1. `backend` running `uvicorn`
2. `frontend` running the SigAuth admin console
3. `clients/hr-portal/backend`
4. `clients/hr-portal`
5. `clients/project-tracker/backend`
6. `clients/project-tracker`
7. `clients/logistica-delivery/backend`
8. `clients/logistica-delivery/frontend`
9. `clients/SigVerse/backend`
10. `clients/SigVerse/frontend`

If you are only demonstrating the main IdP plus SigVerse, the lighter 5-terminal setup is still enough:

1. `backend`
2. `frontend`
3. `clients/SigVerse/backend`
4. `clients/SigVerse/frontend`
5. MailHog or any one-off script terminal
