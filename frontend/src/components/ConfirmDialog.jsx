import React from 'react';
import Modal from './Modal';

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  onConfirm,
  onClose,
}) {
  const confirmClass = 'btn-primary';

  return (
    <Modal open={open} title={title} description={description} onClose={busy ? undefined : onClose}>
      <div className="flex flex-wrap justify-end gap-3">
        <button type="button" onClick={onClose} className="btn-secondary" disabled={busy}>
          {cancelLabel}
        </button>
        <button type="button" onClick={onConfirm} className={confirmClass} disabled={busy}>
          {busy ? 'Working...' : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
