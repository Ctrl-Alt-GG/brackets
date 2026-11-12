import { Field } from '../ui';

/** Uploads a logo as soon as a picture is chosen, shows the current one, and can remove it. */
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
  return (
    <Field hint="PNG or JPEG. It is shown next to the name on the Details pages." label={label}>
      <span className="flex items-center gap-3">
        {logoUrl ? (
          <img alt="" className="size-10 shrink-0 rounded-field object-contain" src={logoUrl} />
        ) : null}
        <input
          accept="image/png,image/jpeg"
          className="file-input w-full"
          disabled={isPending}
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
      </span>
    </Field>
  );
}
