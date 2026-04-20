import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const defaultSettings = {
  allow_social_login: false,
  enforce_mfa: false,
  session_lifetime_seconds: 3600,
  require_email_verification: true,
};

export default function OrganizationNew() {
  const navigate = useNavigate();
  const { isSuperAdmin, setOrgId } = useAuth();
  const [form, setForm] = useState({
    name: '',
    slug: '',
    display_name: '',
    bootstrap_admin: {
      email: '',
      first_name: '',
      last_name: '',
    },
    settings: defaultSettings,
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const updateBootstrapAdmin = (field, value) => {
    setForm(current => ({
      ...current,
      bootstrap_admin: {
        ...current.bootstrap_admin,
        [field]: value,
      },
    }));
  };

  const updateSettings = (field, value) => {
    setForm(current => ({
      ...current,
      settings: {
        ...current.settings,
        [field]: value,
      },
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/api/v1/admin/organizations', form);
      setOrgId(res.data.id);
      navigate(`/organizations/${res.data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Failed to create organization');
    }
    setLoading(false);
  };

  if (!isSuperAdmin) {
    return <div className="text-center py-20 text-dark-400">Only super admins can create organizations.</div>;
  }

  return (
    <div className="max-w-3xl">
      <button onClick={() => navigate('/organizations')} className="text-dark-400 hover:text-dark-200 text-sm mb-4 inline-flex items-center gap-1">← Back</button>
      <h1 className="text-2xl font-bold mb-2">Create Organization</h1>
      <p className="text-dark-400 mb-6">Provision a new tenant and bootstrap its first organization admin in one step.</p>

      <form onSubmit={handleSubmit} className="card space-y-6">
        {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">{error}</div>}

        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Organization</h2>
            <p className="text-sm text-dark-500">This creates the tenant record and seeds its default system roles.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1">Internal Name *</label>
              <input required value={form.name} onChange={e => setForm(current => ({ ...current, name: e.target.value }))} className="input-field" placeholder="acme" />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1">Slug</label>
              <input value={form.slug} onChange={e => setForm(current => ({ ...current, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))} className="input-field" placeholder="Leave blank to auto-generate" />
              <p className="mt-1 text-xs text-dark-500">If left empty, SigAuth will generate an available slug from the organization name.</p>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-1">Display Name</label>
            <input value={form.display_name} onChange={e => setForm(current => ({ ...current, display_name: e.target.value }))} className="input-field" placeholder="Acme Inc" />
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Bootstrap Admin</h2>
            <p className="text-sm text-dark-500">This user is created inside the new org and assigned the `org:admin` role via the bootstrap `admins` group.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1">First Name</label>
              <input value={form.bootstrap_admin.first_name} onChange={e => updateBootstrapAdmin('first_name', e.target.value)} className="input-field" />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1">Last Name</label>
              <input value={form.bootstrap_admin.last_name} onChange={e => updateBootstrapAdmin('last_name', e.target.value)} className="input-field" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-1">Admin Email *</label>
            <input type="email" required value={form.bootstrap_admin.email} onChange={e => updateBootstrapAdmin('email', e.target.value)} className="input-field" />
          </div>
          <p className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            SigAuth will generate a temporary credential automatically and email the first org admin a secure setup link.
          </p>
        </section>

        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Settings</h2>
            <p className="text-sm text-dark-500">Base tenant defaults applied at creation time.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.settings.allow_social_login} onChange={e => updateSettings('allow_social_login', e.target.checked)} className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500" />
              <span className="text-sm text-dark-300">Allow social login</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.settings.enforce_mfa} onChange={e => updateSettings('enforce_mfa', e.target.checked)} className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500" />
              <span className="text-sm text-dark-300">Enforce MFA</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.settings.require_email_verification} onChange={e => updateSettings('require_email_verification', e.target.checked)} className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500" />
              <span className="text-sm text-dark-300">Require email verification</span>
            </label>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1">Session Lifetime (seconds)</label>
              <input type="number" min="300" value={form.settings.session_lifetime_seconds} onChange={e => updateSettings('session_lifetime_seconds', parseInt(e.target.value, 10) || 3600)} className="input-field" />
            </div>
          </div>
        </section>

        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? 'Creating...' : 'Create Organization'}
        </button>
      </form>
    </div>
  );
}
