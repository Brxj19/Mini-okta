import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import { GroupsIcon, PlusIcon } from '../components/Icons';
import { hasPermission as userHasPermission } from '../utils/permissions';

export default function Groups() {
  const { orgId, claims } = useAuth();
  const [groups, setGroups] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const canCreateGroups = userHasPermission(claims, 'group:create');

  const fetchGroups = async (loadMore = false) => {
    if (!orgId) return;
    if (loadMore) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', '24');
      if (loadMore && cursor) params.set('cursor', cursor);
      const res = await api.get(`/api/v1/organizations/${orgId}/groups?${params}`);
      const data = res.data.data || [];
      const pag = res.data.pagination || {};
      if (loadMore) setGroups(prev => [...prev, ...data]);
      else setGroups(data);
      setCursor(pag.next_cursor);
      setHasMore(pag.has_more || false);
    } catch {}
    if (loadMore) setLoadingMore(false);
    else setLoading(false);
  };

  useEffect(() => { fetchGroups(); }, [orgId]);

  if (loading) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  return (
    <div>
      <PageHeader
        eyebrow="Directory Groups"
        title="Groups"
        description="Manage membership-based access controls and review how identities are organized across the current tenant."
        actions={
          canCreateGroups ? (
            <Link to="/groups/new" className="btn-primary">
              <PlusIcon className="h-4 w-4" />
              Create group
            </Link>
          ) : (
            <button type="button" className="btn-primary cursor-not-allowed opacity-55" disabled>
              <PlusIcon className="h-4 w-4" />
              Create group
            </button>
          )
        }
      />

      <div className="mb-6 card">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
            <GroupsIcon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900">{groups.length} loaded groups</p>
            <p className="text-sm text-slate-500">Use application assignments and memberships together to keep access targeted.</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {groups.map(g => (
          <Link key={g.id} to={`/groups/${g.id}`} className="card group transition-all duration-300 hover:-translate-y-0.5 hover:border-blue-200">
            <div className="flex items-center gap-3 mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 font-bold text-white">
                {g.name[0]?.toUpperCase()}
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 transition-colors group-hover:text-blue-700">{g.name}</h3>
                <p className="text-xs text-slate-500">{g.member_count || 0} members</p>
              </div>
            </div>
            {g.description && <p className="line-clamp-2 text-sm text-slate-600">{g.description}</p>}
          </Link>
        ))}
        {groups.length === 0 && (
          <div className="col-span-full py-12 text-center text-slate-500">
            No groups yet.
            {canCreateGroups ? <Link to="/groups/new" className="ml-1 text-blue-700 hover:text-blue-800">Create one →</Link> : null}
          </div>
        )}
      </div>

      {hasMore && (
        <div className="mt-6 text-center">
          <button onClick={() => fetchGroups(true)} className="btn-secondary" disabled={loadingMore}>
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}
