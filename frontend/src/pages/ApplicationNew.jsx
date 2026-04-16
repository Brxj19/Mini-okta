import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import { ArrowLeftIcon, CheckIcon } from '../components/Icons';

export default function ApplicationNew() {
  const { orgId } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: '', app_type: 'web', redirect_uris: '', allowed_scopes: 'openid,profile,email',
    post_logout_redirect_uris: '',
    id_token_lifetime: 3600, access_token_lifetime: 3600, refresh_token_enabled: false, logo_url: '',
  });
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        ...form,
        redirect_uris: form.redirect_uris.split(',').map(s => s.trim()).filter(Boolean),
        post_logout_redirect_uris: form.post_logout_redirect_uris.split(',').map(s => s.trim()).filter(Boolean),
        allowed_scopes: form.allowed_scopes.split(',').map(s => s.trim()).filter(Boolean),
      };
      const res = await api.post(`/api/v1/organizations/${orgId}/applications`, payload);
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Failed to create application');
    }
    setLoading(false);
  };

  if (result) {
    return (
      <div className="max-w-2xl">
        <div className="card">
          <div className="text-center mb-6">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
              <CheckIcon className="h-6 w-6" />
            </div>
            <h2 className="text-xl font-bold mt-2">Application Created</h2>
            <p className="text-dark-400 mt-1">Save these credentials — the client secret will NOT be shown again.</p>
          </div>
          <dl className="space-y-4">
            <div className="bg-dark-900 rounded-lg p-4">
              <dt className="text-xs text-dark-400 uppercase mb-1">Client ID</dt>
              <dd className="font-mono text-primary-400 break-all">{result.client_id}</dd>
            </div>
            {result.client_secret && (
              <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
                <dt className="text-xs text-red-400 uppercase mb-1">Client Secret (ONE-TIME DISPLAY)</dt>
                <dd className="font-mono text-red-300 break-all">{result.client_secret}</dd>
              </div>
            )}
            <div className="bg-dark-900 rounded-lg p-4">
              <dt className="text-xs text-dark-400 uppercase mb-1">App Type</dt>
              <dd className="text-dark-200">{result.app_type}</dd>
            </div>
          </dl>
          <button onClick={() => navigate('/applications')} className="btn-primary mt-6 w-full">Go to Applications</button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <button onClick={() => navigate('/applications')} className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-dark-400 hover:text-dark-200"><ArrowLeftIcon className="h-4 w-4" />Back</button>
      <h1 className="text-2xl font-bold mb-6">Register Application</h1>
      <form onSubmit={handleSubmit} className="card space-y-5">
        {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">{error}</div>}
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Application Name *</label>
          <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="input-field" />
        </div>
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Type *</label>
          <select value={form.app_type} onChange={e => setForm(f => ({ ...f, app_type: e.target.value }))} className="input-field">
            <option value="web">Web (confidential)</option>
            <option value="spa">SPA (public)</option>
            <option value="native">Native (public)</option>
            <option value="m2m">M2M (machine-to-machine)</option>
          </select>
          <p className="text-xs text-dark-500 mt-1">SPA/native: PKCE required, no client secret. Web/M2M: client secret generated.</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Redirect URIs *</label>
          <input required value={form.redirect_uris} onChange={e => setForm(f => ({ ...f, redirect_uris: e.target.value }))} className="input-field" placeholder="http://localhost:4000/callback" />
          <p className="text-xs text-dark-500 mt-1">Comma-separated list of allowed callback URLs</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Post-Logout Redirect URIs</label>
          <input
            value={form.post_logout_redirect_uris}
            onChange={e => setForm(f => ({ ...f, post_logout_redirect_uris: e.target.value }))}
            className="input-field"
            placeholder="http://localhost:4000, http://localhost:4000/logged-out"
          />
          <p className="text-xs text-dark-500 mt-1">Comma-separated list of safe URLs SigAuth can redirect to after IdP logout.</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Scopes</label>
          <input value={form.allowed_scopes} onChange={e => setForm(f => ({ ...f, allowed_scopes: e.target.value }))} className="input-field" />
        </div>
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-1">Logo URL</label>
          <input
            value={form.logo_url}
            onChange={e => setForm(f => ({ ...f, logo_url: e.target.value }))}
            className="input-field"
            placeholder="https://example.com/logo.png"
          />
          <p className="text-xs text-dark-500 mt-1">Shown on the IdP sign-in screen when this application requests access.</p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-1">ID Token Lifetime (s)</label>
            <input type="number" value={form.id_token_lifetime} onChange={e => setForm(f => ({ ...f, id_token_lifetime: parseInt(e.target.value) }))} className="input-field" />
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-1">Access Token Lifetime (s)</label>
            <input type="number" value={form.access_token_lifetime} onChange={e => setForm(f => ({ ...f, access_token_lifetime: parseInt(e.target.value) }))} className="input-field" />
          </div>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.refresh_token_enabled} onChange={e => setForm(f => ({ ...f, refresh_token_enabled: e.target.checked }))} className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500" />
          <span className="text-sm text-dark-300">Enable Refresh Tokens</span>
        </label>
        <button type="submit" disabled={loading} className="btn-primary">{loading ? 'Creating...' : 'Register Application'}</button>
      </form>
    </div>
  );
}
