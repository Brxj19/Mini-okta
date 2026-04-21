import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import UserAvatar from '../components/UserAvatar';
import { ApplicationsIcon, BellIcon, SecurityIcon, UsersIcon } from '../components/Icons';
import { getDisplayName, getShortDisplayName } from '../utils/profile';
import { hasPermission as userHasPermission, hasRole } from '../utils/permissions';

export default function Dashboard() {
  const { orgId, claims, profile, isSuperAdmin } = useAuth();
  const [stats, setStats] = useState({
    users: 0,
    sessions: 0,
    applications: 0,
    alerts: 0,
  });
  const [recentEvents, setRecentEvents] = useState([]);
  const [launcherApps, setLauncherApps] = useState([]);
  const [organization, setOrganization] = useState(null);

  useEffect(() => {
    if (!orgId) return;
    const hasPermission = (permission) => userHasPermission(claims, permission);
    const showMyApps = !isSuperAdmin && !hasRole(claims, 'org:admin');

    Promise.allSettled([
      isSuperAdmin
        ? api.get(`/api/v1/admin/organizations/${orgId}`)
        : api.get('/api/v1/me/organization'),
      hasPermission('user:read')
        ? api.get(`/api/v1/organizations/${orgId}/users?limit=1`)
        : Promise.resolve({ data: { pagination: { total: 0 } } }),
      showMyApps
        ? api.get('/api/v1/me/applications')
        : hasPermission('app:read')
          ? api.get(`/api/v1/organizations/${orgId}/applications?limit=1`)
          : Promise.resolve({ data: { data: [], pagination: { total: 0 } } }),
      hasPermission('audit:read')
        ? api.get(`/api/v1/organizations/${orgId}/audit-log?limit=8`)
        : Promise.resolve({ data: { data: [] } }),
      api.get('/api/v1/me/sessions').catch(() => ({ data: { data: [] } })),
    ]).then(([orgRes, usersRes, appsRes, auditRes, sessionsRes]) => {
      const orgData = orgRes.value?.data || null;
      const usersTotal = usersRes.value?.data?.pagination?.total || 0;
      const apps = appsRes.value?.data?.data || [];
      const applicationTotal = showMyApps
        ? apps.length
        : appsRes.value?.data?.pagination?.total || 0;
      const audit = auditRes.value?.data?.data || [];
      const sessions = sessionsRes.value?.data?.data || [];
      const alertCount = audit.filter((event) => String(event.event_type || '').includes('failure')).length;

      setOrganization(orgData);
      setStats({
        users: usersTotal,
        sessions: sessions.length,
        applications: applicationTotal,
        alerts: alertCount,
      });
      setLauncherApps(showMyApps ? apps.slice(0, 6) : []);
      setRecentEvents(audit);
    });
  }, [orgId, claims, isSuperAdmin]);

  const hasPermission = (permission) => userHasPermission(claims, permission);
  const showMyApps = !isSuperAdmin && !hasRole(claims, 'org:admin');
  const organizationName = organization?.display_name || organization?.name || 'Your organization';
  const account = profile || { email: claims?.email, first_name: claims?.given_name, last_name: claims?.family_name };
  const accountName = getDisplayName(account, claims?.email || 'Account');
  const greetingName = getShortDisplayName(account, '');

  const cards = [
    {
      label: 'Total Users',
      value: stats.users,
      tone: 'bg-indigo-50 text-indigo-700',
      iconTone: 'bg-indigo-100 text-indigo-700',
      icon: UsersIcon,
    },
    {
      label: 'Active Sessions',
      value: stats.sessions,
      tone: 'bg-emerald-50 text-emerald-700',
      iconTone: 'bg-emerald-100 text-emerald-700',
      icon: BellIcon,
    },
    {
      label: 'Applications Connected',
      value: stats.applications,
      tone: 'bg-sky-50 text-sky-700',
      iconTone: 'bg-sky-100 text-sky-700',
      icon: ApplicationsIcon,
    },
    {
      label: 'Security Alerts',
      value: stats.alerts,
      tone: 'bg-amber-50 text-amber-700',
      iconTone: 'bg-amber-100 text-amber-700',
      icon: SecurityIcon,
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Dashboard"
        title={`Welcome back${greetingName ? `, ${greetingName}` : ''}`}
        description="Identity operations at a glance. Access core management flows in one click."
      />

      {organization ? (
        <section className="mb-7 rounded-2xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Organization</p>
              <h2 className="mt-1 text-xl font-semibold text-gray-900">{organizationName}</h2>
              <p className="mt-1 text-sm text-gray-600">
                {organization.slug ? `/${organization.slug}` : 'Organization profile'}{organization?.access_tier ? ` • ${organization.access_tier.replace('_', ' ')}` : ''}
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
              <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5">
                <UserAvatar user={account} imageUrl={profile?.profile_image_url} className="h-11 w-11" textClassName="text-base" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-gray-900">{accountName}</p>
                  <p className="truncate text-xs text-gray-500">{profile?.email || claims?.email || 'Signed-in user'}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                  Status: {organization.status}
                </span>
                {organization.verification_status ? (
                  <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                    Verification: {organization.verification_status}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <div className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <article key={card.label} className="surface p-5 transition-all hover:-translate-y-px hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-gray-600">{card.label}</p>
              <span className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl ${card.iconTone}`}>
                <card.icon className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <p className="text-3xl font-semibold text-gray-900">{card.value}</p>
              <span className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${card.tone}`}>Live</span>
            </div>
          </article>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="surface xl:col-span-2">
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Recent Activity</h2>
              <p className="text-sm text-gray-600">Latest authentication and admin events.</p>
            </div>
            {hasPermission('audit:read') ? (
              <Link to="/audit-log" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">View all</Link>
            ) : null}
          </div>
          <div className="divide-y divide-gray-200">
            {recentEvents.length === 0 ? (
              <p className="px-5 py-8 text-sm text-gray-500">No events yet for this organization.</p>
            ) : recentEvents.map((event) => (
              <div key={event.id} className="flex items-center gap-3 px-5 py-3.5">
                <span className="h-2 w-2 rounded-full bg-indigo-500" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-gray-900">{event.event_type}</p>
                  <p className="text-xs text-gray-500">{new Date(event.created_at).toLocaleString()}</p>
                </div>
                <Link to={`/audit-log/${event.id}`} className="text-xs font-medium text-indigo-600 hover:text-indigo-700">Details</Link>
              </div>
            ))}
          </div>
        </section>

        <section className="surface">
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900">{showMyApps ? 'App Launcher' : 'Organization Snapshot'}</h2>
              <p className="text-sm text-gray-600">
                {showMyApps ? 'Open the applications assigned to your account.' : 'Your current organization, access tier, and account privileges.'}
              </p>
            </div>
            {showMyApps ? (
              <Link to="/my-apps" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">View all</Link>
            ) : (
              <Link to="/settings" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">Open settings</Link>
            )}
          </div>
          {showMyApps ? (
            <div className="grid grid-cols-2 gap-3 p-5">
              {launcherApps.length === 0 ? (
                <div className="col-span-2 rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                  No applications found
                </div>
              ) : launcherApps.map((app) => (
                <Link
                  key={app.id}
                  to={`/applications/${app.id}`}
                  className="rounded-lg border border-gray-200 bg-white p-4 text-left transition-all hover:-translate-y-px hover:border-indigo-200 hover:shadow-sm"
                >
                  <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                    <ApplicationsIcon className="h-4 w-4" />
                  </div>
                  <p className="truncate text-sm font-medium text-gray-900">{app.name}</p>
                  <p className="mt-1 text-xs text-gray-500">{app.app_type}</p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="space-y-3 p-5">
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.14em] text-gray-500">Organization</p>
                <p className="mt-1 text-sm font-medium text-gray-900">{organizationName}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.14em] text-gray-500">Roles</p>
                <p className="mt-1 text-sm font-medium text-gray-900">{(claims?.roles || []).join(', ') || 'No roles assigned'}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.14em] text-gray-500">Permissions</p>
                <p className="mt-1 text-sm font-medium text-gray-900">
                  {claims?.permissions?.length ? `${claims.permissions.length} granted permission(s)` : 'No permissions assigned'}
                </p>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 border-t border-gray-200 p-5">
            {hasPermission('user:read') ? (
              <Link to="/users" className="rounded-lg border border-gray-200 p-3 text-sm text-gray-700 transition-colors hover:bg-gray-50">
                <span className="mb-1 flex items-center gap-2 font-medium"><UsersIcon className="h-4 w-4 text-indigo-600" />Users</span>
                Manage identities
              </Link>
            ) : null}
            {hasPermission('audit:read') ? (
              <Link to="/security" className="rounded-lg border border-gray-200 p-3 text-sm text-gray-700 transition-colors hover:bg-gray-50">
                <span className="mb-1 flex items-center gap-2 font-medium"><SecurityIcon className="h-4 w-4 text-indigo-600" />Security</span>
                Review controls
              </Link>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
