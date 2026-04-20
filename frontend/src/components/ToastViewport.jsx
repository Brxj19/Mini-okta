import React, { useEffect, useState } from 'react';
import { subscribeToToasts } from '../utils/toastBus';

const toneClasses = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-red-200 bg-red-50 text-red-900',
  info: 'border-slate-200 bg-white text-slate-900',
};

export default function ToastViewport() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    return subscribeToToasts((toast) => {
      setToasts((current) => [...current, toast]);
      window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== toast.id));
      }, toast.duration);
    });
  }, []);

  if (!toasts.length) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[120] flex w-full max-w-sm flex-col gap-3">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto rounded-2xl border px-4 py-3 shadow-lg shadow-black/10 ${toneClasses[toast.type] || toneClasses.info}`}
        >
          {toast.title ? <p className="text-sm font-semibold">{toast.title}</p> : null}
          <p className={`text-sm ${toast.title ? 'mt-1' : ''}`}>{toast.message}</p>
          <button
            type="button"
            onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}
            className="mt-2 text-xs font-medium text-current/70 hover:text-current"
          >
            Dismiss
          </button>
        </div>
      ))}
    </div>
  );
}
