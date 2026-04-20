import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import CopyButton from '../components/CopyButton';
import Table from '../components/Table';
import UserAvatar from '../components/UserAvatar';
import { CheckIcon, PlusIcon, SearchIcon, XIcon } from '../components/Icons';
import useDebouncedValue from '../hooks/useDebouncedValue';
import { getDisplayName } from '../utils/profile';
import { hasPermission as userHasPermission } from '../utils/permissions';

export default function Users() {
  const { orgId, claims } = useAuth();
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const debouncedSearch = useDebouncedValue(search, 300);
  const canCreateUsers = userHasPermission(claims, 'user:create');
  const canUpdateUsers = userHasPermission(claims, 'user:update');

  const fetchUsers = async (loadMore = false) => {
    if (!orgId) return;
    if (loadMore) setLoadingMore(true);
    else setLoading(true);

    try {
      const params = new URLSearchParams();
      params.set('limit', '25');
      if (debouncedSearch) params.set('filter[email_contains]', debouncedSearch);
      if (status) params.set('filter[status]', status);
      if (loadMore && cursor) params.set('cursor', cursor);

      const res = await api.get(`/api/v1/organizations/${orgId}/users?${params}`);
      const data = res.data?.data || [];
      const pagination = res.data?.pagination || {};
      setUsers((prev) => loadMore ? [...prev, ...data] : data);
      setCursor(pagination.next_cursor || null);
      setHasMore(!!pagination.has_more);
    } finally {
      if (loadMore) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(false);
  }, [orgId, debouncedSearch, status]);

  const rows = users.map((user) => (
    <tr key={user.id} className="table-row">
      <td className="px-6 py-3">
        <div className="flex items-center gap-2">
          <UserAvatar user={user} className="h-9 w-9" textClassName="text-xs" />
          <div className="min-w-0">
            <Link to={`/users/${user.id}`} className="block truncate font-medium text-indigo-600 hover:text-indigo-700">{user.email}</Link>
            <p className="truncate text-xs text-gray-500">{getDisplayName(user, 'No name set')}</p>
          </div>
          <CopyButton value={user.email} label="Copy email" />
        </div>
      </td>
      <td className="px-6 py-3 text-sm text-gray-700">{`${user.first_name || ''} ${user.last_name || ''}`.trim() || '—'}</td>
      <td className="px-6 py-3">
        <span className={user.status === 'active' ? 'badge-green' : user.status === 'suspended' ? 'badge-yellow' : 'badge-red'}>{user.status}</span>
      </td>
      <td className="px-6 py-3">
        {user.email_verified
          ? <span className="badge-green"><CheckIcon className="h-3.5 w-3.5" />Verified</span>
          : <span className="badge-gray"><XIcon className="h-3.5 w-3.5" />Pending</span>}
      </td>
      <td className="px-6 py-3 text-sm text-gray-500">{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '—'}</td>
      <td className="px-6 py-3">
        <Link to={`/users/${user.id}`} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
          {canUpdateUsers ? 'Edit' : 'View'}
        </Link>
      </td>
    </tr>
  ));

  return (
    <div>
      <PageHeader
        eyebrow="Users"
        title="User Directory"
        description="Create, update, and monitor identities. Most actions are reachable within one click from this table."
        actions={
          canCreateUsers ? (
            <Link to="/users/new" className="btn-primary">
              <PlusIcon className="h-4 w-4" />
              Add user
            </Link>
          ) : (
            <button type="button" className="btn-primary cursor-not-allowed opacity-55" disabled>
              <PlusIcon className="h-4 w-4" />
              Add user
            </button>
          )
        }
      />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row">
        <div className="relative max-w-md flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            className="input-field pl-10"
            value={search}
            placeholder="Search by email"
            onChange={(e) => {
              setCursor(null);
              setSearch(e.target.value);
            }}
          />
        </div>
        <select
          className="input-field w-full sm:w-40"
          value={status}
          onChange={(e) => {
            setCursor(null);
            setStatus(e.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="locked">Locked</option>
        </select>
      </div>

      {loading ? (
        <div className="py-20 text-center text-sm text-gray-500">Loading users...</div>
      ) : (
        <Table
          columns={[
            { key: 'email', label: 'Email' },
            { key: 'name', label: 'Name' },
            { key: 'status', label: 'Status' },
            { key: 'verified', label: 'Verified' },
            { key: 'last_login', label: 'Last login' },
            { key: 'actions', label: 'Actions' },
          ]}
          rows={rows}
          emptyMessage="No users found"
        />
      )}

      {hasMore ? (
        <div className="mt-5 text-center">
          <button onClick={() => fetchUsers(true)} className="btn-secondary" disabled={loadingMore}>
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        </div>
      ) : null}
    </div>
  );
}
