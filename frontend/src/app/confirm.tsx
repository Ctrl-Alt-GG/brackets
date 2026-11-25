import { useEffect, useRef, type ReactNode } from 'react';
import { confirmable, createConfirmation, type ConfirmDialogProps } from 'react-confirm';

import { useOrganizerTranslation } from './organizer-locales';

type ConfirmOptions = {
  /** What is about to happen, as a question, or the paragraphs that lead up to it. */
  message: ReactNode;
  /** The button that goes ahead, named after what it does. */
  confirmLabel: string;
  /** For what can't be undone: the button that goes ahead is red. */
  destructive?: boolean;
};

/**
 * A modal dialog of the page itself. Unlike `window.confirm`, it matches the site, doesn't stop
 * the page while it is open, and can't be switched off by the browser's "prevent additional
 * dialogs", after which a destructive action would run without asking. Cancel has the focus
 * first, so pressing Enter by habit doesn't go ahead.
 */
function ConfirmDialog({
  confirmLabel,
  destructive = false,
  message,
  proceed,
  show,
}: ConfirmDialogProps<ConfirmOptions, boolean>) {
  const { t } = useOrganizerTranslation();
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (show) dialog.current?.showModal();
    else dialog.current?.close();
  }, [show]);

  return (
    <dialog
      className="modal"
      // Escape cancels.
      onCancel={(event) => {
        event.preventDefault();
        proceed(false);
      }}
      ref={dialog}
    >
      <div className="modal-box space-y-2">
        {typeof message === 'string' ? <p>{message}</p> : message}
        <div className="modal-action">
          <button className="btn btn-ghost" onClick={() => proceed(false)} type="button">
            {t('common.cancel')}
          </button>
          <button
            className={destructive ? 'btn btn-error' : 'btn btn-primary'}
            onClick={() => proceed(true)}
            type="button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
      {/* daisyUI's backdrop: a click next to the dialog cancels too. Only for the pointer, as
          the keyboard has Escape and the Cancel button. */}
      <form className="modal-backdrop" method="dialog">
        <button aria-hidden="true" onClick={() => proceed(false)} tabIndex={-1} type="submit">
          {t('common.cancel')}
        </button>
      </form>
    </dialog>
  );
}

/** Resolves to whether the organizer went ahead. */
// Removed once daisyUI's closing transition, 0.3 seconds, has run.
export const confirm = createConfirmation(confirmable(ConfirmDialog), 400);
