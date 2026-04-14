import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../branding';
import CopyButton from '../components/CopyButton';
import { ArrowLeftIcon, ProductMark } from '../components/Icons';
import AuthParticleCanvas from '../components/AuthParticleCanvas';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState('credentials');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [challengeToken, setChallengeToken] = useState('');
  const [manualEntryKey, setManualEntryKey] = useState('');
  const [qrCodeDataUrl, setQrCodeDataUrl] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/api/v1/login', { email, password });
      if (res.data?.mfa_required) {
        setStep('mfa');
        setChallengeToken(res.data.challenge_token || '');
        setMfaCode('');
        setQrCodeDataUrl('');
        return;
      }
      if (res.data?.mfa_setup_required) {
        setStep('mfa-setup');
        setChallengeToken(res.data.challenge_token || '');
        setManualEntryKey(res.data.manual_entry_key || '');
        setQrCodeDataUrl(res.data.qr_code_data_url || '');
        setMfaCode('');
        return;
      }
      login(res.data.id_token);
      navigate('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail || {};
      if (detail.error === 'password_setup_required') {
        setError('Complete account setup from invitation email before signing in.');
      } else if (detail.error === 'password_expired' || detail.error === 'password_expired_hard') {
        setError('Password expired. Use the reset flow to continue.');
      } else if (detail.error === 'mfa_challenge_expired') {
        setStep('credentials');
        setChallengeToken('');
        setMfaCode('');
        setManualEntryKey('');
        setQrCodeDataUrl('');
        setBackupCodes([]);
        setError(detail.error_description || 'Your MFA challenge expired. Sign in again.');
      } else {
        setError(detail.error_description || 'Sign in failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleMfaSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/api/v1/login/mfa/verify', {
        challenge_token: challengeToken,
        code: mfaCode,
      });
      if (res.data?.backup_codes?.length) {
        login(res.data.id_token);
        setBackupCodes(res.data.backup_codes || []);
        setStep('backup-codes');
        return;
      }
      login(res.data.id_token);
      navigate('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail || {};
      setError(detail.error_description || 'Unable to verify authenticator code.');
    } finally {
      setLoading(false);
    }
  };

  const resetToCredentials = () => {
    setStep('credentials');
    setChallengeToken('');
    setMfaCode('');
    setManualEntryKey('');
    setQrCodeDataUrl('');
    setBackupCodes([]);
    setError('');
    setLoading(false);
  };

  return (
    <div className="auth-cosmos-shell flex min-h-screen items-start justify-center px-4 py-6 sm:py-10 md:items-center">
      <AuthParticleCanvas />
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-[0_20px_48px_rgba(15,23,42,0.08)] sm:p-8">
        <div className="mb-5">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            Back to home
          </Link>
        </div>

        <div className="mb-7 flex items-center gap-3">
          <ProductMark className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold text-gray-900">{PRODUCT_NAME}</h1>
            <p className="text-sm text-gray-600">{PRODUCT_TAGLINE}</p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold tracking-tight text-gray-900">
          {step === 'credentials'
            ? 'Sign in'
            : step === 'mfa'
              ? 'Verify your sign-in'
              : step === 'mfa-setup'
                ? 'Set up Google Authenticator'
                : 'Save your backup codes'}
        </h2>
        <p className="mt-1 text-sm text-gray-600">
          {step === 'credentials'
            ? `Continue to your ${PRODUCT_NAME} workspace.`
            : step === 'mfa'
              ? 'Enter the current 6-digit code from your authenticator app or one of your backup codes.'
              : step === 'mfa-setup'
                ? 'Your organization requires multi-factor authentication before you can continue.'
                : 'These recovery codes are shown only once. Store them somewhere safe before you continue.'}
        </p>

        <form onSubmit={step === 'credentials' ? handleSubmit : handleMfaSubmit} className="mt-6 space-y-4">
          {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

          {step === 'credentials' ? (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@example.com" required />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input-field" placeholder="••••••••" required />
              </div>
            </>
          ) : null}

          {step === 'mfa-setup' ? (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
              {qrCodeDataUrl ? (
                <div className="mb-4 flex justify-center rounded-xl border border-gray-200 bg-white p-4">
                  <img src={qrCodeDataUrl} alt="Google Authenticator setup QR code" className="h-44 w-44" />
                </div>
              ) : null}
              <p className="text-sm font-medium text-gray-900">Manual setup key</p>
              <div className="mt-2 flex items-start justify-between gap-3">
                <p className="break-all font-mono text-xs leading-6 text-gray-700">{manualEntryKey}</p>
                <CopyButton value={manualEntryKey} label="Copy setup key" />
              </div>
              <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-gray-600">
                <li>Open Google Authenticator and scan the QR code.</li>
                <li>If needed, select <strong>Enter a setup key</strong>.</li>
                <li>Use your email address as the account name.</li>
                <li>Paste this key only if scanning is unavailable, then enter the 6-digit code below.</li>
              </ol>
            </div>
          ) : null}

          {step === 'mfa' || step === 'mfa-setup' ? (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                {step === 'mfa-setup' ? 'Authenticator code' : 'Authenticator or backup code'}
              </label>
              <input
                type="text"
                value={mfaCode}
                onChange={(e) => setMfaCode(
                  step === 'mfa-setup'
                    ? e.target.value.replace(/\D/g, '').slice(0, 6)
                    : e.target.value.toUpperCase().replace(/[^A-Z0-9-\s]/g, '').slice(0, 24)
                )}
                className="input-field"
                inputMode={step === 'mfa-setup' ? 'numeric' : 'text'}
                autoComplete="one-time-code"
                placeholder={step === 'mfa-setup' ? '123456' : '123456 or ABCD-EFGH-IJKL'}
                required
              />
            </div>
          ) : null}

          {step !== 'backup-codes' ? (
            <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
              {loading
                ? step === 'credentials'
                  ? 'Signing in...'
                  : 'Verifying...'
                : step === 'credentials'
                  ? 'Sign in'
                  : step === 'mfa'
                    ? 'Verify code'
                    : 'Finish MFA setup'}
            </button>
          ) : null}
        </form>

        {step === 'backup-codes' ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-gray-900">Recovery codes</p>
                <CopyButton value={backupCodes.join('\n')} label="Copy codes" />
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {backupCodes.map((code) => (
                  <div key={code} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-center font-mono text-xs tracking-[0.16em] text-gray-700">
                    {code}
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-gray-600">
                Each code works once. You can use them if you lose access to Google Authenticator.
              </p>
            </div>
            <button type="button" className="btn-primary w-full justify-center" onClick={() => navigate('/dashboard')}>
              Continue to dashboard
            </button>
          </div>
        ) : null}

        {step === 'credentials' ? (
          <div className="mt-5 flex items-center justify-between text-sm">
            <Link to="/password-reset/request" className="font-medium text-gray-700 hover:text-black">Forgot password?</Link>
            <Link to="/signup" className="font-medium text-gray-700 hover:text-black">Create account</Link>
          </div>
        ) : step !== 'backup-codes' ? (
          <div className="mt-5 text-center text-sm">
            <button type="button" onClick={resetToCredentials} className="font-medium text-gray-700 hover:text-black">
              Back to sign in
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
