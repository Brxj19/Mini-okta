import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import RoleBadge from '../components/RoleBadge';
import PageHeader from '../components/PageHeader';
import UserAvatar from '../components/UserAvatar';
import { ArrowLeftIcon, CheckIcon, XIcon } from '../components/Icons';
import CopyButton from '../components/CopyButton';
import ConfirmDialog from '../components/ConfirmDialog';
import { getDisplayName } from '../utils/profile';
import { hasPermission, hasRole } from '../utils/permissions';

export default function UserDetail() {
  const { id } = useParams();
  const { orgId, claims, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [notificationPreferences, setNotificationPreferences] = useState([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirmAction, setConfirmAction] = useState(null);

  const fetchUser = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/users/${id}`);
      setUser(res.data);
      setEditForm({
        first_name: res.data?.first_name || '',
        last_name: res.data?.last_name || '',
      });
    } catch { navigate('/users'); }
    setLoading(false);
  };

  const fetchNotificationPreferences = async () => {
    if (!orgId || !id) return;
    setPreferencesLoading(true);
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/users/${id}/notification-preferences`);
      setNotificationPreferences(res.data?.preferences || []);
    } catch {
      setNotificationPreferences([]);
    } finally {
      setPreferencesLoading(false);
    }
  };

  useEffect(() => {
    fetchUser();
    fetchNotificationPreferences();
  }, [id, orgId]);

  const handleEditSave = async () => {
    setSavingEdit(true);
    setError('');
    setMessage('');
    try {
      const res = await api.patch(`/api/v1/organizations/${orgId}/users/${id}`, editForm);
      setUser((current) => ({ ...current, ...res.data }));
      setIsEditing(false);
      setMessage('User details updated.');
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to update this user.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleSuspend = async () => {
    await api.post(`/api/v1/organizations/${orgId}/users/${id}/suspend`);
    fetchUser();
  };

  const handleUnlock = async () => {
    await api.post(`/api/v1/organizations/${orgId}/users/${id}/unlock`);
    fetchUser();
  };

  const handleResetPassword = async () => {
    await api.post(`/api/v1/organizations/${orgId}/users/${id}/reset-password`);
  };

  const handleRevokeSessions = async () => {
    await api.post(`/api/v1/organizations/${orgId}/users/${id}/revoke-sessions`);
  };

  const handleDelete = async () => {
    await api.delete(`/api/v1/organizations/${orgId}/users/${id}`);
    navigate('/users');
  };

  const togglePreference = async (eventKey, enabled) => {
    const nextPreferences = notificationPreferences.map((item) => (
      item.event_key === eventKey ? { ...item, enabled } : item
    ));
    setNotificationPreferences(nextPreferences);
    setPreferencesSaving(true);
    setError('');
    setMessage('');
    try {
      const res = await api.put(`/api/v1/organizations/${orgId}/users/${id}/notification-preferences`, {
        preferences: nextPreferences.map((item) => ({
          event_key: item.event_key,
          enabled: item.enabled,
        })),
      });
      setNotificationPreferences(res.data?.preferences || nextPreferences);
      setMessage('Notification preferences updated.');
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to update notification preferences.');
      await fetchNotificationPreferences();
    } finally {
      setPreferencesSaving(false);
    }
  };

  if (loading || !user) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  const displayName = getDisplayName(user, user.email);
  const actorCanManageProtectedUsers = isSuperAdmin || hasRole(claims, 'org:admin');
  const targetIsProtected = !!user.is_super_admin || (user.roles || []).includes('org:admin');
  const isSelf = claims?.sub === user.id;
  const allowSensitiveActions = !targetIsProtected || actorCanManageProtectedUsers;
  const canUpdateUsers = hasPermission(claims, 'user:update');
  const canResetPasswords = hasPermission(claims, 'user:reset_password');
  const canDeleteUsers = hasPermission(claims, 'user:delete');
  const canReadUsers = hasPermission(claims, 'user:read');
  const canRevokeSessions = canUpdateUsers && allowSensitiveActions && !isSelf;
  const canSuspendUser = canUpdateUsers && allowSensitiveActions && !isSelf && user.status === 'active';
  const canUnlockUser = canUpdateUsers && allowSensitiveActions && !isSelf && (user.status === 'locked' || user.status === 'suspended');
  const canResetUserPassword = canResetPasswords && allowSensitiveActions && !isSelf;
  const canDeleteUser = canDeleteUsers && allowSensitiveActions && !isSelf;
  const canEditUser = canUpdateUsers && allowSensitiveActions && !isSelf;

  return (
    <div>
      <button onClick={() => navigate('/users')} className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-dark-400 hover:text-dark-200">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to users
      </button>

      <PageHeader
        eyebrow="User Profile"
        title={displayName}
        description={user.email}
        actions={
          <div className="flex gap-2">
            <button
              onClick={() => setConfirmAction('revoke')}
              className={`btn-secondary text-sm ${canRevokeSessions ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canRevokeSessions}
            >
              Revoke sessions
            </button>
            <button
              onClick={() => setConfirmAction('reset')}
              className={`btn-secondary text-sm ${canResetUserPassword ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canResetUserPassword}
            >
              Reset password
            </button>
            <button
              onClick={() => setConfirmAction('suspend')}
              className={`btn-danger text-sm ${canSuspendUser ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canSuspendUser}
            >
              Suspend
            </button>
            <button
              onClick={() => setConfirmAction('unlock')}
              className={`btn-secondary text-sm ${canUnlockUser ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canUnlockUser}
            >
              Unlock
            </button>
            <button
              onClick={() => setConfirmAction('delete')}
              className={`btn-danger text-sm ${canDeleteUser ? '' : 'cursor-not-allowed opacity-55'}`}
              disabled={!canDeleteUser}
            >
              Delete
            </button>
          </div>
        }
      />

      {error ? (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}

      {isSelf ? (
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          Administrative self-actions are blocked here. Use the normal account settings and sign-out flows for your own account.
        </div>
      ) : null}
      {targetIsProtected && !allowSensitiveActions ? (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          This account has administrator access. Only organization admins can revoke sessions, reset passwords, suspend, or delete it.
        </div>
      ) : null}

      <div className="mb-8 flex items-center gap-4 rounded-xl border border-dark-700 bg-dark-900 p-5 shadow-sm">
          <UserAvatar user={user} className="h-14 w-14" textClassName="text-lg" />
          <div>
            <p className="text-base font-semibold text-dark-100">{displayName}</p>
            <div className="mt-1 flex items-center gap-2">
              <p className="text-sm text-dark-400">{user.email}</p>
              <CopyButton value={user.email} label="Copy email" />
            </div>
          </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Details</h2>
            {canEditUser ? (
              isEditing ? (
                <div className="flex gap-2">
                  <button onClick={() => {
                    setIsEditing(false);
                    setEditForm({ first_name: user.first_name || '', last_name: user.last_name || '' });
                  }} className="btn-secondary text-sm" disabled={savingEdit}>
                    Cancel
                  </button>
                  <button onClick={handleEditSave} className="btn-primary text-sm" disabled={savingEdit}>
                    {savingEdit ? 'Saving...' : 'Save'}
                  </button>
                </div>
              ) : (
                <button onClick={() => setIsEditing(true)} className="btn-secondary text-sm">
                  Edit user
                </button>
              )
            ) : null}
          </div>
          <dl className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-dark-400 uppercase">First name</dt>
                <dd className="mt-1 text-dark-300">
                  {isEditing ? (
                    <input
                      value={editForm.first_name}
                      onChange={(event) => setEditForm((current) => ({ ...current, first_name: event.target.value }))}
                      className="input-field"
                      placeholder="First name"
                    />
                  ) : (
                    user.first_name || '—'
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-dark-400 uppercase">Last name</dt>
                <dd className="mt-1 text-dark-300">
                  {isEditing ? (
                    <input
                      value={editForm.last_name}
                      onChange={(event) => setEditForm((current) => ({ ...current, last_name: event.target.value }))}
                      className="input-field"
                      placeholder="Last name"
                    />
                  ) : (
                    user.last_name || '—'
                  )}
                </dd>
              </div>
            </div>
            <div><dt className="text-xs text-dark-400 uppercase">Status</dt><dd className="mt-1"><span className={user.status === 'active' ? 'badge-green' : 'badge-red'}>{user.status}</span></dd></div>
            <div><dt className="text-xs text-dark-400 uppercase">Email Verified</dt><dd className="mt-1">{user.email_verified ? <span className="badge-green"><CheckIcon className="h-3.5 w-3.5" />Verified</span> : <span className="badge-gray"><XIcon className="h-3.5 w-3.5" />Not verified</span>}</dd></div>
            <div><dt className="text-xs text-dark-400 uppercase">MFA</dt><dd className="mt-1">{user.mfa_enabled ? <span className="badge-green"><CheckIcon className="h-3.5 w-3.5" />Enabled</span> : <span className="badge-gray"><XIcon className="h-3.5 w-3.5" />Disabled</span>}</dd></div>
            <div><dt className="text-xs text-dark-400 uppercase">Last Login</dt><dd className="mt-1 text-dark-300">{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '—'}</dd></div>
            <div><dt className="text-xs text-dark-400 uppercase">Created</dt><dd className="mt-1 text-dark-300">{new Date(user.created_at).toLocaleString()}</dd></div>
            <div>
              <dt className="text-xs text-dark-400 uppercase">User ID</dt>
              <dd className="mt-1 flex items-center gap-2 text-dark-300 font-mono text-xs break-all">
                {user.id}
                <CopyButton value={user.id} label="Copy user id" />
              </dd>
            </div>
          </dl>
        </div>

        <div className="space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold mb-3">Groups</h2>
            <div className="flex flex-wrap gap-2">
              {(user.groups || []).length === 0 && <span className="text-dark-500 text-sm">No group memberships</span>}
              {(user.groups || []).map(g => (
                <span key={g.id} className="badge-blue" title={g.description || g.name}>
                  {g.name}
                </span>
              ))}
            </div>
          </div>
          <div className="card">
            <h2 className="text-lg font-semibold mb-3">Effective Roles</h2>
            <div className="flex flex-wrap gap-2">
              {(user.roles || []).length === 0 && <span className="text-dark-500 text-sm">No roles assigned</span>}
              {(user.roles || []).map(r => <RoleBadge key={r} role={r} />)}
            </div>
          </div>
          <div className="card">
            <h2 className="text-lg font-semibold mb-3">Effective Permissions</h2>
            <div className="flex flex-wrap gap-1.5">
              {(user.permissions || []).length === 0 && <span className="text-dark-500 text-sm">No permissions</span>}
              {(user.permissions || []).map(p => (
                <span key={p} className="badge-gray text-xs">{p}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {canReadUsers ? (
        <div className="card mt-6">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Notification Preferences</h2>
            {preferencesSaving ? <span className="text-xs text-dark-400">Saving...</span> : null}
          </div>
          {preferencesLoading ? (
            <p className="text-sm text-dark-500">Loading preferences...</p>
          ) : (
            <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
              {notificationPreferences.map((preference) => (
                <label key={preference.event_key} className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{preference.event_key}</span>
                    <span className="block text-xs text-slate-500">Control whether this user receives alerts for this event.</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={!!preference.enabled}
                    onChange={(event) => togglePreference(preference.event_key, event.target.checked)}
                    disabled={preferencesSaving || !canEditUser}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                </label>
              ))}
            </div>
          )}
        </div>
      ) : null}

      <ConfirmDialog
        open={!!confirmAction}
        title={
          confirmAction === 'suspend' ? 'Suspend user?' :
          confirmAction === 'unlock' ? 'Unlock user?' :
          confirmAction === 'reset' ? 'Send password reset email?' :
          confirmAction === 'revoke' ? 'Revoke all active sessions?' :
          confirmAction === 'delete' ? 'Delete user?' :
          ''
        }
        description={
          confirmAction === 'suspend' ? 'This will suspend the user and revoke all of their active sessions.' :
          confirmAction === 'unlock' ? 'This will reactivate the user account so they can sign in again.' :
          confirmAction === 'reset' ? 'A password reset email will be sent to this user.' :
          confirmAction === 'revoke' ? 'This will revoke all active sessions for this user across SigAuth and connected apps.' :
          confirmAction === 'delete' ? 'This user will be soft-deleted and removed from normal operations.' :
          ''
        }
        confirmLabel={
          confirmAction === 'reset' ? 'Send email' :
          confirmAction === 'revoke' ? 'Revoke sessions' :
          confirmAction === 'unlock' ? 'Unlock user' :
          confirmAction === 'suspend' ? 'Suspend user' :
          confirmAction === 'delete' ? 'Delete user' :
          'Confirm'
        }
        onClose={() => setConfirmAction(null)}
        onConfirm={async () => {
          const action = confirmAction;
          setConfirmAction(null);
          if (action === 'suspend') await handleSuspend();
          if (action === 'unlock') await handleUnlock();
          if (action === 'reset') await handleResetPassword();
          if (action === 'revoke') await handleRevokeSessions();
          if (action === 'delete') await handleDelete();
        }}
      />
    </div>
  );
}
