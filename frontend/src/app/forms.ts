import { z } from 'zod';

/** A `datetime-local` value, sent as the UTC timestamp the API expects. */
export const zLocalDateTime = z
  .string()
  .min(1, 'Pick a date and time')
  .transform((value) => new Date(value).toISOString());
