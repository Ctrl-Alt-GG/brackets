import { useForm, type FieldValues, type UseFormProps } from 'react-hook-form';

/**
 * A form that adds something, such as a player, and is empty again for the next one once it is
 * saved. Its fields are locked while it is being saved: wrap them in
 * `<fieldset className="contents" disabled={form.locked}>`, so that nothing typed in the meantime
 * is lost when the form empties. A refused submission keeps what was typed, to correct it.
 */
export function useCreateForm<TValues extends FieldValues, TContext = unknown, TOutput = TValues>(
  options: UseFormProps<TValues, TContext, TOutput>,
) {
  const form = useForm<TValues, TContext, TOutput>(options);

  /** The form's submit handler, which saves with `create`, such as a mutation's `mutateAsync`. */
  const submitWith = (create: (values: TOutput) => Promise<unknown>) =>
    form.handleSubmit(async (values) => {
      try {
        await create(values);
      } catch {
        // The mutation cache has shown the error already.
        return;
      }
      form.reset();
    });

  return { ...form, locked: form.formState.isSubmitting, submitWith };
}
