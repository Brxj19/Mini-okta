const listeners = new Set();

function emit(payload) {
  listeners.forEach((listener) => listener(payload));
}

export function subscribeToToasts(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pushToast(payload) {
  emit({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: payload?.type || 'info',
    title: payload?.title || '',
    message: payload?.message || '',
    duration: payload?.duration ?? 4000,
  });
}
