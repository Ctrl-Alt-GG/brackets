import { dequal as equal } from 'dequal';
import { useCallback, useEffect, useRef } from 'react';
import {
  useForm,
  type DefaultValues,
  type FieldPath,
  type FieldPathValue,
  type FieldValues,
  type UseFormProps,
} from 'react-hook-form';

/**
 * An editor follows the server except for genuine unsaved edits. A successful mutation makes
 * its submission the new baseline, retaining anything typed while that request was in flight.
 * Spread saveCallbacks into the editor's mutation; create forms do not need this lifecycle.
 *
 * React Hook Form's own `values` with `resetOptions: { keepDirtyValues: true }` follows the
 * server too, but it can't replace this. It judges an edit against the values from before a save,
 * so a field typed back to its old value while the save is in flight looks unedited, and the
 * saved value would overwrite it. Its dirty state of a list also stays set once a single entry
 * changed, so a list that was changed and changed back would no longer follow the server.
 */
export function useSavedForm<TValues extends FieldValues, TContext = unknown, TOutput = TValues>({
  values,
  ...options
}: Omit<UseFormProps<TValues, TContext, TOutput>, 'values' | 'resetOptions'> & {
  values: TValues;
}) {
  const form = useForm<TValues, TContext, TOutput>({
    ...options,
    defaultValues: values as DefaultValues<TValues>,
  });
  const serverValues = useRef(structuredClone(values));
  const baselineValues = useRef(structuredClone(values));
  const submission = useRef<{ values: TValues; server: TValues } | null>(null);
  const { getValues, reset, setValue } = form;

  const resetKeeping = useCallback(
    (baseline: TValues, current: TValues, keep: (name: string) => boolean) => {
      reset(structuredClone(baseline));
      for (const key of Object.keys(current)) {
        if (keep(key)) {
          const name = key as FieldPath<TValues>;
          setValue(name, structuredClone(current[key]) as FieldPathValue<TValues, typeof name>, {
            shouldDirty: true,
          });
        }
      }
    },
    [reset, setValue],
  );

  useEffect(() => {
    if (equal(values, serverValues.current)) return;
    const previous = baselineValues.current;
    const current = getValues();
    const pending = submission.current;
    serverValues.current = structuredClone(values);
    baselineValues.current = structuredClone(values);
    resetKeeping(
      values,
      current,
      (key) =>
        !equal(current[key], previous[key]) ||
        (pending != null && !equal(current[key], pending.values[key])),
    );
  }, [getValues, resetKeeping, values]);

  const onMutate = useCallback(() => {
    submission.current = {
      server: structuredClone(serverValues.current),
      values: structuredClone(getValues()),
    };
  }, [getValues]);
  const onSuccess = useCallback(() => {
    const saved = submission.current;
    if (!saved) return;
    const current = getValues();
    // The global mutation callback refetches first. Prefer that response when it has arrived,
    // including server normalization; a failed refetch still leaves the saved submission clean.
    const baseline = equal(serverValues.current, saved.server)
      ? saved.values
      : serverValues.current;
    submission.current = null;
    baselineValues.current = structuredClone(baseline);
    resetKeeping(baseline, current, (key) => !equal(current[key], saved.values[key]));
  }, [getValues, resetKeeping]);
  const onError = useCallback(() => {
    submission.current = null;
  }, []);

  return { ...form, saveCallbacks: { onError, onMutate, onSuccess } };
}
