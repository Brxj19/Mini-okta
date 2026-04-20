import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import { hasRole } from '../utils/permissions';

const PAID_PLAN_CODES = new Set(['go', 'plus', 'pro']);

let razorpayScriptPromise = null;

function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(true);
  if (razorpayScriptPromise) return razorpayScriptPromise;

  razorpayScriptPromise = new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });

  return razorpayScriptPromise;
}

function formatDate(isoValue) {
  if (!isoValue) return 'Not available';
  const value = new Date(isoValue);
  if (Number.isNaN(value.getTime())) return 'Not available';
  return value.toLocaleString();
}

function formatPlanName(planCode) {
  if (!planCode) return 'Free';
  return planCode
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function getPlanRank(planCode) {
  return {
    free: 0,
    go: 1,
    plus: 2,
    pro: 3,
    enterprise_manual: 4,
  }[planCode] || 0;
}

export default function UpgradeAccess() {
  const { orgId, claims, isSuperAdmin } = useAuth();
  const isOrgAdmin = hasRole(claims, 'org:admin');
  const [planStatus, setPlanStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyPlanCode, setBusyPlanCode] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState('upi');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [demoCheckout, setDemoCheckout] = useState(null);
  const [upgradeRequestSaving, setUpgradeRequestSaving] = useState(false);
  const [upgradeRequestForm, setUpgradeRequestForm] = useState({
    company_name: '',
    company_website: '',
    company_size: '',
    primary_use_case: '',
    expected_monthly_users: '',
    requested_features: '',
    billing_contact_name: '',
    billing_contact_email: claims?.email || '',
    notes: '',
    agree_to_terms: false,
  });

  const refreshPlanStatus = async ({ withLoader = false } = {}) => {
    if (!orgId) return;
    if (withLoader) setLoading(true);
    try {
      const res = await api.get(`/api/v1/organizations/${orgId}/plan-status`);
      setPlanStatus(res.data);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to load billing details.');
    } finally {
      if (withLoader) setLoading(false);
    }
  };

  useEffect(() => {
    if (!orgId) {
      setLoading(false);
      return;
    }
    refreshPlanStatus({ withLoader: true });
  }, [orgId]);

  useEffect(() => {
    setUpgradeRequestForm((current) => ({
      ...current,
      billing_contact_email: current.billing_contact_email || claims?.email || '',
    }));
  }, [claims?.email]);

  const completeCheckout = async (payload) => {
    const res = await api.post(`/api/v1/organizations/${orgId}/billing/checkout-complete`, payload);
    setPlanStatus(res.data);
    return res.data;
  };

  const openRazorpayCheckout = async (checkout) => {
    const loaded = await loadRazorpayScript();
    if (!loaded || !window.Razorpay) {
      throw new Error('Unable to load Razorpay checkout right now.');
    }

    return new Promise((resolve, reject) => {
      const razorpay = new window.Razorpay({
        key: checkout.key_id,
        amount: checkout.amount_paise,
        currency: checkout.currency,
        name: checkout.merchant_name,
        description: checkout.description,
        order_id: checkout.order_id,
        prefill: checkout.prefill,
        theme: checkout.theme,
        handler: async (response) => {
          try {
            const updated = await completeCheckout({
              provider: 'razorpay',
              session_id: checkout.session_id,
              payment_method: paymentMethod,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            resolve(updated);
          } catch (err) {
            reject(err);
          }
        },
        modal: {
          ondismiss: () => reject(new Error('Checkout was closed before payment completed.')),
        },
      });

      razorpay.open();
    });
  };

  const startCheckout = async (planCode) => {
    if (!orgId) return;
    setError('');
    setSuccess('');
    setBusyPlanCode(planCode);

    try {
      const res = await api.post(`/api/v1/organizations/${orgId}/billing/checkout-session`, {
        plan_code: planCode,
        payment_method: paymentMethod,
      }, { skipToast: true, skipErrorToast: true });

      setPlanStatus(res.data.plan_status);
      const checkout = res.data.checkout || {};

      if (checkout.provider === 'demo') {
        setDemoCheckout(checkout);
        return;
      }

      await openRazorpayCheckout(checkout);
      setSuccess(`${formatPlanName(planCode)} plan activated successfully.`);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || err.message || 'Unable to start checkout.');
    } finally {
      setBusyPlanCode('');
    }
  };

  const confirmDemoCheckout = async () => {
    if (!demoCheckout) return;
    setActionLoading(true);
    setError('');
    setSuccess('');
    try {
      const updated = await completeCheckout({
        provider: 'demo',
        session_id: demoCheckout.session_id,
        payment_method: paymentMethod,
      });
      setDemoCheckout(null);
      setSuccess(`${formatPlanName(updated.current_plan_code)} plan activated successfully in demo mode.`);
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to complete demo payment.');
    } finally {
      setActionLoading(false);
    }
  };

  const manageSubscription = async (action) => {
    if (!orgId) return;
    setActionLoading(true);
    setError('');
    setSuccess('');
    try {
      const endpoint = action === 'cancel' ? 'cancel-at-period-end' : 'resume';
      const res = await api.post(`/api/v1/organizations/${orgId}/billing/${endpoint}`);
      setPlanStatus(res.data);
      setSuccess(
        action === 'cancel'
          ? 'Subscription will now end after the current billing cycle.'
          : 'Subscription renewal has been resumed.'
      );
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to update subscription right now.');
    } finally {
      setActionLoading(false);
    }
  };

  const submitUpgradeRequest = async () => {
    if (!orgId) return;
    setUpgradeRequestSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = {
        ...upgradeRequestForm,
        expected_monthly_users: upgradeRequestForm.expected_monthly_users
          ? Number(upgradeRequestForm.expected_monthly_users)
          : null,
      };
      const res = await api.post(`/api/v1/organizations/${orgId}/upgrade-request`, payload);
      setPlanStatus(res.data);
      setSuccess('Upgrade request submitted for super-admin review.');
    } catch (err) {
      setError(err.response?.data?.detail?.error_description || 'Unable to submit the upgrade request.');
    } finally {
      setUpgradeRequestSaving(false);
    }
  };

  if (loading) {
    return <div className="py-20 text-center text-gray-500">Loading billing details...</div>;
  }

  if (isSuperAdmin) {
    return <div className="py-20 text-center text-gray-500">Super admins do not manage organization subscriptions from this screen.</div>;
  }

  if (!isOrgAdmin) {
    return <div className="py-20 text-center text-gray-500">Only organization admins can manage plans and subscriptions.</div>;
  }

  if (!planStatus) {
    return <div className="py-20 text-center text-gray-500">No billing information is available for this organization.</div>;
  }

  const currentPlanCode = planStatus.current_plan_code || 'free';
  const subscription = planStatus.subscription;
  const currentPlan = planStatus.current_plan || {};
  const availablePlans = planStatus.available_plans || [];
  const activePaidPlanCode = subscription?.status === 'active' && PAID_PLAN_CODES.has(subscription?.plan_code)
    ? subscription.plan_code
    : null;
  const renewalAvailable = !!planStatus.renewal_available;
  const paidPlanBaseline = Math.max(
    getPlanRank(currentPlanCode),
    getPlanRank(planStatus.last_paid_plan_code)
  );
  const visiblePlans = availablePlans.filter((plan) => !PAID_PLAN_CODES.has(plan.code) || getPlanRank(plan.code) >= paidPlanBaseline);
  const upgradeRequest = planStatus.upgrade_request;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Billing"
        title="Plans And Subscription"
        description="Choose a paid plan, collect a demo payment, and manage the organization subscription lifecycle from one place."
      />

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
      {success ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</div> : null}

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="surface p-6">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${planStatus.access_tier === 'limited' ? 'bg-amber-100 text-amber-900' : 'bg-emerald-100 text-emerald-900'}`}>
              {planStatus.access_tier === 'limited' ? 'Free Tier' : 'Paid Tier'}
            </span>
            <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-700">
              Current plan: {currentPlan?.name || formatPlanName(currentPlanCode)}
            </span>
            <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-700">
              Verification: {planStatus.verification_status}
            </span>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Provider</p>
              <p className="mt-2 text-lg font-semibold text-gray-900">{planStatus.billing_provider === 'razorpay' ? 'Razorpay' : 'Demo Checkout'}</p>
              <p className="mt-1 text-sm text-gray-600">
                {planStatus.gateway_ready
                  ? 'Checkout is ready for the current provider.'
                  : 'Gateway keys are not configured, so demo checkout mode will be used.'}
              </p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Payment method</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setPaymentMethod('upi')}
                  className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${paymentMethod === 'upi' ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'}`}
                >
                  UPI
                </button>
                <button
                  type="button"
                  onClick={() => setPaymentMethod('card')}
                  className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${paymentMethod === 'card' ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'}`}
                >
                  Card
                </button>
              </div>
            </div>
          </div>
        </article>

        <article className="surface p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Subscription snapshot</p>
          <h2 className="mt-2 text-xl font-semibold text-gray-900">
            {subscription?.plan_name || currentPlan?.name || 'Free'}
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            {subscription?.status === 'expired'
              ? 'Your paid subscription cycle has ended and the organization is back on the free tier until renewal.'
              : currentPlanCode === 'free'
                ? 'This organization is currently running on the free self-serve tier.'
                : 'A paid subscription is currently active for this organization.'}
          </p>

          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-gray-500">Status</dt>
              <dd className="font-medium text-gray-900">{subscription?.status || 'inactive'}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-gray-500">Current cycle start</dt>
              <dd className="text-right font-medium text-gray-900">{formatDate(subscription?.current_period_start)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-gray-500">Current cycle end</dt>
              <dd className="text-right font-medium text-gray-900">{formatDate(subscription?.current_period_end)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-gray-500">Renewal preference</dt>
              <dd className="text-right font-medium text-gray-900">
                {subscription?.cancel_at_period_end ? 'Ends at cycle close' : 'Continue until canceled'}
              </dd>
            </div>
          </dl>

          <div className="mt-5 flex flex-wrap gap-3">
            {activePaidPlanCode ? (
              <>
                <button
                  type="button"
                  onClick={() => startCheckout(activePaidPlanCode)}
                  disabled={actionLoading || !!busyPlanCode || !renewalAvailable}
                  className="btn-primary"
                >
                  Renew Current Plan
                </button>
                {subscription?.cancel_at_period_end ? (
                  <button
                    type="button"
                    onClick={() => manageSubscription('resume')}
                    disabled={actionLoading}
                    className="btn-secondary"
                  >
                    Resume Subscription
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => manageSubscription('cancel')}
                    disabled={actionLoading}
                    className="btn-secondary"
                  >
                    Cancel At Period End
                  </button>
                )}
              </>
            ) : planStatus.last_paid_plan_code ? (
              <button
                type="button"
                onClick={() => startCheckout(planStatus.last_paid_plan_code)}
                disabled={!!busyPlanCode || !renewalAvailable}
                className="btn-primary"
              >
                Renew {formatPlanName(planStatus.last_paid_plan_code)}
              </button>
            ) : null}
          </div>
          {!renewalAvailable && activePaidPlanCode ? (
            <p className="mt-3 text-sm text-gray-500">
              Renewal becomes available when the current billing period ends on {formatDate(planStatus.renewal_available_at)}.
            </p>
          ) : null}
        </article>
      </section>

      <section className="surface p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Plans</p>
            <h2 className="mt-1 text-2xl font-semibold text-gray-900">Choose the right tier for your organization</h2>
            <p className="mt-1 text-sm text-gray-600">For the internship demo, these plans are intentionally priced at Rs 1, Rs 3, and Rs 5 per billing cycle.</p>
          </div>
          <p className="text-sm text-gray-500">Every subscription cycle runs for {currentPlan?.cycle_days || 30} days.</p>
        </div>

        <div className="mt-6 grid gap-4 xl:grid-cols-4">
          {visiblePlans.map((plan) => {
            const isCurrent = currentPlanCode === plan.code && subscription?.status === 'active';
            const isPaidPlan = PAID_PLAN_CODES.has(plan.code);
            const buttonLabel = !isPaidPlan
              ? 'Current free tier'
              : isCurrent
                ? 'Current plan'
                : currentPlanCode === 'free'
                  ? `Upgrade to ${plan.name}`
                  : `Switch to ${plan.name}`;

            return (
              <article
                key={plan.code}
                className={`rounded-3xl border p-5 transition-all ${plan.code === 'plus' ? 'border-gray-900 bg-gray-900 text-white shadow-xl' : 'border-gray-200 bg-white text-gray-900'}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className={`text-xs font-semibold uppercase tracking-[0.14em] ${plan.code === 'plus' ? 'text-gray-300' : 'text-gray-500'}`}>{plan.badge}</p>
                    <h3 className="mt-2 text-2xl font-semibold">{plan.name}</h3>
                  </div>
                  {isCurrent ? (
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${plan.code === 'plus' ? 'bg-white/15 text-white' : 'bg-gray-100 text-gray-700'}`}>
                      Current
                    </span>
                  ) : null}
                </div>

                <p className={`mt-4 text-3xl font-semibold ${plan.code === 'plus' ? 'text-white' : 'text-gray-900'}`}>
                  {plan.price_display}
                  {plan.price_paise > 0 ? <span className={`ml-1 text-sm font-medium ${plan.code === 'plus' ? 'text-gray-300' : 'text-gray-500'}`}>/ {plan.cycle_days} days</span> : null}
                </p>
                <p className={`mt-3 text-sm leading-6 ${plan.code === 'plus' ? 'text-gray-200' : 'text-gray-600'}`}>{plan.description}</p>

                <div className={`mt-4 rounded-2xl border p-3 text-sm ${plan.code === 'plus' ? 'border-white/10 bg-white/5 text-gray-200' : 'border-gray-200 bg-gray-50 text-gray-700'}`}>
                  <p>Max users: {plan.limits?.max_users || 'Unlimited'}</p>
                  <p className="mt-1">Max apps: {plan.limits?.max_apps || 'Unlimited'}</p>
                </div>

                <ul className={`mt-4 space-y-2 text-sm ${plan.code === 'plus' ? 'text-gray-200' : 'text-gray-700'}`}>
                  {plan.features.map((feature) => (
                    <li key={feature}>- {feature}</li>
                  ))}
                </ul>

                <button
                  type="button"
                  disabled={!isPaidPlan || isCurrent || !!busyPlanCode}
                  onClick={() => startCheckout(plan.code)}
                  className={`mt-6 w-full rounded-full px-4 py-3 text-sm font-semibold transition ${
                    !isPaidPlan || isCurrent
                      ? plan.code === 'plus'
                        ? 'cursor-not-allowed bg-white/10 text-white/70'
                        : 'cursor-not-allowed bg-gray-100 text-gray-400'
                      : plan.code === 'plus'
                        ? 'bg-white text-gray-900 hover:bg-gray-100'
                        : 'bg-gray-900 text-white hover:bg-black'
                  }`}
                >
                  {busyPlanCode === plan.code ? 'Preparing checkout...' : buttonLabel}
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="surface p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Payment history</p>
            <h2 className="mt-1 text-xl font-semibold text-gray-900">Recent billing activity</h2>
          </div>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-700">
            {planStatus.payments?.length || 0} payments
          </span>
        </div>

        {planStatus.payments?.length ? (
          <div className="mt-5 overflow-hidden rounded-2xl border border-gray-200">
            <div className="grid grid-cols-[1.2fr_1fr_1fr_1fr] gap-3 border-b border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">
              <span>Plan</span>
              <span>Amount</span>
              <span>Method</span>
              <span>Paid at</span>
            </div>
            {planStatus.payments.map((payment) => (
              <div key={payment.payment_id} className="grid grid-cols-[1.2fr_1fr_1fr_1fr] gap-3 border-t border-gray-100 px-4 py-3 text-sm text-gray-700 first:border-t-0">
                <div>
                  <p className="font-medium text-gray-900">{payment.plan_name || formatPlanName(payment.plan_code)}</p>
                  <p className="text-xs text-gray-500">{payment.provider} - {payment.payment_id}</p>
                </div>
                <span>Rs {(Number(payment.amount_paise || 0) / 100).toFixed(0)}</span>
                <span>{String(payment.payment_method || 'upi').toUpperCase()}</span>
                <span>{formatDate(payment.paid_at)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-5 rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center text-sm text-gray-500">
            No payments yet. Choose a paid plan to activate subscription billing for this organization.
          </div>
        )}
      </section>

      {planStatus.access_tier === 'limited' ? (
        <section className="surface p-6">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Verification upgrade</p>
              <h2 className="mt-1 text-2xl font-semibold text-gray-900">Request full access review</h2>
              <p className="mt-1 text-sm text-gray-600">Submit organization details so a super admin can review and unlock verified enterprise access.</p>
            </div>
            {upgradeRequest?.status ? (
              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
                Request status: {upgradeRequest.status}
              </span>
            ) : null}
          </div>

          {upgradeRequest?.payload ? (
            <div className="mt-5 rounded-2xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
              <p className="font-medium text-gray-900">Most recent submission</p>
              <p className="mt-1 text-xs text-gray-500">
                Submitted {upgradeRequest.submitted_at ? new Date(upgradeRequest.submitted_at).toLocaleString() : 'recently'} by {upgradeRequest.submitted_by_email || 'an org admin'}.
              </p>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Organization name</span>
              <input className="input-field" value={upgradeRequestForm.company_name} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, company_name: e.target.value }))} />
            </label>
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Website</span>
              <input className="input-field" value={upgradeRequestForm.company_website} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, company_website: e.target.value }))} placeholder="https://example.com" />
            </label>
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Company size</span>
              <input className="input-field" value={upgradeRequestForm.company_size} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, company_size: e.target.value }))} placeholder="1-10, 11-50, 51-200..." />
            </label>
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Expected monthly users</span>
              <input className="input-field" type="number" min="0" value={upgradeRequestForm.expected_monthly_users} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, expected_monthly_users: e.target.value }))} />
            </label>
            <label className="text-sm md:col-span-2">
              <span className="mb-1.5 block font-medium text-gray-700">Primary use case</span>
              <textarea className="input-field min-h-[108px]" value={upgradeRequestForm.primary_use_case} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, primary_use_case: e.target.value }))} />
            </label>
            <label className="text-sm md:col-span-2">
              <span className="mb-1.5 block font-medium text-gray-700">Requested features</span>
              <textarea className="input-field min-h-[108px]" value={upgradeRequestForm.requested_features} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, requested_features: e.target.value }))} />
            </label>
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Billing contact name</span>
              <input className="input-field" value={upgradeRequestForm.billing_contact_name} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, billing_contact_name: e.target.value }))} />
            </label>
            <label className="text-sm">
              <span className="mb-1.5 block font-medium text-gray-700">Billing contact email</span>
              <input className="input-field" type="email" value={upgradeRequestForm.billing_contact_email} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, billing_contact_email: e.target.value }))} />
            </label>
            <label className="text-sm md:col-span-2">
              <span className="mb-1.5 block font-medium text-gray-700">Notes</span>
              <textarea className="input-field min-h-[120px]" value={upgradeRequestForm.notes} onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, notes: e.target.value }))} />
            </label>
          </div>

          <label className="mt-5 flex items-start gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={upgradeRequestForm.agree_to_terms}
              onChange={(e) => setUpgradeRequestForm((current) => ({ ...current, agree_to_terms: e.target.checked }))}
              className="mt-0.5 h-4 w-4 rounded border-gray-300"
            />
            <span>I confirm that these details are accurate and that the organization is requesting a verified enterprise review.</span>
          </label>

          <div className="mt-5 flex justify-end">
            <button type="button" onClick={submitUpgradeRequest} disabled={upgradeRequestSaving} className="btn-primary">
              {upgradeRequestSaving ? 'Submitting...' : 'Submit upgrade request'}
            </button>
          </div>
        </section>
      ) : null}

      {demoCheckout ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-3xl border border-gray-200 bg-white p-6 shadow-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Demo payment</p>
            <h3 className="mt-2 text-2xl font-semibold text-gray-900">Complete checkout</h3>
            <p className="mt-2 text-sm text-gray-600">
              This project is in demo billing mode. Confirm the payment below to simulate a successful {paymentMethod.toUpperCase()} transaction.
            </p>

            <div className="mt-5 rounded-2xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
              <div className="flex items-center justify-between gap-3">
                <span>Plan</span>
                <span className="font-medium text-gray-900">{formatPlanName(demoCheckout.plan_code)}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span>Amount</span>
                <span className="font-medium text-gray-900">Rs {(Number(demoCheckout.amount_paise || 0) / 100).toFixed(0)}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span>Method</span>
                <span className="font-medium text-gray-900">{paymentMethod.toUpperCase()}</span>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => setDemoCheckout(null)}
                disabled={actionLoading}
                className="btn-secondary flex-1"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDemoCheckout}
                disabled={actionLoading}
                className="btn-primary flex-1"
              >
                {actionLoading ? 'Confirming...' : 'Confirm Payment'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
