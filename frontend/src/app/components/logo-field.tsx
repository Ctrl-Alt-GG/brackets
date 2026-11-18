import { useId } from 'react';

/**
 * Uploads a logo as soon as a picture is chosen, shows the current one, and can remove it. The
 * label belongs to the file input alone: the remove button next to it has its own.
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
  const id = useId();

  return (
    <div className="fieldset">
      <label className="fieldset-legend" htmlFor={id}>
        {label}
      </label>
      <div className="flex items-center gap-3">
        {logoUrl ? (
          <img alt="" className="size-10 shrink-0 rounded-field object-contain" src={logoUrl} />
        ) : null}
        <input
          accept="image/png,image/jpeg"
          aria-describedby={`${id}-hint`}
          className="file-input w-full"
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
        {logoUrl ? (
          <button
            className="btn btn-ghost btn-sm"
            disabled={isPending}
            onClick={() => onChange(null)}
            type="button"
          >
            Remove
          </button>
        ) : null}
      </div>
      <span className="label whitespace-normal" id={`${id}-hint`}>
        PNG or JPEG. It is shown next to the name on the Details pages.
      </span>
    </div>
  );
}
