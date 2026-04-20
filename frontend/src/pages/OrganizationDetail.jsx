import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import PageHeader from '../components/PageHeader';
import { ArrowLeftIcon } from '../components/Icons';
import CopyButton from '../components/CopyButton';
import ConfirmDialog from '../components/ConfirmDialog';

const DEFAULT_SETTINGS = {
  allow_social_login: false,
  enforce_mfa: false,
  session_lifetime_seconds: 3600,
  require_email_verification: true,
};

function buildSettingsForm(settings = {}) {
  return {
    ...DEFAULT_SETTINGS,
    ...settings,
  };
}

export default function OrganizationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isSuperAdmin } = useAuth();
  const [org, setOrg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  const [form, setForm] = useState({
    display_name: '',
    ...DEFAULT_SETTINGS,
  });

  const accessTier = org?.settings?.access_tier || 'verified_enterprise';
  const verificationStatus = org?.settings?.verification_status || (accessTier === 'limited' ? 'pending' : 'approved');
  const upgradeRequestStatus = org?.settings?.upgrade_request?.status || null;

  useEffect(() => {
    if (!isSuperAdmin) {
      navigate('/dashboard');
      return;
    }
    api.get(`/api/v1/admin/organizations/${id}`)
      .then(res => {
        const nextOrg = res.data;
        setOrg(nextOrg);
        setForm({
          display_name: nextOrg.display_name || '',
          ...buildSettingsForm(nextOrg.settings),
        });
      })
      .catch(() => navigate('/organizations'))
      .finally(() => setLoading(false));
  }, [id, isSuperAdmin, navigate]);

  const updateField = (field, value) => {
    setForm(current => ({ ...current, [field]: value }));
  };

  const handleUpdate = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {
        display_name: form.display_name || null,
        settings: {
          ...(org?.settings || {}),
          allow_social_login: !!form.allow_social_login,
          enforce_mfa: !!form.enforce_mfa,
          session_lifetime_seconds: Number(form.session_lifetime_seconds) || DEFAULT_SETTINGS.session_lifetime_seconds,
          require_email_verification: !!form.require_email_verification,
        },
      };
      const res = await api.patch(`/api/v1/admin/organizations/${id}`, payload);
      setOrg(res.data);
      setForm({
        display_name: res.data.display_name || '',
        ...buildSettingsForm(res.data.settings),
      });
      setIsEditing(false);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to save organization settings.');
    }
    setSaving(false);
  };

  const handleEditStart = () => {
    setError('');
    setForm({
      display_name: org.display_name || '',
      ...buildSettingsForm(org.settings),
    });
    setIsEditing(true);
  };

  const handleEditCancel = () => {
    setError('');
    setForm({
      display_name: org.display_name || '',
      ...buildSettingsForm(org.settings),
    });
    setIsEditing(false);
  };

  const handleSuspend = async () => {
    const res = await api.post(`/api/v1/admin/organizations/${id}/suspend`);
    setOrg(res.data);
    setSuccess('Organization suspended.');
  };

  const handleActivate = async () => {
    const res = await api.post(`/api/v1/admin/organizations/${id}/activate`);
    setOrg(res.data);
    setSuccess('Organization activated.');
  };

  const handleVerifyEnterprise = async () => {
    const res = await api.post(`/api/v1/admin/organizations/${id}/verify-enterprise`);
    setOrg(res.data);
    setSuccess('Organization moved to verified enterprise.');
  };

  const handleSetLimited = async () => {
    const res = await api.post(`/api/v1/admin/organizations/${id}/set-limited`);
    setOrg(res.data);
    setSuccess('Organization moved to limited tier.');
  };

  const handleApproveUpgradeRequest = async () => {
    const res = await api.post(`/api/v1/admin/organizations/${id}/approve-upgrade-request`);
    setOrg(res.data);
    setSuccess('Upgrade request approved.');
  };

  const handleDeleteOrganization = async () => {
    await api.delete(`/api/v1/admin/organizations/${id}`);
    navigate('/organizations');
  };

  if (loading || !org) return <div className="text-center py-20 text-dark-400">Loading...</div>;

  return (
    <div>
      <button onClick={() => navigate('/organizations')} className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to organizations
      </button>

      <PageHeader
        eyebrow="Organization"
        title={org.display_name || org.name}
        description="Update tenant presentation and policy settings without editing raw JSON."
        actions={
          <div className="flex gap-3">
            {org.status === 'active' && <button onClick={() => setConfirmState('suspend')} className="btn-danger">Suspend</button>}
            {org.status === 'suspended' && <button onClick={handleActivate} className="btn-primary">Activate</button>}
            {accessTier === 'limited' && org.status === 'active' && (
              <button onClick={handleVerifyEnterprise} className="btn-primary">
                Verify Enterprise
              </button>
            )}
            {upgradeRequestStatus === 'submitted' && org.status === 'active' && (
              <button onClick={handleApproveUpgradeRequest} className="btn-primary">
                Approve Upgrade Request
              </button>
            )}
            {accessTier === 'verified_enterprise' && org.status === 'active' && (
              <button onClick={handleSetLimited} className="btn-secondary">
                Set Limited
              </button>
            )}
            <button onClick={() => setConfirmState('delete')} className="btn-danger">
              Delete
            </button>
          </div>
        }
      />

      {success ? (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      ) : null}

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <span className={org.status === 'active' ? 'badge-green' : 'badge-yellow'}>{org.status}</span>
        <span className="badge-gray font-mono">{org.slug}</span>
        <span className={accessTier === 'limited' ? 'badge-yellow' : 'badge-blue'}>
          {accessTier === 'limited' ? 'self-serve limited' : 'verified enterprise'}
        </span>
        <span className={verificationStatus === 'approved' ? 'badge-green' : 'badge-orange'}>
          verification: {verificationStatus}
        </span>
        {upgradeRequestStatus ? (
          <span className={upgradeRequestStatus === 'submitted' ? 'badge-yellow' : upgradeRequestStatus === 'approved' ? 'badge-green' : 'badge-gray'}>
            request: {upgradeRequestStatus}
          </span>
        ) : null}
        <CopyButton value={org.slug} label="Copy organization slug" />
      </div>

      <div className="card">
        <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-600">Internal Name</label>
            <p className="text-slate-900">{org.name}</p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-600">Created</label>
            <p className="text-slate-900">{new Date(org.created_at).toLocaleString()}</p>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-sm font-medium text-slate-600">Display Name</label>
            <input
              value={form.display_name}
              onChange={e => updateField('display_name', e.target.value)}
              className="input-field"
              placeholder="Customer-facing organization name"
              disabled={!isEditing}
            />
          </div>
        </div>

        <div className="mb-6 border-t border-slate-200 pt-6">
          <h2 className="text-lg font-semibold text-slate-900">Settings</h2>
          <p className="mt-1 text-sm text-slate-500">Control tenant sign-in and session policies with structured fields.</p>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {org.settings?.upgrade_request?.payload ? (
          <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-4">
            <p className="text-sm font-semibold text-amber-900">Upgrade request details</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {Object.entries(org.settings.upgrade_request.payload).map(([key, value]) => (
                <div key={key}>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-800">{key.replace(/_/g, ' ')}</p>
                  <p className="mt-1 text-sm text-slate-700">{String(value || '—')}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
            <input
              type="checkbox"
              checked={!!form.allow_social_login}
              onChange={e => updateField('allow_social_login', e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              disabled={!isEditing}
            />
            <span>
              <span className="block text-sm font-semibold text-slate-900">Allow social login</span>
              <span className="mt-1 block text-sm text-slate-500">Permit configured external identity providers for this organization.</span>
            </span>
          </label>

          <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
            <input
              type="checkbox"
              checked={!!form.enforce_mfa}
              onChange={e => updateField('enforce_mfa', e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              disabled={!isEditing}
            />
            <span>
              <span className="block text-sm font-semibold text-slate-900">Enforce MFA</span>
              <span className="mt-1 block text-sm text-slate-500">Require multi-factor authentication across this tenant.</span>
            </span>
          </label>

          <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
            <input
              type="checkbox"
              checked={!!form.require_email_verification}
              onChange={e => updateField('require_email_verification', e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              disabled={!isEditing}
            />
            <span>
              <span className="block text-sm font-semibold text-slate-900">Require email verification</span>
              <span className="mt-1 block text-sm text-slate-500">Block new users until their email address is verified.</span>
            </span>
          </label>

          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
            <label className="mb-1 block text-sm font-semibold text-slate-900">Session lifetime (seconds)</label>
            <p className="mb-3 text-sm text-slate-500">Set the default browser session length for this organization.</p>
            <input
              type="number"
              min="300"
              step="300"
              value={form.session_lifetime_seconds}
              onChange={e => updateField('session_lifetime_seconds', e.target.value)}
              className="input-field"
              disabled={!isEditing}
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          {!isEditing && (
            <button onClick={handleEditStart} className="btn-secondary">
              Edit settings
            </button>
          )}
          {isEditing && (
            <>
              <button onClick={handleEditCancel} className="btn-secondary" disabled={saving}>
                Cancel
              </button>
              <button onClick={handleUpdate} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save settings'}
              </button>
            </>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={!!confirmState}
        title={confirmState === 'suspend' ? 'Suspend organization?' : 'Delete organization?'}
        description={
          confirmState === 'suspend'
            ? 'This tenant will be suspended and normal sign-in should stop until reactivated.'
            : 'This is a soft delete. The tenant will disappear from normal operations.'
        }
        confirmLabel={confirmState === 'suspend' ? 'Suspend organization' : 'Delete organization'}
        onClose={() => setConfirmState(null)}
        onConfirm={async () => {
          const action = confirmState;
          setConfirmState(null);
          if (action === 'suspend') await handleSuspend();
          if (action === 'delete') await handleDeleteOrganization();
        }}
      />
    </div>
  );
}
