import React, { useEffect, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { ApplicationsIcon } from '../components/Icons';
import api from '../api/client';
import { getApplicationLaunchUrl } from '../utils/applicationLaunch';

export default function MyApps() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    api.get('/api/v1/me/applications')
      .then((res) => {
        if (!active) return;
        setApps(res.data?.data || []);
      })
      .catch(() => {
        if (!active) return;
        setApps([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div className="py-20 text-center text-sm text-gray-500">Loading your apps...</div>;
  }

  return (
    <div>
      <PageHeader
        eyebrow="My Apps"
        title="App Directory"
        description="Applications available to you through your organization group assignments."
      />

      {apps.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
          No apps are assigned to you yet. Ask your administrator to add you to a group linked with an application.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {apps.map((app) => {
            const launchUrl = getApplicationLaunchUrl(app);
            return (
              <article key={app.id} className="surface p-5 transition-all hover:-translate-y-px hover:border-gray-300 hover:shadow-md">
                <div className="mb-4 flex items-start gap-3">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-gray-200 bg-gray-50 text-gray-900">
                    <ApplicationsIcon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-gray-900">{app.name}</h3>
                    <p className="mt-1 text-xs text-gray-500">{app.app_type} application</p>
                  </div>
                </div>

                <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                  <p className="text-xs uppercase tracking-[0.14em] text-gray-500">Status</p>
                  <p className="mt-1 text-sm font-medium text-gray-800">{app.status}</p>
                </div>

                <div className="mt-4">
                  <button
                    className="btn-primary w-full justify-center"
                    type="button"
                    onClick={() => window.open(launchUrl, '_blank', 'noopener,noreferrer')}
                    disabled={!launchUrl}
                    title={launchUrl ? `Launch ${app.name}` : 'No launch URL configured'}
                  >
                    Launch app
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
