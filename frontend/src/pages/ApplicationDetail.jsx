import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import { ArrowLeftIcon, PlusIcon, XIcon } from '../components/Icons';
import PageHeader from '../components/PageHeader';
import CopyButton from '../components/CopyButton';
import { hasPermission as userHasPermission } from '../utils/permissions';

const DEFAULT_SCOPES = ['openid', 'profile', 'email'];
const SCOPE_PATTERN = /^[a-zA-Z0-9:._-]+$/;

function normalizeApplicationForm(app) {
  return {
    name: app.name || '',
    logo_url: app.logo_url || '',
    redirect_uris: app.redirect_uris || [],
    post_logout_redirect_uris: app.post_logout_redirect_uris || [],
    allowed_scopes: app.allowed_scopes || DEFAULT_SCOPES,
    id_token_lifetime: app.id_token_lifetime || 3600,
    access_token_lifetime: app.access_token_lifetime || 3600,
    refresh_token_enabled: !!app.refresh_token_enabled,
  };
}

export default function ApplicationDetail() {
  const { id } = useParams();
  const { orgId, claims, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [app, setApp] = useState(null);
  const [newSecret, setNewSecret] = useState(null);
  const [groups, setGroups] = useState([]);
  const [allGroups, setAllGroups] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState('');
  const [allRoles, setAllRoles] = useState([]);
  const [roleMappings, setRoleMappings] = useState([]);
  const [mappingForm, setMappingForm] = useState({ source_type: 'group', source_value: '', app_role: '' });
  const [mappingError, setMappingError] = useState('');
  const [savingMapping, setSavingMapping] = useState(false);
  const [configForm, setConfigForm] = useState(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [configError, setConfigError] = useState('');
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [redirectInput, setRedirectInput] = useState('');
  const [postLogoutRedirectInput, setPostLogoutRedirectInput] = useState('');
  const [scopeInput, setScopeInput] = useState('');
  const [permissionMessage, setPermissionMessage] = useState('');

  const canUpdateApp = isSuperAdmin || userHasPermission(claims, 'app:update');
  const canDeleteApp = isSuperAdmin || userHasPermission(claims, 'app:delete');

  const denyAction = (message = 'You do not have permission to perform this action.') => {
    setPermissionMessage(message);
  };

  const fetchApp = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/applications/${id}`);
      setApp(res.data);
      setConfigForm(normalizeApplicationForm(res.data));
    } catch { navigate('/applications'); }
  };

  const fetchAssignedGroups = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/applications/${id}/groups`);
      setGroups(res.data.data || []);
    } catch {}
  };

  const fetchAllGroups = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/groups?limit=100`);
      setAllGroups(res.data.data || []);
    } catch {}
  };

  const fetchAllRoles = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/roles?limit=100`);
      setAllRoles(res.data.data || []);
    } catch {}
  };

  const fetchRoleMappings = async () => {
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/applications/${id}/role-mappings`);
      setRoleMappings(res.data.data || []);
    } catch {}
  };

  useEffect(() => {
    fetchApp();
    fetchAssignedGroups();
    fetchAllGroups();
    fetchAllRoles();
    fetchRoleMappings();
  }, [id, orgId]);

  const handleRotateSecret = async () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to rotate application secrets.');
      return;
    }
    if (!confirm('Rotate client secret? The old secret will stop working immediately.')) return;
    try {
      const res = await api.post(`/api/v1/organizations/${orgId}/applications/${id}/rotate-secret`);
      setNewSecret(res.data.client_secret);
    } catch {}
  };

  const handleDisable = async () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to disable applications.');
      return;
    }
    if (!confirm('Disable this application?')) return;
    await api.post(`/api/v1/organizations/${orgId}/applications/${id}/disable`);
    fetchApp();
  };

  const handleDelete = async () => {
    if (!canDeleteApp) {
      denyAction('You do not have permission to delete applications.');
      return;
    }
    if (!confirm('Delete this application? All tokens will be revoked.')) return;
    await api.delete(`/api/v1/organizations/${orgId}/applications/${id}`);
    navigate('/applications');
  };

  const assignGroup = async () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to change application group assignments.');
      return;
    }
    if (!selectedGroup) return;
    try {
      await api.post(`/api/v1/organizations/${orgId}/applications/${id}/groups`, { group_ids: [selectedGroup] });
      setSelectedGroup('');
      fetchAssignedGroups();
    } catch {}
  };

  const removeGroup = async (groupId) => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to change application group assignments.');
      return;
    }
    if (!confirm('Remove this group from the application?')) return;
    try {
      await api.delete(`/api/v1/organizations/${orgId}/applications/${id}/groups/${groupId}`);
      fetchAssignedGroups();
    } catch {}
  };

  const updateMappingField = (field, value) => {
    setMappingForm(current => ({ ...current, [field]: value }));
  };

  const addRoleMapping = async () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to manage application role mappings.');
      return;
    }
    const sourceValue = mappingForm.source_value.trim();
    const appRole = mappingForm.app_role.trim();
    if (!sourceValue || !appRole) {
      setMappingError('Source value and app role are required.');
      return;
    }

    setSavingMapping(true);
    setMappingError('');
    try {
      await api.post(`/api/v1/organizations/${orgId}/applications/${id}/role-mappings`, {
        source_type: mappingForm.source_type,
        source_value: sourceValue,
        app_role: appRole,
      });
      setMappingForm({ source_type: mappingForm.source_type, source_value: '', app_role: '' });
      await fetchRoleMappings();
    } catch (err) {
      setMappingError(err.response?.data?.detail?.error_description || 'Unable to create role mapping.');
    }
    setSavingMapping(false);
  };

  const removeRoleMapping = async (mappingId) => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to manage application role mappings.');
      return;
    }
    if (!confirm('Remove this role mapping?')) return;
    try {
      await api.delete(`/api/v1/organizations/${orgId}/applications/${id}/role-mappings/${mappingId}`);
      await fetchRoleMappings();
    } catch {}
  };

  if (!app) return <div className="text-center py-20 text-dark-400">Loading...</div>;
  if (!configForm) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  const typeColors = { web: 'badge-blue', spa: 'badge-purple', native: 'badge-teal', m2m: 'badge-orange' };
  const assignedGroupIds = new Set(groups.map(group => group.id));
  const availableGroups = allGroups.filter(group => !assignedGroupIds.has(group.id));
  const assignedGroupNames = groups.map(group => group.name).sort((a, b) => a.localeCompare(b));
  const availableRoleNames = allRoles.map(role => role.name).sort((a, b) => a.localeCompare(b));
  const mappingSourceCandidates = mappingForm.source_type === 'group' ? assignedGroupNames : availableRoleNames;

  const updateConfigField = (field, value) => {
    setConfigForm(current => ({ ...current, [field]: value }));
  };

  const addRedirectUri = () => {
    if (!isEditingConfig) return;
    const value = redirectInput.trim();
    if (!value) return;

    try {
      const parsed = new URL(value);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        setConfigError('Redirect URI must use http or https.');
        return;
      }
    } catch {
      setConfigError('Redirect URI must be a valid URL.');
      return;
    }

    if (configForm.redirect_uris.includes(value)) {
      setConfigError('Redirect URI already added.');
      return;
    }

    updateConfigField('redirect_uris', [...configForm.redirect_uris, value]);
    setRedirectInput('');
    setConfigError('');
  };

  const removeRedirectUri = (uri) => {
    if (!isEditingConfig) return;
    updateConfigField(
      'redirect_uris',
      configForm.redirect_uris.filter(current => current !== uri)
    );
  };

  const addPostLogoutRedirectUri = () => {
    if (!isEditingConfig) return;
    const value = postLogoutRedirectInput.trim();
    if (!value) return;

    try {
      const parsed = new URL(value);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        setConfigError('Post-logout redirect URI must use http or https.');
        return;
      }
    } catch {
      setConfigError('Post-logout redirect URI must be a valid URL.');
      return;
    }

    if (configForm.post_logout_redirect_uris.includes(value)) {
      setConfigError('Post-logout redirect URI already added.');
      return;
    }

    updateConfigField('post_logout_redirect_uris', [...configForm.post_logout_redirect_uris, value]);
    setPostLogoutRedirectInput('');
    setConfigError('');
  };

  const removePostLogoutRedirectUri = (uri) => {
    if (!isEditingConfig) return;
    updateConfigField(
      'post_logout_redirect_uris',
      configForm.post_logout_redirect_uris.filter(current => current !== uri)
    );
  };

  const addScope = (rawScope = scopeInput) => {
    if (!isEditingConfig) return;
    const value = rawScope.trim();
    if (!value) return;

    if (!SCOPE_PATTERN.test(value)) {
      setConfigError('Scopes may contain only letters, numbers, and : . _ -');
      return;
    }

    if (configForm.allowed_scopes.includes(value)) {
      setConfigError('Scope already added.');
      return;
    }

    updateConfigField('allowed_scopes', [...configForm.allowed_scopes, value]);
    setScopeInput('');
    setConfigError('');
  };

  const removeScope = (scope) => {
    if (!isEditingConfig) return;
    updateConfigField(
      'allowed_scopes',
      configForm.allowed_scopes.filter(current => current !== scope)
    );
  };

  const handleEditStart = () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to edit application configuration.');
      return;
    }
    setConfigError('');
    setPermissionMessage('');
    setConfigForm(normalizeApplicationForm(app));
    setRedirectInput('');
    setPostLogoutRedirectInput('');
    setScopeInput('');
    setIsEditingConfig(true);
  };

  const handleEditCancel = () => {
    setConfigError('');
    setPermissionMessage('');
    setConfigForm(normalizeApplicationForm(app));
    setRedirectInput('');
    setPostLogoutRedirectInput('');
    setScopeInput('');
    setIsEditingConfig(false);
  };

  const handleSaveConfig = async () => {
    if (!canUpdateApp) {
      denyAction('You do not have permission to edit application configuration.');
      return;
    }
    setSavingConfig(true);
    setConfigError('');
    try {
      const payload = {
        name: configForm.name,
        logo_url: configForm.logo_url || null,
        redirect_uris: configForm.redirect_uris,
        post_logout_redirect_uris: configForm.post_logout_redirect_uris,
        allowed_scopes: configForm.allowed_scopes,
        id_token_lifetime: Number(configForm.id_token_lifetime),
        access_token_lifetime: Number(configForm.access_token_lifetime),
        refresh_token_enabled: !!configForm.refresh_token_enabled,
      };
      const res = await api.patch(`/api/v1/organizations/${orgId}/applications/${id}`, payload);
      setApp(res.data);
      setConfigForm(normalizeApplicationForm(res.data));
      setIsEditingConfig(false);
    } catch (err) {
      setConfigError(err.response?.data?.detail?.error_description || 'Unable to save application configuration.');
    }
    setSavingConfig(false);
  };

  return (
    <div>
      <button onClick={() => navigate('/applications')} className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to applications
      </button>

      <PageHeader
        eyebrow="Application"
        title={app.name}
        description="View client credentials, token policy, and application-specific group assignments."
        actions={
          <div className="flex gap-2">
            {['web', 'm2m'].includes(app.app_type) && (
              <button onClick={handleRotateSecret} className={`btn-secondary text-sm ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>Rotate secret</button>
            )}
            {app.status === 'active' && <button onClick={handleDisable} className={`btn-danger text-sm ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>Disable</button>}
            <button onClick={handleDelete} className={`btn-danger text-sm ${canDeleteApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canDeleteApp}>Delete</button>
          </div>
        }
      />

      {permissionMessage ? (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {permissionMessage}
        </div>
      ) : null}

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <span className={typeColors[app.app_type] || 'badge-gray'}>{app.app_type}</span>
        <span className={app.status === 'active' ? 'badge-green' : 'badge-red'}>{app.status}</span>
        <span className="badge-gray">{groups.length} assigned group{groups.length === 1 ? '' : 's'}</span>
      </div>

      {newSecret && (
        <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-6">
          <h3 className="mb-2 font-semibold text-red-700">New Client Secret (ONE-TIME DISPLAY)</h3>
          <code className="block rounded-lg bg-white p-3 font-mono text-sm break-all text-red-700">{newSecret}</code>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Credentials</h2>
          <dl className="space-y-4">
            <div>
              <dt className="text-xs text-slate-500 uppercase">Client ID</dt>
              <dd className="mt-1 flex items-center gap-2 break-all font-mono text-blue-700">
                {app.client_id}
                <CopyButton value={app.client_id} label="Copy client id" />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Client Secret</dt>
              <dd className="mt-1 text-sm italic text-slate-500">
                {['web', 'm2m'].includes(app.app_type) ? 'Hidden (rotate to get new one)' : 'N/A for public apps'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Configuration</h2>
          {configError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {configError}
            </div>
          )}
          <dl className="space-y-4">
            <div>
              <dt className="text-xs text-slate-500 uppercase">Name</dt>
              <dd className="mt-1">
                <input
                  value={configForm.name}
                  onChange={e => updateConfigField('name', e.target.value)}
                  className="input-field"
                  disabled={!isEditingConfig || !canUpdateApp}
                />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Logo URL</dt>
              <dd className="mt-1">
                <input
                  value={configForm.logo_url}
                  onChange={e => updateConfigField('logo_url', e.target.value)}
                  className="input-field"
                  placeholder="https://example.com/logo.svg"
                  disabled={!isEditingConfig || !canUpdateApp}
                />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Redirect URIs</dt>
              <dd className="mt-1">
                <div className="flex gap-2">
                  <input
                    value={redirectInput}
                    onChange={e => setRedirectInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addRedirectUri();
                      }
                    }}
                    className="input-field font-mono text-xs"
                    placeholder="https://app.example.com/callback"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                  <button type="button" onClick={addRedirectUri} className={`btn-secondary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} disabled={!isEditingConfig || !canUpdateApp}>Add</button>
                </div>
                <div className="mt-3 space-y-2">
                  {configForm.redirect_uris.map(uri => (
                    <div key={uri} className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="font-mono text-xs text-slate-700 break-all">{uri}</span>
                      <div className="flex items-center gap-2">
                        <CopyButton value={uri} label="Copy redirect URI" />
                        <button type="button" onClick={() => removeRedirectUri(uri)} className="text-red-700 hover:text-red-800" disabled={!isEditingConfig || !canUpdateApp}>
                          <XIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                  {configForm.redirect_uris.length === 0 && (
                    <p className="text-xs text-slate-500">No redirect URIs added.</p>
                  )}
                </div>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Post-Logout Redirect URIs</dt>
              <dd className="mt-1">
                <div className="flex gap-2">
                  <input
                    value={postLogoutRedirectInput}
                    onChange={e => setPostLogoutRedirectInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addPostLogoutRedirectUri();
                      }
                    }}
                    className="input-field font-mono text-xs"
                    placeholder="https://app.example.com/logged-out"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                  <button type="button" onClick={addPostLogoutRedirectUri} className={`btn-secondary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} disabled={!isEditingConfig || !canUpdateApp}>Add</button>
                </div>
                <div className="mt-3 space-y-2">
                  {configForm.post_logout_redirect_uris.map(uri => (
                    <div key={uri} className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="font-mono text-xs text-slate-700 break-all">{uri}</span>
                      <div className="flex items-center gap-2">
                        <CopyButton value={uri} label="Copy post-logout redirect URI" />
                        <button type="button" onClick={() => removePostLogoutRedirectUri(uri)} className="text-red-700 hover:text-red-800" disabled={!isEditingConfig || !canUpdateApp}>
                          <XIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                  {configForm.post_logout_redirect_uris.length === 0 && (
                    <p className="text-xs text-slate-500">No post-logout redirect URIs added.</p>
                  )}
                </div>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Allowed Scopes</dt>
              <dd className="mt-1">
                <div className="flex gap-2">
                  <input
                    value={scopeInput}
                    onChange={e => setScopeInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addScope();
                      }
                    }}
                    className="input-field"
                    placeholder="Type scope and press Enter"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                  <button type="button" onClick={() => addScope()} className={`btn-secondary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} disabled={!isEditingConfig || !canUpdateApp}>Add</button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {DEFAULT_SCOPES.map(scope => (
                    <button
                      key={scope}
                      type="button"
                      onClick={() => addScope(scope)}
                      className="badge-gray hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                      disabled={!isEditingConfig || !canUpdateApp}
                    >
                      + {scope}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {configForm.allowed_scopes.map(scope => (
                    <span key={scope} className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                      {scope}
                      <button type="button" onClick={() => removeScope(scope)} className="text-blue-700 hover:text-blue-900" disabled={!isEditingConfig || !canUpdateApp}>
                        <XIcon className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  ))}
                  {configForm.allowed_scopes.length === 0 && (
                    <p className="text-xs text-slate-500">No scopes added.</p>
                  )}
                </div>
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-xs text-slate-500 uppercase">ID Token TTL</dt>
                <dd className="mt-1">
                  <input
                    type="number"
                    min="300"
                    max="86400"
                    value={configForm.id_token_lifetime}
                    onChange={e => updateConfigField('id_token_lifetime', e.target.value)}
                    className="input-field"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 uppercase">Access Token TTL</dt>
                <dd className="mt-1">
                  <input
                    type="number"
                    min="300"
                    max="86400"
                    value={configForm.access_token_lifetime}
                    onChange={e => updateConfigField('access_token_lifetime', e.target.value)}
                    className="input-field"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                </dd>
              </div>
            </div>
            <div>
              <dt className="text-xs text-slate-500 uppercase">Refresh Token</dt>
              <dd className="mt-2">
                <label className="flex items-center gap-3 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={!!configForm.refresh_token_enabled}
                    onChange={e => updateConfigField('refresh_token_enabled', e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    disabled={!isEditingConfig || !canUpdateApp}
                  />
                  Enable refresh tokens for this application
                </label>
              </dd>
            </div>
            <div className="pt-2 flex gap-3">
              {!isEditingConfig && (
                <button onClick={handleEditStart} className={`btn-secondary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>
                  Edit configuration
                </button>
              )}
              {isEditingConfig && (
                <>
                  <button onClick={handleEditCancel} className="btn-secondary" disabled={savingConfig}>
                    Cancel
                  </button>
                  <button onClick={handleSaveConfig} disabled={savingConfig || !canUpdateApp} className="btn-primary">
                    {savingConfig ? 'Saving...' : 'Save configuration'}
                  </button>
                </>
              )}
            </div>
          </dl>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Assigned Groups</h2>
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Regular users can sign in only if they belong to one of these groups. Organization admins can always sign in, and role mappings remain optional.
          </div>
          <div className="flex gap-3 mb-5">
            <select value={selectedGroup} onChange={e => setSelectedGroup(e.target.value)} className="input-field" disabled={!canUpdateApp}>
              <option value="">Select group to assign...</option>
              {availableGroups.map(group => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
            <button onClick={assignGroup} disabled={canUpdateApp && !selectedGroup} className={`btn-primary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>
              <PlusIcon className="h-4 w-4" />
              Assign
            </button>
          </div>

          <div className="space-y-3">
            {groups.map(group => (
              <div key={group.id} className="flex items-start justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-slate-900">{group.name}</p>
                  <p className="mt-1 text-xs text-slate-500">{group.description || 'No description'}</p>
                </div>
                <button onClick={() => removeGroup(group.id)} className={`text-sm font-medium text-red-700 hover:text-red-800 ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>Remove</button>
              </div>
            ))}
            {groups.length === 0 && <p className="text-sm text-slate-500">No groups assigned to this application.</p>}
          </div>
        </div>

        <div className="card xl:col-span-3">
          <h2 className="text-lg font-semibold mb-4">Application Role Mappings</h2>
          <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
            app_roles are derived from these mappings first. If no mappings exist, the platform fallback heuristic is used.
          </div>
          {mappingError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {mappingError}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
            <select
              value={mappingForm.source_type}
              onChange={e => {
                if (!canUpdateApp) {
                  return;
                }
                const nextType = e.target.value;
                setMappingError('');
                setMappingForm({ source_type: nextType, source_value: '', app_role: mappingForm.app_role });
              }}
              className="input-field"
              disabled={!canUpdateApp}
            >
              <option value="group">From App Group</option>
              <option value="role">From Org Role</option>
            </select>
            <input
              list={`mapping-source-options-${mappingForm.source_type}`}
              value={mappingForm.source_value}
              onChange={e => updateMappingField('source_value', e.target.value)}
              className="input-field"
              placeholder={mappingForm.source_type === 'group' ? 'e.g. sigverse-admins' : 'e.g. org:admin'}
              disabled={!canUpdateApp}
            />
            <datalist id={`mapping-source-options-${mappingForm.source_type}`}>
              {mappingSourceCandidates.map(name => (
                <option key={name} value={name} />
              ))}
            </datalist>
            <input
              value={mappingForm.app_role}
              onChange={e => updateMappingField('app_role', e.target.value)}
              className="input-field"
              placeholder="e.g. delivery_agent"
              disabled={!canUpdateApp}
            />
            <button onClick={addRoleMapping} disabled={savingMapping} className={`btn-primary ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>
              {savingMapping ? 'Adding...' : 'Add mapping'}
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-slate-500">Source Type</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-slate-500">Source Value</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-slate-500">App Role</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold uppercase text-slate-500">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {roleMappings.map(mapping => (
                  <tr key={mapping.id}>
                    <td className="px-4 py-2 text-sm text-slate-700">{mapping.source_type}</td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-xs text-slate-700">{mapping.source_value}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                        {mapping.app_role}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button onClick={() => removeRoleMapping(mapping.id)} className={`text-sm font-medium text-red-700 hover:text-red-800 ${canUpdateApp ? '' : 'cursor-not-allowed opacity-55'}`} aria-disabled={!canUpdateApp}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
                {roleMappings.length === 0 && (
                  <tr>
                    <td colSpan="4" className="px-4 py-5 text-sm text-slate-500">
                      No role mappings configured. Token generation will use fallback group-name heuristics.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
