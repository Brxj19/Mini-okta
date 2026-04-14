import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../api/client';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../branding';
import { ArrowLeftIcon, ProductMark } from '../components/Icons';
import PasswordCriteria from '../components/PasswordCriteria';
import AuthParticleCanvas from '../components/AuthParticleCanvas';

export default function Signup() {
  const navigate = useNavigate();
  const [mode, setMode] = useState('organization');
  const [form, setForm] = useState({
    organization_name: '',
    organization_slug: '',
    admin_first_name: '',
    admin_last_name: '',
    admin_email: '',
    admin_password: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const payload = {
        organization_name: form.organization_name.trim(),
        organization_slug: form.organization_slug.trim() || null,
        admin_first_name: form.admin_first_name.trim() || null,
        admin_last_name: form.admin_last_name.trim() || null,
        admin_email: form.admin_email.trim(),
        admin_password: form.admin_password,
      };
      const res = await api.post('/api/v1/signup/organization', payload);
      const orgSlug = res?.data?.organization?.slug;
      setSuccess(
        `Organization created in free self-serve mode${orgSlug ? ` (${orgSlug})` : ''}. Sign in as org admin and choose a paid plan whenever you want to unlock full access.`
      );
      setTimeout(() => navigate('/login'), 1400);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Could not complete organization signup.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-cosmos-shell flex min-h-screen items-start justify-center px-4 py-6 sm:py-10 md:items-center">
      <AuthParticleCanvas />
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_20px_48px_rgba(15,23,42,0.08)] sm:p-8">
        <div className="mb-5">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            Back to home
          </Link>
        </div>

        <div className="mb-6 flex items-center gap-3">
          <ProductMark className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Get Started With {PRODUCT_NAME}</h1>
            <p className="text-sm text-gray-600">{PRODUCT_TAGLINE}</p>
          </div>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-2 rounded-lg border border-gray-200 bg-gray-50 p-1">
          <button
            type="button"
            onClick={() => {
              setMode('organization');
              setError('');
              setSuccess('');
            }}
            className={`rounded-md px-3 py-2 text-sm font-medium transition ${mode === 'organization' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Create Organization
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('join');
              setError('');
              setSuccess('');
            }}
            className={`rounded-md px-3 py-2 text-sm font-medium transition ${mode === 'join' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Join Existing Org
          </button>
        </div>

        {mode === 'organization' && (
          <form className="space-y-4" onSubmit={onSubmit}>
            {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
            {success ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</div> : null}

            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">Organization Name</label>
              <input className="input-field" value={form.organization_name} onChange={(e) => setForm((f) => ({ ...f, organization_name: e.target.value }))} required />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">Organization Slug (optional)</label>
              <input className="input-field" value={form.organization_slug} onChange={(e) => setForm((f) => ({ ...f, organization_slug: e.target.value.toLowerCase() }))} placeholder="acme-corp" />
              <p className="mt-1 text-xs text-gray-500">Lowercase letters, numbers, hyphens only.</p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">First Name</label>
                <input className="input-field" value={form.admin_first_name} onChange={(e) => setForm((f) => ({ ...f, admin_first_name: e.target.value }))} />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">Last Name</label>
                <input className="input-field" value={form.admin_last_name} onChange={(e) => setForm((f) => ({ ...f, admin_last_name: e.target.value }))} />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">Admin Email</label>
              <input type="email" className="input-field" value={form.admin_email} onChange={(e) => setForm((f) => ({ ...f, admin_email: e.target.value }))} required />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">Admin Password</label>
              <input type="password" className="input-field" value={form.admin_password} onChange={(e) => setForm((f) => ({ ...f, admin_password: e.target.value }))} required />
              <PasswordCriteria password={form.admin_password} />
            </div>

            <div className="rounded-lg border border-gray-300 bg-gray-100 px-3 py-2 text-xs text-gray-700">
              New organizations start on the free self-serve tier. Your org admin can upgrade to Go, Plus, or Pro later to unlock higher limits and full access.
            </div>

            <button disabled={loading} className="btn-primary w-full">{loading ? 'Creating Organization...' : 'Create Organization'}</button>
          </form>
        )}

        {mode === 'join' && (
          <div className="space-y-4">
            <div className="rounded-lg border border-gray-300 bg-gray-100 px-3 py-3 text-sm text-gray-800">
              Joining an existing organization is invite-only.
            </div>
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-700">
              Ask your organization admin to create your user and send you the invitation/setup email.
            </div>
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-700">
              Already invited? Open the setup link from your email, set your password, then sign in.
            </div>
            <Link to="/login" className="btn-primary w-full">Go To Sign In</Link>
          </div>
        )}

        <p className="mt-6 text-center text-sm text-gray-600">
          Already have an account?{' '}
          <Link className="font-medium text-gray-900 hover:text-black" to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
