import React from 'react';
import { Link } from 'react-router-dom';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../branding';
import AuthParticleCanvas from '../components/AuthParticleCanvas';
import {
  ApplicationsIcon,
  AuditIcon,
  GroupsIcon,
  MailIcon,
  ProductMark,
  RolesIcon,
  SecurityIcon,
  SparkIcon,
  UsersIcon,
} from '../components/Icons';

const docsBase = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const developerDocsUrl = `${docsBase}/docs`;

const highlights = [
  {
    title: 'OIDC that feels production-ready',
    description: 'Authorization Code + PKCE, scoped apps, invitation onboarding, and password lifecycle controls in one focused platform.',
    icon: SecurityIcon,
  },
  {
    title: 'Admin tooling teams can actually use',
    description: 'Manage orgs, users, groups, applications, and roles from a clean console built for day-to-day IAM operations.',
    icon: UsersIcon,
  },
  {
    title: 'Traceable access decisions',
    description: 'Audit events, delivery visibility, and org-level controls make the platform easier to trust and easier to demo.',
    icon: AuditIcon,
  },
];

const capabilities = [
  { label: 'Multi-tenant organizations', icon: GroupsIcon },
  { label: 'App and group assignments', icon: ApplicationsIcon },
  { label: 'RBAC and permission mapping', icon: RolesIcon },
  { label: 'Security workflows and resets', icon: MailIcon },
];

const platformPillars = [
  {
    title: 'Identity Lifecycle',
    description: 'Invite users, activate accounts, manage profile updates, and control password setup/reset with auditable flows.',
  },
  {
    title: 'Access Governance',
    description: 'Map users to groups, groups to apps, and roles to permissions so access remains structured as your org grows.',
  },
  {
    title: 'Operational Visibility',
    description: 'Track sign-in behavior, admin actions, email deliveries, and system events from a central control plane.',
  },
];

const useCases = [
  'Internal tools with SSO-ready access control',
  'SaaS prototypes requiring tenant-aware IAM',
  'Learning projects for OIDC, PKCE, and RBAC',
  'Admin consoles that need auditability from day one',
];

