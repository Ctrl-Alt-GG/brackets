import { useId } from 'react';

import { useOrganizerTranslation } from '../organizer-locales';

/**
 * Uploads a logo as soon as a picture is chosen, shows the current one, and can remove it. The
 * field's name belongs to the file input alone: the remove button next to it has its own.
 */
export function LogoField({
  isPending,
  label,
  logoUrl,
  onChange,
}: {
  isPending: boolean;
  label: string;
  logoUrl: string | null;
  /** The chosen picture, or `null` to remove the current logo. */
  onChange: (file: File | null) => void;
}) {
  const { t } = useOrganizerTranslation();
  const id = useId();

  return (
    <div className="fieldset">
      <span className="fieldset-legend" id={`${id}-label`}>
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        {logoUrl ? (
          <img alt="" className="size-10 shrink-0 rounded-field object-contain" src={logoUrl} />
        ) : null}
        {/* The browser writes the file input's button and status in its own language, and the
            picture is uploaded as soon as it is chosen. So the input is hidden from sight, though
            not from the keyboard, and a button of the page's own opens it. */}
        <input
          accept="image/png,image/jpeg"
          aria-describedby={`${id}-hint`}
          aria-labelledby={`${id}-label`}
          className="peer sr-only"
          disabled={isPending}
          id={id}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onChange(file);
            // The same file can be chosen again, for instance after it was refused.
            event.target.value = '';
          }}
          type="file"
        />
        <label
          className="btn btn-soft btn-sm peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary peer-disabled:pointer-events-none peer-disabled:opacity-50"
          htmlFor={id}
        >
          {logoUrl ? t('common.replaceLogo') : t('common.uploadLogo')}
        </label>
        {logoUrl ? (
          <button
            className="btn btn-ghost btn-sm"
            disabled={isPending}
            onClick={() => onChange(null)}
            type="button"
          >
            {t('common.remove')}
          </button>
        ) : null}
      </div>
      <span className="label whitespace-normal" id={`${id}-hint`}>
        {t('common.logoHint')}
      </span>
    </div>
  );
}
