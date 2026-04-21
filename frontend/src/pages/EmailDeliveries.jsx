import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import PageHeader from '../components/PageHeader';
import CopyButton from '../components/CopyButton';

export default function EmailDeliveries() {
  const { orgId, isSuperAdmin } = useAuth();
  const [rows, setRows] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [eventKey, setEventKey] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [processing, setProcessing] = useState(false);
  const [processSummary, setProcessSummary] = useState(null);

  const fetchRows = async (loadMore = false) => {
    if (!orgId && !isSuperAdmin) return;
    setLoading(true);
    const params = new URLSearchParams();
    params.set('limit', '25');
    if (status) params.set('status', status);
    if (eventKey) params.set('event_key', eventKey);
    if (toEmail) params.set('to_email', toEmail);
    if (loadMore && cursor) params.set('cursor', cursor);
    try {
      const basePath = isSuperAdmin
        ? '/api/v1/admin/email-deliveries'
        : `/api/v1/organizations/${orgId}/email-deliveries`;
      const res = await api.get(`${basePath}?${params.toString()}`);
      const data = res.data?.data || [];
      const pagination = res.data?.pagination || {};
      setRows((prev) => (loadMore ? [...prev, ...data] : data));
      setCursor(pagination.next_cursor || null);
      setHasMore(!!pagination.has_more);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRows(false); }, [orgId, status, eventKey, toEmail, isSuperAdmin]);

  const processQueue = async () => {
    setProcessing(true);
    try {
      const res = await api.post('/api/v1/admin/email-deliveries/process?limit=100');
      setProcessSummary(res.data || null);
      await fetchRows(false);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Email Queue"
        description="Delivery tracking, retries, and dead-letter visibility."
        actions={
          <div className="flex items-center gap-2">
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="input-field max-w-[170px] text-sm">
              <option value="">All statuses</option>
              <option value="pending">pending</option>
              <option value="sent">sent</option>
              <option value="failed">failed</option>
              <option value="dead">dead</option>
            </select>
            <input
              value={eventKey}
              onChange={(e) => setEventKey(e.target.value)}
              className="input-field max-w-[200px] text-sm"
              placeholder="Event key"
            />
            <input
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              className="input-field max-w-[220px] text-sm"
              placeholder="Recipient email"
            />
            {isSuperAdmin && <button onClick={processQueue} disabled={processing} className="btn-secondary text-sm">{processing ? 'Processing...' : 'Process queue'}</button>}
          </div>
        }
      />

      <div className="section-shell overflow-hidden">
        {processSummary ? (
          <div className="border-b border-emerald-200 bg-emerald-50 px-6 py-3 text-sm text-emerald-800">
            {processSummary.message}
          </div>
        ) : null}
        <table className="w-full">
          <thead>
            <tr className="table-header">
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase text-dark-400">To</th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase text-dark-400">Event</th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase text-dark-400">Status</th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase text-dark-400">Attempts</th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase text-dark-400">Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="table-row">
                <td className="px-6 py-3 text-sm text-dark-300">
                  <div className="flex items-center gap-2">
                    <span>{row.to_email}</span>
                    <CopyButton value={row.to_email} label="Copy email" />
                  </div>
                </td>
                <td className="px-6 py-3 text-sm text-dark-300">{row.event_key}</td>
                <td className="px-6 py-3">
                  <span className={row.status === 'sent' ? 'badge-green' : row.status === 'dead' ? 'badge-red' : row.status === 'failed' ? 'badge-yellow' : 'badge-gray'}>
                    {row.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-sm text-dark-300">{row.attempt_count}/{row.max_attempts}</td>
                <td className="px-6 py-3 text-sm text-dark-400">{new Date(row.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {rows.length === 0 && !loading && <tr><td colSpan={5} className="py-8 text-center text-sm text-dark-500">No emails found.</td></tr>}
          </tbody>
        </table>
      </div>

      {hasMore && <div className="mt-4 text-center"><button onClick={() => fetchRows(true)} className="btn-secondary">{loading ? 'Loading...' : 'Load more'}</button></div>}
    </div>
  );
}
