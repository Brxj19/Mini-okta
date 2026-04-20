import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import RoleBadge from '../components/RoleBadge';
import PermissionCheckbox from '../components/PermissionCheckbox';
import PageHeader from '../components/PageHeader';
import { PlusIcon } from '../components/Icons';
import { hasPermission as userHasPermission } from '../utils/permissions';
import { pushToast } from '../utils/toastBus';

export default function Roles() {
  const { orgId, claims } = useAuth();
  const [roles, setRoles] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', permissions: [] });
  const canCreateRoles = userHasPermission(claims, 'role:create');
  const canUpdateRoles = userHasPermission(claims, 'role:update');

  const fetchRoles = async (loadMore = false) => {
    if (!orgId) return;
    if (loadMore) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', '20');
      if (loadMore && cursor) params.set('cursor', cursor);
      const res = await api.get(`/api/v1/organizations/${orgId}/roles?${params}`);
      const data = res.data.data || [];
      const pag = res.data.pagination || {};
      if (loadMore) setRoles(prev => [...prev, ...data]);
      else setRoles(data);
      setCursor(pag.next_cursor);
      setHasMore(pag.has_more || false);
    } catch {}
    if (loadMore) setLoadingMore(false);
    else setLoading(false);
  };

  useEffect(() => { fetchRoles(); }, [orgId]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await api.post(`/api/v1/organizations/${orgId}/roles`, form);
      setForm({ name: '', description: '', permissions: [] });
      setShowCreate(false);
      fetchRoles();
    } catch {}
    setCreating(false);
  };

  const handleUpdate = async () => {
    setCreating(true);
    try {
      await api.patch(`/api/v1/organizations/${orgId}/roles/${editingId}`, form);
      setEditingId(null);
      setForm({ name: '', description: '', permissions: [] });
      fetchRoles();
    } catch {}
    setCreating(false);
  };

  const startEdit = (role) => {
    if (!canUpdateRoles) return;
    if (role.is_system) {
      pushToast({ type: 'info', title: 'Role locked', message: 'System roles cannot be edited.' });
      return;
    }
    setEditingId(role.id);
    setForm({ name: role.name, description: role.description || '', permissions: role.permissions || [] });
    setShowCreate(false);
  };

  if (loading) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  return (
    <div>
      <PageHeader
        eyebrow="Authorization Model"
        title="Roles"
        description="Manage system and custom roles, then assign them through groups to keep permissions consistent."
        actions={
          canCreateRoles ? (
            <button onClick={() => { setShowCreate(true); setEditingId(null); setForm({ name: '', description: '', permissions: [] }); }} className="btn-primary">
              <PlusIcon className="h-4 w-4" />
              Create role
            </button>
          ) : (
            <button type="button" className="btn-primary cursor-not-allowed opacity-55" disabled>
              <PlusIcon className="h-4 w-4" />
              Create role
            </button>
          )
        }
      />

      {(canCreateRoles || canUpdateRoles) && (showCreate || editingId) && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold mb-4">{editingId ? 'Edit Role' : 'Create Custom Role'}</h2>
          <div className="space-y-4 mb-6">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-1">Name *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="input-field" placeholder="e.g. billing:admin" />
              </div>
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-1">Description</label>
                <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="input-field" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-2">Permissions</label>
              <PermissionCheckbox selected={form.permissions} onChange={p => setForm(f => ({ ...f, permissions: p }))} />
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={editingId ? handleUpdate : handleCreate} disabled={creating || !form.name} className="btn-primary">
              {creating ? 'Saving...' : editingId ? 'Update Role' : 'Create Role'}
            </button>
            <button onClick={() => { setShowCreate(false); setEditingId(null); }} className="btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {roles.map(role => (
          <div key={role.id} className={`card flex items-start justify-between group ${canUpdateRoles && !role.is_system ? 'cursor-pointer' : ''}`} onClick={() => startEdit(role)}>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <RoleBadge role={role.name} />
                {role.is_system && <span className="badge-gray text-xs">System</span>}
              </div>
              <p className="text-sm text-dark-400">{role.description}</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {(role.permissions || []).map(p => <span key={p} className="text-xs text-dark-500 bg-dark-800 px-2 py-0.5 rounded">{p}</span>)}
              </div>
            </div>
            {!role.is_system && canUpdateRoles ? (
              <span className="text-dark-500 group-hover:text-primary-400 text-sm transition-colors">Edit →</span>
            ) : null}
          </div>
        ))}
      </div>

      {hasMore && (
        <div className="mt-6 text-center">
          <button onClick={() => fetchRoles(true)} disabled={loadingMore} className="btn-secondary">
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}