export default function Home() {
  return (
    <div className="landing-shell">
      <AuthParticleCanvas />
      <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
        <Link to="/" className="flex items-center gap-3 text-slate-900">
          <ProductMark className="h-11 w-11" />
          <div>
            <div className="landing-eyebrow">{PRODUCT_NAME}</div>
            <div className="text-sm text-slate-600">{PRODUCT_TAGLINE}</div>
          </div>
        </Link>

        <div className="flex items-center gap-3">
          <a href={developerDocsUrl} target="_blank" rel="noreferrer" className="landing-nav-link">Docs</a>
          <Link to="/login" className="landing-nav-link">Sign in</Link>
          <Link to="/signup" className="landing-nav-cta">Start building</Link>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto grid max-w-7xl gap-12 px-6 pb-16 pt-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:px-10 lg:pb-24 lg:pt-12">
          <div className="max-w-3xl">
            <div className="landing-chip">
              <SparkIcon className="h-4 w-4" />
              Production-style IAM for demos, prototypes, and internal tools
            </div>

            <h1 className="mt-6 landing-hero-title">
              Identity, access, and admin controls with a sharper first impression.
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600 lg:text-xl">
              {PRODUCT_NAME} brings together OIDC, user lifecycle flows, group-aware access, and a practical admin console in one compact platform that still feels serious.
            </p>

            <div className="mt-8 flex flex-col gap-4 sm:flex-row">
              <Link to="/signup" className="landing-primary-cta">Launch the admin experience</Link>
              {/* <Link to="/login" className="landing-secondary-cta">Use seeded credentials</Link> */}
              <a href={developerDocsUrl} target="_blank" rel="noreferrer" className="landing-secondary-cta">Read developer docs</a>
            </div>

            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              <div className="landing-stat-panel">
                <div className="landing-stat-value">OIDC</div>
                <div className="landing-stat-label">Authorization Code + PKCE</div>
              </div>
              <div className="landing-stat-panel">
                <div className="landing-stat-value">RBAC</div>
                <div className="landing-stat-label">Roles, groups, app scoping</div>
              </div>
              <div className="landing-stat-panel">
                <div className="landing-stat-value">Audit</div>
                <div className="landing-stat-label">Logs and delivery visibility</div>
              </div>
            </div>
          </div>

          <div className="landing-showcase">
            <div className="landing-orb landing-orb-cyan" />
            <div className="landing-orb landing-orb-amber" />

            <div className="landing-console-card">
              <div className="flex items-center justify-between border-b border-indigo-100 px-6 py-4">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Admin Console</p>
                  <p className="text-xs text-slate-500">Control plane for access and identity</p>
                </div>
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
                  Live system
                </span>
              </div>

              <div className="grid gap-4 px-6 py-6">
                <div className="landing-mini-metric">
                  <span className="text-slate-600">Applications secured</span>
                  <strong className="text-2xl text-slate-900">03</strong>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="landing-subcard">
                    <div className="flex items-center gap-3">
                      <SecurityIcon className="h-5 w-5 text-slate-700" />
                      <div>
                        <p className="text-sm font-medium text-slate-900">Access policies</p>
                        <p className="text-xs text-slate-500">Password setup, reset, expiry</p>
                      </div>
                    </div>
                  </div>

                  <div className="landing-subcard">
                    <div className="flex items-center gap-3">
                      <AuditIcon className="h-5 w-5 text-amber-600" />
                      <div>
                        <p className="text-sm font-medium text-slate-900">Audit visibility</p>
                        <p className="text-xs text-slate-500">Track user and admin activity</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="landing-timeline">
                  <div className="landing-timeline-row">
                    <span className="landing-timeline-dot bg-emerald-500" />
                    New application authorized with PKCE
                  </div>
                  <div className="landing-timeline-row">
                    <span className="landing-timeline-dot bg-slate-600" />
                    Group assignment synced to application roles
                  </div>
                  <div className="landing-timeline-row">
                    <span className="landing-timeline-dot bg-sky-500" />
                    Invitation email queued for onboarding
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-6 pb-8 lg:px-10">
          <div className="landing-trust-strip">
            {capabilities.map(({ label, icon: Icon }) => (
              <div key={label} className="landing-trust-item">
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-6 py-10 lg:px-10 lg:py-16">
          <div className="grid gap-5 lg:grid-cols-3">
            {highlights.map(({ title, description, icon: Icon }) => (
              <article key={title} className="landing-feature-card">
                <div className="landing-feature-icon">
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="mt-5 text-xl font-semibold text-slate-900">{title}</h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">{description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-6 py-4 lg:px-10 lg:py-8">
          <div className="landing-architecture-panel">
            <div>
              <div className="landing-eyebrow">What {PRODUCT_NAME} Gives You</div>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 lg:text-4xl">
                A compact identity platform with real-world IAM building blocks.
              </h2>
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
                {PRODUCT_NAME} is designed for builders who need a practical identity layer without enterprise platform overhead.
                It combines authentication, authorization, and admin operations so client apps can integrate once and scale with confidence.
              </p>
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-3">
              {platformPillars.map((pillar) => (
                <article key={pillar.title} className="landing-feature-card">
                  <h3 className="text-lg font-semibold text-slate-900">{pillar.title}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-600">{pillar.description}</p>
                </article>
              ))}
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="landing-process-card">
                <h3 className="text-lg font-semibold text-slate-900">How The Flow Works</h3>
                <div className="mt-4 grid gap-3">
                  <div className="landing-flow-step"><span>01</span> Client app redirects to the {PRODUCT_NAME} authorize endpoint with PKCE.</div>
                  <div className="landing-flow-step"><span>02</span> User signs in, policies are evaluated, and consent/access checks run.</div>
                  <div className="landing-flow-step"><span>03</span> Tokens are returned to the client app for session establishment.</div>
                  <div className="landing-flow-step"><span>04</span> App enforces roles and permissions from user/group assignments.</div>
                </div>
              </div>
              <div className="landing-process-card">
                <h3 className="text-lg font-semibold text-slate-900">Popular Use Cases</h3>
                <ul className="mt-4 grid gap-3">
                  {useCases.map((item) => (
                    <li key={item} className="landing-usecase-item">{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-6 pb-20 pt-6 lg:px-10 lg:pb-28">
          <div className="landing-cta-panel">
            <div className="max-w-2xl">
              <div className="landing-eyebrow text-slate-700">Built for your {PRODUCT_NAME} rollout</div>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 lg:text-4xl">
                A homepage that explains the product before the login form has to.
              </h2>
              <p className="mt-4 text-base leading-7 text-slate-600">
                The new landing experience gives your project a stronger story: what it does, why it matters, and where to go next.
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <Link to="/signup" className="landing-primary-cta">Create an account</Link>
              <Link to="/login" className="landing-secondary-cta">Open console</Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
