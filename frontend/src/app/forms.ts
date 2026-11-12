import { z } from 'zod';

/** A `datetime-local` value, sent as the UTC timestamp the API expects. */
export const zLocalDateTime = z
  .string()
  .min(1, 'Pick a date and time')
  .transform((value) => new Date(value).toISOString());

/** A tournament's Details link: the same rule as the API's, checked while it is typed. */
export const zDetailsLink = z
  .string()
  .trim()
  .max(64, 'The Details link can be at most 64 characters long')
  .regex(
    /^([A-Za-z0-9_-]*[A-Za-z][A-Za-z0-9_-]*)?$/,
    'Use only letters, numbers, "-" and "_", with at least one letter',
  );
