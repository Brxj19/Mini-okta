import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import CopyButton from '../components/CopyButton';
import { ApplicationsIcon, PlusIcon } from '../components/Icons';
import { hasPermission as userHasPermission } from '../utils/permissions';

const APP_TYPE_TONE = {
  web: 'badge-blue',
  spa: 'badge-purple',
  native: 'badge-teal',
  m2m: 'badge-orange',
};

function getLaunchUrl(app) {
  const firstRedirect = app?.redirect_uris?.[0];
  if (!firstRedirect) return null;
  try {
    const parsed = new URL(firstRedirect);
    return `${parsed.origin}/`;
  } catch {
    return null;
  }
}

export default function Applications() {
  const { orgId, claims, isSuperAdmin } = useAuth();
  const [apps, setApps] = useState([]);
  const [totalApps, setTotalApps] = useState(0);
  const [planStatus, setPlanStatus] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [permissionMessage, setPermissionMessage] = useState('');
  const canCreateApplications = isSuperAdmin || userHasPermission(claims, 'app:create');
  const canLaunchApplications = isSuperAdmin || userHasPermission(claims, 'app:update');
  const maxApps = Number(planStatus?.limits?.max_apps || 0);
  const appLimitReached = !!maxApps && totalApps >= maxApps;

  const launchApplication = (launchUrl, appName) => {
    if (!canLaunchApplications) {
      setPermissionMessage('You do not have permission to launch applications from the organization directory.');
      return;
    }
    if (!launchUrl) {
      setPermissionMessage(`No launch URL is configured for ${appName}.`);
      return;
    }
    setPermissionMessage('');
    window.open(launchUrl, '_blank', 'noopener,noreferrer');
  };

  const fetchApps = async (loadMore = false) => {
    if (!orgId) return;
    if (loadMore) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', '24');
      if (loadMore && cursor) params.set('cursor', cursor);
      const res = await api.get(`/api/v1/organizations/${orgId}/applications?${params}`);
      const data = res.data?.data || [];
      const pagination = res.data?.pagination || {};
      setApps((prev) => loadMore ? [...prev, ...data] : data);
      setTotalApps(Number(pagination.total || 0));
      setCursor(pagination.next_cursor || null);
      setHasMore(!!pagination.has_more);
    } finally {
      if (loadMore) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => { fetchApps(false); }, [orgId]);
  useEffect(() => {
    if (!orgId) return;
    api.get(`/api/v1/organizations/${orgId}/plan-status`)
      .then((res) => setPlanStatus(res.data || null))
      .catch(() => setPlanStatus(null));
  }, [orgId]);

  if (loading) return <div className="py-20 text-center text-sm text-gray-500">Loading applications...</div>;

  return (
    <div>
      <PageHeader
        eyebrow="Applications"
        title="Application Directory"
        description="Register and manage SSO connections. Launch and inspect each application in one click."
        actions={
          canCreateApplications && !appLimitReached ? (
            <Link className="btn-primary" to="/applications/new">
              <PlusIcon className="h-4 w-4" />
              Add application
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => setPermissionMessage(
                appLimitReached
                  ? `This organization has reached its application limit of ${maxApps} for the current plan.`
                  : 'You do not have permission to create applications.'
              )}
              className="btn-primary cursor-not-allowed justify-center opacity-55"
              aria-disabled="true"
            >
              <PlusIcon className="h-4 w-4" />
              Add application
            </button>
          )
        }
      />

      {permissionMessage ? (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {permissionMessage}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {apps.map((app) => {
          const launchUrl = getLaunchUrl(app);
          return (
          <article key={app.id} className="surface p-5 transition-all hover:-translate-y-px hover:border-indigo-200 hover:shadow-md">
            <div className="mb-4 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                  <ApplicationsIcon className="h-5 w-5" />
                </span>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">{app.name}</h3>
                  <p className="text-xs text-gray-500">Client app</p>
                </div>
              </div>
              <span className={app.status === 'active' ? 'badge-green' : 'badge-red'}>{app.status}</span>
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                <span className="text-gray-500">Type</span>
                <span className={APP_TYPE_TONE[app.app_type] || 'badge-gray'}>{app.app_type}</span>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                <p className="text-gray-500">Client ID</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="truncate font-mono text-xs text-gray-700">{app.client_id}</p>
                  <CopyButton value={app.client_id} label="Copy client id" />
                </div>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <Link className="btn-secondary flex-1 justify-center" to={`/applications/${app.id}`}>
                Open
              </Link>
              <button
                className={`btn-primary flex-1 justify-center ${canLaunchApplications ? '' : 'cursor-not-allowed opacity-55'}`}
                type="button"
                onClick={() => launchApplication(launchUrl, app.name)}
                aria-disabled={!canLaunchApplications || !launchUrl}
                title={
                  !canLaunchApplications
                    ? 'You do not have permission to launch this application'
                    : launchUrl
                      ? `Launch ${app.name}`
                      : 'No redirect URI configured'
                }
              >
                Launch
              </button>
            </div>
          </article>
          );
        })}
      </div>

      {apps.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
          No applications found for this organization.
        </div>
      ) : null}

      {hasMore ? (
        <div className="mt-6 text-center">
          <button onClick={() => fetchApps(true)} className="btn-secondary" disabled={loadingMore}>
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        </div>
      ) : null}
    </div>
  );
}
