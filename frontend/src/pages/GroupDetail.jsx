import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import GroupMembershipTable from '../components/GroupMembershipTable';
import RoleBadge from '../components/RoleBadge';
import PageHeader from '../components/PageHeader';
import { ArrowLeftIcon } from '../components/Icons';
import ConfirmDialog from '../components/ConfirmDialog';
import { hasPermission, hasRole } from '../utils/permissions';

export default function GroupDetail() {
  const { id } = useParams();
  const { orgId, claims, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [group, setGroup] = useState(null);
  const [roles, setRoles] = useState([]);
  const [allRoles, setAllRoles] = useState([]);
  const [selectedRole, setSelectedRole] = useState('');
  const [tab, setTab] = useState('members');
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmState, setConfirmState] = useState(null);

  const fetchGroup = async () => {
    try {
      // Groups endpoint returns group in list, get it specifically
      const res = await api.get(`/api/v1/organizations/${orgId}/groups?limit=100`);
      const found = (res.data.data || []).find(g => g.id === id);
      if (found) {
        setGroup(found);
        setEditName(found.name || '');
        setEditDescription(found.description || '');
      }
      else navigate('/groups');
    } catch { navigate('/groups'); }
  };

  const fetchGroupRoles = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/groups/${id}/roles`);
      setRoles(res.data.data || []);
    } catch {}
  };

  const fetchAllRoles = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/roles?limit=100`);
      setAllRoles(res.data.data || []);
    } catch {}
  };

  useEffect(() => {
    fetchGroup();
    fetchGroupRoles();
    fetchAllRoles();
  }, [id, orgId]);

  const assignRole = async () => {
    if (!selectedRole) return;
    try {
      await api.post(`/api/v1/organizations/${orgId}/groups/${id}/roles`, { role_ids: [selectedRole] });
      setSelectedRole('');
      fetchGroupRoles();
    } catch {}
  };

  const removeRole = async (roleId) => {
    try {
      await api.delete(`/api/v1/organizations/${orgId}/groups/${id}/roles/${roleId}`);
      fetchGroupRoles();
    } catch {}
  };

  const handleDelete = async () => {
    await api.delete(`/api/v1/organizations/${orgId}/groups/${id}`);
    navigate('/groups');
  };

  const saveGroupDetails = async () => {
    setSaveError('');
    setSaving(true);
    try {
      const res = await api.patch(`/api/v1/organizations/${orgId}/groups/${id}`, {
        name: editName,
        description: editDescription,
      });
      setGroup(res.data);
      setEditName(res.data.name || '');
      setEditDescription(res.data.description || '');
      setEditing(false);
    } catch (err) {
      setSaveError(err.response?.data?.detail?.error_description || 'Unable to update group.');
    } finally {
      setSaving(false);
    }
  };

  if (!group) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  const assignedRoleIds = new Set(roles.map(r => r.id));
  const availableRoles = allRoles.filter(r => !assignedRoleIds.has(r.id));
  const groupIsProtected = roles.some((role) => role.name === 'org:admin');
  const actorCanManageProtectedGroup = isSuperAdmin || hasRole(claims, 'org:admin');
  const canManageMembers = hasPermission(claims, 'group:member:add') && hasPermission(claims, 'group:member:remove');
  const canAssignRoles = hasPermission(claims, 'group:role:assign');
  const canRemoveRoles = hasPermission(claims, 'group:role:update');
  const canDeleteGroup = hasPermission(claims, 'group:delete');
  const canUpdateGroup = hasPermission(claims, 'group:update');
  const blockProtectedGroupActions = groupIsProtected && !actorCanManageProtectedGroup;
  const canEditGroup = canUpdateGroup && !blockProtectedGroupActions;
  const canManageGroupRoles = (canAssignRoles || canRemoveRoles) && !blockProtectedGroupActions;
  const canDeleteCurrentGroup = canDeleteGroup && !blockProtectedGroupActions;

  return (
    <div>
      <button onClick={() => navigate('/groups')} className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to groups
      </button>

      <PageHeader
        eyebrow="Group"
        title={group.name}
        description={group.description || 'Manage memberships and effective roles for this directory group.'}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => {
                if (!canEditGroup) return;
                setEditing((value) => !value);
                setSaveError('');
                setEditName(group.name || '');
                setEditDescription(group.description || '');
              }}
              className={`btn-secondary text-sm ${canEditGroup ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canEditGroup}
            >
              {editing ? 'Cancel Edit' : 'Edit Group'}
            </button>
            <button
              onClick={() => setConfirmState({ type: 'delete' })}
              className={`btn-danger text-sm ${canDeleteCurrentGroup ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canDeleteCurrentGroup}
            >
              Delete Group
            </button>
          </div>
        }
      />

      {blockProtectedGroupActions ? (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          This group grants administrator access. Only organization admins can change its memberships, roles, or delete it.
        </div>
      ) : null}

      {editing && canEditGroup ? (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Group name</label>
              <input
                className="input-field"
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                placeholder="engineering"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Description</label>
              <input
                className="input-field"
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
                placeholder="Describe this group"
              />
            </div>
          </div>
          {saveError ? (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {saveError}
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button onClick={saveGroupDetails} disabled={saving || !editName.trim()} className="btn-primary text-sm">
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setSaveError('');
                setEditName(group.name || '');
                setEditDescription(group.description || '');
              }}
              className="btn-secondary text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <div className="mb-6 flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm w-fit">
        {['members', 'roles'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              tab === t ? 'bg-blue-50 text-blue-700' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {t === 'members' ? 'Members' : 'Roles'}
          </button>
        ))}
      </div>

      {tab === 'members' && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Members</h2>
          <GroupMembershipTable
            groupId={id}
            allowManageMembers={canManageMembers && !blockProtectedGroupActions}
            blockedMessage={blockProtectedGroupActions ? 'Organization admin access groups can only be managed by organization admins.' : ''}
          />
        </div>
      )}

      {tab === 'roles' && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Assigned Roles</h2>
          {canAssignRoles ? (
            <div className="flex gap-3 mb-6">
              <select value={selectedRole} onChange={e => setSelectedRole(e.target.value)} className="input-field max-w-xs" disabled={!canManageGroupRoles}>
                <option value="">Select role to assign...</option>
                {availableRoles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <button onClick={assignRole} disabled={!selectedRole || !canManageGroupRoles} className={`btn-primary text-sm ${canManageGroupRoles ? '' : 'cursor-not-allowed opacity-55'}`}>Assign</button>
            </div>
          ) : null}
          <div className="space-y-3">
            {roles.map(r => (
              <div key={r.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div>
                  <RoleBadge role={r.name} />
                  <p className="mt-1 text-xs text-slate-500">{r.description}</p>
                </div>
                {canRemoveRoles ? (
                  <button onClick={() => setConfirmState({ type: 'removeRole', role: r })} disabled={!canManageGroupRoles} className="text-sm text-red-700 hover:text-red-800 disabled:cursor-not-allowed disabled:text-slate-400">Remove</button>
                ) : null}
              </div>
            ))}
            {roles.length === 0 && <p className="text-sm text-slate-500">No roles assigned</p>}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.type === 'delete' ? 'Delete group?' : 'Remove role from group?'}
        description={
          confirmState?.type === 'delete'
            ? 'All memberships and role assignments will be removed from this group.'
            : confirmState?.role
              ? `${confirmState.role.name} will no longer be assigned to this group.`
              : ''
        }
        confirmLabel={confirmState?.type === 'delete' ? 'Delete group' : 'Remove role'}
        onClose={() => setConfirmState(null)}
        onConfirm={async () => {
          const state = confirmState;
          setConfirmState(null);
          if (state?.type === 'delete') await handleDelete();
          if (state?.type === 'removeRole' && state.role) await removeRole(state.role.id);
        }}
      />
    </div>
  );
}
