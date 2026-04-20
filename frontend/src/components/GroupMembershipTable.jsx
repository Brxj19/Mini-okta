import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import UserAvatar from './UserAvatar';
import { PlusIcon, SearchIcon, XIcon } from './Icons';
import ConfirmDialog from './ConfirmDialog';
import { getDisplayName } from '../utils/profile';

export default function GroupMembershipTable({ groupId, allowManageMembers = true, blockedMessage = '' }) {
  const { orgId } = useAuth();
  const [members, setMembers] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [error, setError] = useState('');
  const [pendingRemoval, setPendingRemoval] = useState(null);

  const fetchMembers = async (loadMore = false) => {
    if (!orgId || !groupId) return;
    try {
      const params = new URLSearchParams();
      params.set('limit', '25');
      if (loadMore && cursor) params.set('cursor', cursor);
      const res = await api.get(`/api/v1/organizations/${orgId}/groups/${groupId}/members?${params}`);
      const data = res.data.data || [];
      const pag = res.data.pagination || {};
      if (loadMore) setMembers(prev => [...prev, ...data]);
      else setMembers(data);
      setCursor(pag.next_cursor);
      setHasMore(pag.has_more || false);
    } catch {}
  };

  useEffect(() => { fetchMembers(); }, [orgId, groupId]);

  const handleSearch = async (q) => {
    if (!allowManageMembers) return;
    setSearch(q);
    setError('');
    if (q.length < 2) { setSearchResults([]); return; }
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/users?filter[email_contains]=${q}&limit=10`);
      const existing = new Set(members.map(m => m.id));
      setSearchResults((res.data.data || []).filter(u => !existing.has(u.id)));
    } catch { setSearchResults([]); }
  };

  const addMember = async (userId) => {
    setLoading(true);
    setError('');
    try {
      await api.post(`/api/v1/organizations/${orgId}/groups/${groupId}/members`, { user_ids: [userId] });
      setSearch('');
      setSearchResults([]);
      setShowAddPanel(false);
      fetchMembers();
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to add that user to this group.');
    }
    setLoading(false);
  };

  const removeMember = async (userId) => {
    try {
      await api.delete(`/api/v1/organizations/${orgId}/groups/${groupId}/members/${userId}`);
      fetchMembers();
    } catch {}
  };

  return (
    <div>
      <div className="mb-5 rounded-xl border border-dark-700 bg-dark-800 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-dark-100">Manage members</h3>
            <p className="mt-1 text-sm text-dark-400">Search the current organization directory and add users to this group.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!allowManageMembers) return;
              setShowAddPanel(current => !current);
              if (showAddPanel) {
                setSearch('');
                setSearchResults([]);
              }
            }}
            className="btn-primary"
            disabled={!allowManageMembers}
          >
            {showAddPanel ? <XIcon className="h-4 w-4" /> : <PlusIcon className="h-4 w-4" />}
            {allowManageMembers ? (showAddPanel ? 'Close' : 'Add member') : 'Managed by admin'}
          </button>
        </div>

        {!allowManageMembers && blockedMessage ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {blockedMessage}
          </div>
        ) : null}

        {showAddPanel && (
          <div className="mt-4">
            {error && (
              <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-dark-500" />
              <input
                type="text"
                value={search}
                onChange={e => handleSearch(e.target.value)}
                placeholder="Search users by email"
                className="input-field pl-10"
              />
            </div>

            {search.length > 0 && search.length < 2 && (
              <p className="mt-2 text-xs text-dark-500">Type at least 2 characters to search.</p>
            )}

            {searchResults.length > 0 && (
              <div className="mt-3 overflow-hidden rounded-lg border border-dark-700 bg-dark-900">
                {searchResults.map(u => (
                  <div key={u.id} className="flex items-center justify-between border-b border-dark-700 px-4 py-3 last:border-b-0">
                    <div className="flex items-center gap-3">
                      <UserAvatar user={u} className="h-10 w-10" textClassName="text-xs" />
                      <div>
                      <p className="text-sm font-medium text-dark-100">{u.email}</p>
                      <p className="text-xs text-dark-400">{getDisplayName(u, 'No name set')}</p>
                      </div>
                    </div>
                    <button onClick={() => addMember(u.id)} disabled={loading} className="btn-secondary">
                      <PlusIcon className="h-4 w-4" />
                      Add
                    </button>
                  </div>
                ))}
              </div>
            )}

            {search.length >= 2 && searchResults.length === 0 && (
              <div className="mt-3 rounded-lg border border-dark-700 bg-dark-900 px-4 py-3 text-sm text-dark-500">
                No eligible users found for that search.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="table-header">
              <th className="text-left py-3 px-4 text-xs font-semibold text-dark-400 uppercase">Email</th>
              <th className="text-left py-3 px-4 text-xs font-semibold text-dark-400 uppercase">Name</th>
              <th className="text-left py-3 px-4 text-xs font-semibold text-dark-400 uppercase">Status</th>
              <th className="py-3 px-4"></th>
            </tr>
          </thead>
          <tbody>
            {members.map(m => (
              <tr key={m.id} className="table-row">
                <td className="py-3 px-4 text-sm">
                  <div className="flex items-center gap-3">
                    <UserAvatar user={m} className="h-9 w-9" textClassName="text-xs" />
                    <span>{m.email}</span>
                  </div>
                </td>
                <td className="py-3 px-4 text-sm text-dark-300">{getDisplayName(m, '—')}</td>
                <td className="py-3 px-4">
                  <span className={m.status === 'active' ? 'badge-green' : 'badge-red'}>{m.status}</span>
                </td>
                <td className="py-3 px-4 text-right">
                  {allowManageMembers ? (
                    <button onClick={() => setPendingRemoval(m)} className="text-sm font-medium text-red-700 hover:text-red-800">Remove</button>
                  ) : null}
                </td>
              </tr>
            ))}
            {members.length === 0 && (
              <tr><td colSpan={4} className="py-8 text-center text-dark-500">No members</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="mt-4 text-center">
          <button onClick={() => fetchMembers(true)} className="btn-secondary">
            Load more members
          </button>
        </div>
      )}

      <ConfirmDialog
        open={!!pendingRemoval}
        title="Remove member from group?"
        description={pendingRemoval ? `${pendingRemoval.email} will be removed from this group.` : ''}
        confirmLabel="Remove member"
        onClose={() => setPendingRemoval(null)}
        onConfirm={async () => {
          const user = pendingRemoval;
          setPendingRemoval(null);
          if (user) await removeMember(user.id);
        }}
      />
    </div>
  );
}
